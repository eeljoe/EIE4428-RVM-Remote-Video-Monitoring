#!/usr/bin/env bash
# 08 r1 verifier mutation probe: drop the backslash half of the path-separator
# check in validated_face_name; expect the hostile-name tests to go red, then
# restore and prove the sha1 returns. Usage: bash <this> <worktree> <python>
set -u
WT="$1"; PY="$2"
cd "$WT" || exit 9
F=src/rvm/server/session.py
BEFORE=$("$PY" -c "import hashlib;print(hashlib.sha1(open('$F','rb').read()).hexdigest())")
"$PY" -c "p='$F';s=open(p,encoding='utf-8').read();old='if \"/\" in cleaned or \"'+chr(92)*2+'\" in cleaned:';assert old in s,'find failed';open(p,'w',encoding='utf-8').write(s.replace(old,'if \"/\" in cleaned:'))" || exit 9
echo "MUTATED line:"; grep -n '"/" in cleaned' "$F" | head -2
"$PY" -m pytest tests/test_face_api.py -q -k "could_never_be_deleted or can_be_deleted_again"
TEST_EXIT=$?
git checkout "$F" >/dev/null 2>&1
AFTER=$("$PY" -c "import hashlib;print(hashlib.sha1(open('$F','rb').read()).hexdigest())")
echo "SHA1 before=$BEFORE after=$AFTER match=$([ "$BEFORE" = "$AFTER" ] && echo yes || echo NO)"
echo "MUTANT_TEST_EXIT=$TEST_EXIT (expect nonzero=red)"
[ "$BEFORE" = "$AFTER" ] && [ "$TEST_EXIT" -ne 0 ]
