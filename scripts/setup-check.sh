#!/usr/bin/env bash
# Runs docs/SETUP.md. Offline by default. With CEXUK_LIVE=1 it also makes ONE real lookup against
# CeX's public search (the weekly CI run does this, so a change at CeX shows up as a red badge).
# Used by .github/workflows/setup-check.yml. Run it locally from the repo root too.
set -euo pipefail
step() { printf '\n== %s\n' "$*"; }

step "1. offline tests (nothing to install)"
python3 -m unittest discover -s tests -t . 2>&1 | tail -3

step "1. CLI loads"
python3 -m cexuk --help >/dev/null && echo ok

step "1. the Python API imports"
python3 -c "import cexuk; assert callable(cexuk.lookup) and callable(cexuk.search); print('lookup, search ok')"

if [ "${CEXUK_LIVE:-0}" = 1 ]; then
  step "2. one live lookup against CeX UK"
  set +e; out=$(python3 -m cexuk "Sony WH-1000XM4" --json); rc=$?; set -e
  python3 -c "
import json, sys
d = json.loads(sys.argv[1]); rc = int(sys.argv[2])
assert rc == 0 and d['rows'], 'no matching rows (rc=%s): %s' % (rc, d.get('note'))
assert d['sell'] > 0 and 'checked' in d, d
print('%d rows, sells £%.2f, cash £%.2f, voucher £%.2f, checked %s' % (len(d['rows']), d['sell'], d['cash'], d['voucher'], d['checked']))
" "$out" "$rc"
else
  step "2. live lookup skipped (set CEXUK_LIVE=1 to make one real request)"
fi

printf '\nSETUP CHECK PASSED\n'
