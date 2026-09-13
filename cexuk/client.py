"""CeX UK prices from CeX's own public search index. Standard library only.

The storefront (uk.webuy.com) refuses a server, and this does not try to get
past that. The site's SEARCH box queries an Algolia index at search.webuy.io,
which answers a plain, unauthenticated request with the same rows the website
renders. This asks the way the page asks: one POST, a JSON body, no key.

⚠️ This is not an official API. There is no contract and no versioning, and it
can change whenever CeX's front end does. Nothing here should fail loudly when
it does: a dead lookup returns ABSENT, never a price of zero.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .match import MIN_MATCH, match_score

__version__ = "0.1.0"

SEARCH = "https://search.webuy.io/1/indexes/*/queries"
INDEX = "prod_cex_uk"
# ⚠️ An honest name, not a browser's. Measured 2026-09-13: the index serves
# the same rows to a named client as to a browser string, so there is nothing to
# gain by pretending. If it ever stops serving an honest client, that is the
# answer.
UA = f"cex-uk-prices/{__version__} (+https://github.com/casareanderson/cex-uk-prices)"
TIMEOUT = 20
# UK only. The index is the UK one; each row also carries `origin`, and a row
# that says another country is dropped rather than trusted.
ORIGIN = "UK"
# Politeness. One request per lookup, at most one per MIN_INTERVAL seconds from
# this process, no retries. This works because it looks like ordinary use.
MIN_INTERVAL = 1.0

_lock = threading.Lock()
_last = 0.0


def _pace() -> None:
    global _last
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()


# ⚠️ The grade is a bare trailing capital, and NOT always after a comma:
# "…Midnight, Unlocked B" is grade B with the comma three words earlier.
_GRADE = re.compile(r"[,\s]\s*([ABC])\s*$")


@dataclass
class Row:
    """One CeX listing: one product at one grade."""
    name: str
    grade: str             # A / B / C - CeX's own condition ladder
    sell_gbp: float        # sellPrice: what CeX RETAILS it for. An ask; nobody paid it.
    cash_gbp: float        # cashPriceCalculated: what CeX pays you in cash today. 0 = won't buy.
    voucher_gbp: float     # exchangePriceCalculated: the same in store credit. Not money.
    cash_pct: int          # buyPerc: cash as a % of retail
    voucher_pct: int       # exchangePerc: voucher as a % of retail
    box_id: str
    launch_gbp: float = 0.0      # firstPrice
    category: str = ""           # categoryName, e.g. "Headphones"
    super_category: str = ""     # superCatName, e.g. "Electronics"
    stores: tuple = field(default_factory=tuple)   # UK stores holding THIS grade
    online_qty: int = 0          # ecomQuantity
    previous_gbp: float = 0.0    # previousPrice: retail before the last change
    price_changed: str = ""      # priceLastChanged, as YYYY-MM-DD
    discontinued: bool = False
    origin: str = ""

    @property
    def product_id(self) -> str:
        """⚠️ boxId is <product code><grade letter>: ...117A, ...117B and ...117C
        are ONE product at three conditions, not three pieces of evidence."""
        if self.grade and self.box_id.endswith(self.grade):
            return self.box_id[:-1]
        return self.box_id


def _names(v) -> tuple:
    return tuple(s.strip() for s in (v or []) if isinstance(s, str) and s.strip())


def row_from_hit(h: dict) -> Row:
    """One Algolia hit -> one Row. Pure, so it can be tested on real shapes.

    ⚠️ Rows are not uniform: some have no priceLastChanged, previousPrice or
    stores at all. Everything optional defaults.
    ⚠️ `boxBuyAllowed` is deliberately NOT read. It does not mean "CeX will buy
    this": measured on a Google Nest Mini (2nd Gen), boxBuyAllowed=1 with a £0
    cash price and discontinued=1.
    """
    name = (h.get("boxName") or "").strip()
    m = _GRADE.search(name)
    return Row(
        name=_GRADE.sub("", name).strip(),
        grade=m.group(1) if m else "",
        sell_gbp=float(h.get("sellPrice") or 0),
        cash_gbp=float(h.get("cashPriceCalculated") or 0),
        voucher_gbp=float(h.get("exchangePriceCalculated") or 0),
        cash_pct=int(h.get("buyPerc") or 0),
        voucher_pct=int(h.get("exchangePerc") or 0),
        box_id=str(h.get("boxId") or ""),
        launch_gbp=float(h.get("firstPrice") or 0),
        category=str(h.get("categoryName") or "").strip(),
        super_category=str(h.get("superCatName") or "").strip(),
        stores=_names(h.get("stores")),
        online_qty=int(h.get("ecomQuantity") or 0),
        previous_gbp=float(h.get("previousPrice") or 0),
        price_changed=str(h.get("priceLastChanged") or "")[:10],
        discontinued=bool(h.get("discontinued")),
        origin=str(h.get("origin") or "").strip())


def search(query: str, limit: int = 6) -> list[Row]:
    """Raw rows for a query. NOT relevance-checked - use `lookup()` for that.

    Returns [] on any failure: a dead lookup must never read as "CeX says £0".
    """
    body = json.dumps({"requests": [{
        "indexName": INDEX,
        "params": f"query={urllib.parse.quote(query or '')}&hitsPerPage={int(limit)}",
    }]}).encode()
    req = urllib.request.Request(SEARCH, data=body, headers={
        "User-Agent": UA, "Content-Type": "application/json"})
    _pace()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            hits = (json.load(r).get("results") or [{}])[0].get("hits") or []
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError):
        return []
    rows = [row_from_hit(h) for h in hits if isinstance(h, dict)]
    return [r for r in rows if r.sell_gbp > 0 and (r.origin or ORIGIN).upper() == ORIGIN]


def price_move(row: Row) -> str:
    """'CeX raised it £55 → £60 on 29 Aug 2026', or '' when nothing moved."""
    if not (row.previous_gbp and row.sell_gbp) or abs(row.previous_gbp - row.sell_gbp) < 0.005:
        return ""
    verb = "raised" if row.sell_gbp > row.previous_gbp else "cut"
    when = ""
    try:
        d = dt.date.fromisoformat(row.price_changed)
        when = f" on {d.day} {d:%b %Y}"
    except ValueError:
        pass
    return f"CeX {verb} it £{row.previous_gbp:.0f} → £{row.sell_gbp:.0f}{when}"


def lookup(query: str, limit: int = 6) -> dict:
    """Rows that are really the product asked about, and what they add up to.

    `rows`       rows that cleared the match gate (MIN_MATCH)
    `rejected`   (score, row) pairs that did not - CeX always returns something
    `products`   distinct products among `rows` (grades of one product count once)
    `sell`/`cash`/`voucher`   from the BEST cash offer's row, so the three
                 numbers describe the same grade of the same product
    `stores`/`online_qty`     pooled across the grades of THAT product only
    `price_move`, `discontinued`, `category`   from that row
    `checked`    when this was read - stock and prices are a snapshot

    When nothing matches, `rows` is empty and there is no `cash` key at all:
    no match is not an offer of £0.
    """
    got = search(query, limit)
    scored = [(match_score(query, r.name), r) for r in got]
    rows = [r for s, r in scored if s >= MIN_MATCH]
    out: dict = {"query": query, "rows": rows,
                 "rejected": [(round(s, 2), r) for s, r in scored if s < MIN_MATCH],
                 "checked": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    if not rows:
        out["note"] = (f"no CeX match ({len(got)} result(s) returned, none the same product)"
                       if got else "no CeX match")
        return out
    best = max(rows, key=lambda r: r.cash_gbp)
    same = [r for r in rows if r.product_id == best.product_id]
    stores = sorted({s for r in same for s in r.stores})
    out.update({
        "products": len({r.product_id for r in rows}),
        "product": best.name, "grade": best.grade,
        "sell": best.sell_gbp, "cash": best.cash_gbp, "voucher": best.voucher_gbp,
        "cash_pct": best.cash_pct, "voucher_pct": best.voucher_pct,
        "category": best.category, "super_category": best.super_category,
        "stores": stores, "online_qty": sum(r.online_qty for r in same),
        "price_move": price_move(best), "discontinued": best.discontinued,
    })
    out["note"] = (f"CeX sells it for £{best.sell_gbp:.0f} (grade {best.grade or '-'}) and pays "
                   + (f"£{best.cash_gbp:.0f} cash / £{best.voucher_gbp:.0f} voucher"
                      if best.cash_gbp else "nothing - it will not buy this one"
                      + (" (discontinued)" if best.discontinued else "")))
    return out


def floor_warning(ask_gbp: float, cash_gbp: float) -> str:
    """Said out loud when an asking price is below what CeX would simply pay."""
    if not (ask_gbp and cash_gbp) or ask_gbp >= cash_gbp:
        return ""
    return (f"£{ask_gbp:.2f} is below the £{cash_gbp:.0f} CeX would pay in cash today. "
            f"Selling it for that loses money against trading it in.")
