"""Is the row CeX returned the product you asked about?

CeX's search is an Algolia index: fuzzy, and it ALWAYS returns something. Asked
about a product it does not stock, it answers confidently with a different one.
Measured on 2026-09-12:

    "Raspberry Pi Argon ONE with SSD"   -> Raspberry Pi 500+           (cash £136)
    "Argon ONE M.2 case"                -> "Hercule Poirot - The First
                                           Cases" (a DVD), JBL headphones
    "Casio FX-CG50 Graphing Calculator" -> FX-CG20 / FX-CG500 / FX-CG10

So every row is scored against the query before any number is believed.
"""
from __future__ import annotations

import re

# ⭐ MEASURED, not chosen. Genuine matches scored 0.62 (Google Nest Mini),
# 0.67 (Sony WH-1000XM4) and 0.86 (Xiaomi TV Box 3rd Gen); every wrong product
# topped out at 0.50. 0.6 sits in that gap.
MIN_MATCH = 0.6

_NOISE = {
    "the", "and", "for", "with", "new", "used", "genuine", "original", "free",
    "fast", "same", "day", "dispatch", "uk", "gb", "official", "boxed", "set",
    "compatible", "scientific", "quality", "great", "excellent", "condition",
    "unit", "item", "only", "inc", "vat", "postage", "delivery", "sale",
}

# A token that looks like a model designation: contains a digit, or is a short
# suffix like "ti" / "xl" / "se". These ARE the product; the rest is category
# and marketing.
_MODELISH = re.compile(r"^(?=.*\d)[a-z0-9-]{2,}$|^(ti|xl|se|xs|pro|max|mini|plus)$")


def _tokens(text: str) -> set[str]:
    """⚠️ Two-character tokens are kept. Dropping them threw away the only word
    that separates "RTX 3060 Ti" from a plain RTX 3060."""
    return {w.strip(".,()[]/-").lower() for w in (text or "").split()
            if len(w.strip(".,()[]/-")) >= 2}


def match_score(query: str, title: str) -> float:
    """Fraction of the query's meaningful words that the title carries, with
    every model-ish token required.

    ⚠️ The model number is a VETO, not one vote among five. Measured false
    positives on plain word overlap:
      "RTX 3060 Ti" matched a plain RTX 3060 at 1.00
      "Nest Mini"   matched "Nest Audio" at 0.67
      "WH-1000XM5"  matched WH-1000XM3 at 0.75
    ⚠️ But not every word is required: sellers' adjectives ("scientific",
    "compatible") appear in no shop title, and an AND across all of them
    matches nothing.
    """
    q = _tokens(query) - _NOISE
    if not q:
        return 0.0
    t = _tokens(title)
    want = {w for w in q if _MODELISH.match(w)}
    if want and not want.issubset(t):
        return 0.0
    return len(q & t) / len(q)
