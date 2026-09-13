"""python -m cexuk "Sony WH-1000XM4" [--limit 6] [--ask 60] [--json] [--rejected]"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .client import floor_warning, lookup


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cexuk", description="CeX UK retail and trade-in prices.")
    ap.add_argument("query", help="what to look up, e.g. \"Sony WH-1000XM4\"")
    ap.add_argument("--limit", type=int, default=6, help="rows to ask CeX for (default 6)")
    ap.add_argument("--ask", type=float, default=0.0,
                    help="your intended asking price, checked against CeX's cash offer")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--rejected", action="store_true",
                    help="also show the rows CeX returned that are NOT this product")
    a = ap.parse_args(argv)

    r = lookup(a.query, a.limit)
    if a.json:
        doc = {**r, "rows": [dataclasses.asdict(x) for x in r["rows"]],
               "rejected": [{"score": s, **dataclasses.asdict(x)} for s, x in r["rejected"]]}
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0 if r["rows"] else 1

    if not r["rows"]:
        print(r["note"])
    else:
        print(r["note"])
        print(f"\n{'grade':<6}{'sells':>8}{'cash':>8}{'voucher':>9}{'stores':>8}{'online':>8}  name")
        for x in sorted(r["rows"], key=lambda x: -x.sell_gbp):
            print(f"{x.grade or '-':<6}{x.sell_gbp:>8.2f}{x.cash_gbp:>8.2f}{x.voucher_gbp:>9.2f}"
                  f"{len(x.stores):>8}{x.online_qty:>8}  {x.name[:50]}")
        n = len(r["stores"])
        print(f"\nUK stock: {'in ' + str(n) + ' store(s)' if n else 'in no store'}, "
              f"{r['online_qty']} online" + (f"  ({', '.join(r['stores'][:8])}"
                                              + (", …" if n > 8 else "") + ")" if n else ""))
        if r["price_move"]:
            print(r["price_move"])
        if r["category"]:
            print(f"category: {r['super_category']} / {r['category']}")
        if a.ask:
            w = floor_warning(a.ask, r["cash"])
            print(w or f"£{a.ask:.2f} is above CeX's £{r['cash']:.2f} cash offer.")
        print(f"checked {r['checked']}")
    if a.rejected and r["rejected"]:
        print("\nreturned by CeX but NOT this product:")
        for s, x in r["rejected"]:
            print(f"  {s:.2f}  £{x.sell_gbp:>7.2f}  {x.name[:60]}")
    # ⚠️ Absent is not zero: exit non-zero so a script can tell "no match" from "£0".
    return 0 if r["rows"] else 1


if __name__ == "__main__":
    sys.exit(main())
