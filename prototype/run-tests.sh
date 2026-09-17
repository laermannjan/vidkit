#!/usr/bin/env bash
# Runs every suite. Serves the fixtures the tests need, and cleans up after.
set -uo pipefail
cd "$(dirname "$0")"

python3 -m http.server 8777 --bind 127.0.0.1 -d site >/dev/null 2>&1 &
SITE=$!
python3 -m http.server 8778 --bind 127.0.0.1 -d cdn  >/dev/null 2>&1 &
CDN=$!
trap 'kill $SITE $CDN 2>/dev/null' EXIT

for i in $(seq 20); do
  curl -sf -o /dev/null http://127.0.0.1:8777/day1.html && break
  sleep 0.25
done

fail=0
for t in smoke multi_test suggest_test edit_test; do
  out=$(./$t.py 2>&1)
  p=$(grep -cE '^  PASS' <<<"$out"); f=$(grep -cE '^  FAIL' <<<"$out")
  printf "  %-13s %2d pass  %d fail\n" "$t" "$p" "$f"
  [ "$f" -gt 0 ] && { fail=1; grep -E '^  FAIL' <<<"$out" | sed 's/^/    /'; }
done
[ $fail -eq 0 ] && echo "  all green" || echo "  FAILURES"
exit $fail
