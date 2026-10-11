# Setting up cex-uk-prices

Two minutes. There's nothing to install, no key and no account: it reads the same public search CeX's
website uses. The steps marked **CI checks this** run on a fresh Ubuntu machine every week by
[`setup-check`](../.github/workflows/setup-check.yml), and the weekly run also makes **one** live lookup,
so if CeX changes its search the badge goes red.

## What you need

| | |
|---|---|
| OS | anything with Python |
| Python | 3.10 or newer (CI runs 3.10 and 3.13). Standard library only. |
| Network | outbound HTTPS to `search.webuy.io`. UK results only. |

## 1. Install (CI checks this)

```bash
git clone https://github.com/casareanderson/cex-uk-prices && cd cex-uk-prices
python3 -m unittest discover -s tests -t .    # 17 tests, no network; ends with OK
python3 -m cexuk --help
```

## 2. First lookup (the weekly CI run checks this)

```bash
python3 -m cexuk "Sony WH-1000XM4"
```

Success is a one-line summary, a table with a row per grade (sell, cash, voucher, stores, online), the UK
stock line and `checked <date time>`. The exit code is **0 on a match and 1 on no match**, so a script can
tell "CeX doesn't have it" apart from "CeX pays £0".

Then the useful flags:

```bash
python3 -m cexuk "Sony WH-1000XM4" --ask 60         # is my asking price below CeX's cash offer?
python3 -m cexuk "Argon ONE M.2 case" --rejected    # what CeX returned that ISN'T your product
python3 -m cexuk "Sony WH-1000XM4" --json           # everything, machine-readable
python3 -m cexuk "Sony WH-1000XM4" --limit 10       # ask CeX for more rows (default 6)
```

## 3. Use it from Python

Put the repo folder on your `PYTHONPATH` (or copy the `cexuk` folder into your project), then:

```python
import cexuk

r = cexuk.lookup("Xiaomi Mi TV Box S 3rd Gen")
if r["rows"]:                       # a match
    print(r["sell"], r["cash"], r["voucher"], r["checked"])
else:                               # no match: there is no "cash" key at all
    print(r["note"])
```

Check for `rows` before reading prices. A failed request or a no-match has **no** `cash` key, on purpose,
so it can never be mistaken for £0.

## Settings

There are no environment variables or config files. The settings are module constants you can change
in your own copy:

| name | default | what it does |
|---|---|---|
| `client.UA` | names this project | the User-Agent. **Change it to name your program** if you build on this. |
| `client.MIN_INTERVAL` | `1.0` s | minimum gap between requests from one process |
| `client.TIMEOUT` | `20` s | request timeout |
| `client.ORIGIN` | `UK` | rows from any other origin are dropped |
| `match.MIN_MATCH` | `0.6` | score a row needs to count as your product (measured, see the README) |

## Read these before you trust a number

The README's "The traps" section has the eight that produced wrong answers in a real tool. The four that
matter most when you start:

1. **The search always answers, even for the wrong product.** That's what `--rejected` shows you.
   Long, specific queries do best.
2. **A cash price of £0 means "won't buy"**, not "worthless".
3. **Voucher isn't cash.** CeX pays more in credit than in money.
4. **The grade is part of the name.** Three rows for grades A, B and C are one product.

## Common errors

| you see | what's wrong |
|---|---|
| exit code 1 and a note, no table | no row scored 0.6 or above. Try a longer, more specific query, and look at `--rejected`. |
| `--rejected` shows your product just under 0.6 | the match gate is word overlap with a model-number veto. Add the exact model number to the query. |
| every lookup returns nothing, even for things CeX stocks | the network call failed (failures return no rows, never zeros), or CeX changed its search. Check the repo's setup-check badge: the weekly live lookup will be red too if it's CeX. |
| `ModuleNotFoundError: No module named 'cexuk'` | run it from the repo folder, or put that folder on `PYTHONPATH` |

## Etiquette

Not affiliated with CeX, and CeX's terms apply to you: read them before building on this. Keep it slow
(one request per lookup, at most one a second, no retries), name your program in the User-Agent, and if
the search ever stops answering an honest client, take that as the answer. Don't try to get round bot
protection.

## Updating and uninstalling

```bash
cd cex-uk-prices && git pull && python3 -m unittest discover -s tests -t .
```

To uninstall, delete the folder. It writes nothing anywhere else.

## What CI can't prove

Every week CI runs the 17 offline tests, loads the CLI and the Python API, and makes one live lookup to
check CeX's search still answers in the shape the code expects. It can't prove the prices are right for
your product, that the match gate picks the right row for every kind of item (it's been measured on
electronics, not games or films), or that CeX will keep this search open.
