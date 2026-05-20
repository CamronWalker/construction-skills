#!/usr/bin/env bash
# Smoke tests for .githooks/pre-commit. Exercises three cases:
#   1. plugin file changed + bumps present  → pass
#   2. plugin file changed + no bumps + version not -dev → fail
#   3. plugin file changed + no bumps + version contains -dev → pass (exemption)
set -e

REPO=$(mktemp -d)
trap "rm -rf $REPO" EXIT
cd "$REPO"
git init -q
mkdir -p .claude-plugin scheduling/.claude-plugin scheduling/skills .githooks
cp "$OLDPWD/.githooks/pre-commit" .githooks/
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit

# Seed initial commit (pretty-printed JSON to match real repo format and hook's grep pattern)
cat > .claude-plugin/marketplace.json <<'EOF'
{
  "version": "0.1.0",
  "plugins": [
    {
      "name": "scheduling",
      "source": "./scheduling",
      "version": "0.1.0"
    }
  ]
}
EOF
cat > scheduling/.claude-plugin/plugin.json <<'EOF'
{
  "name": "scheduling",
  "version": "0.1.0"
}
EOF
echo "# placeholder" > scheduling/skills/foo.md
git add -A
git commit -q -m "seed" --no-verify

passes=0
fails=0
assert() { if [ "$1" = "$2" ]; then echo "  PASS: $3"; passes=$((passes+1)); else echo "  FAIL: $3 (got $1, expected $2)"; fails=$((fails+1)); fi; }

# Case 1: plugin file changed + bumps present
echo "# placeholder v2" > scheduling/skills/foo.md
cat > scheduling/.claude-plugin/plugin.json <<'EOF'
{
  "name": "scheduling",
  "version": "0.2.0"
}
EOF
cat > .claude-plugin/marketplace.json <<'EOF'
{
  "version": "0.2.0",
  "plugins": [
    {
      "name": "scheduling",
      "source": "./scheduling",
      "version": "0.2.0"
    }
  ]
}
EOF
git add -A
if git commit -q -m "case1" 2>/dev/null; then
  assert "0" "0" "Case 1 (plugin change + bumps): allowed"
else
  assert "1" "0" "Case 1 (plugin change + bumps): allowed"
fi

# Case 2: plugin file changed + no bumps + version not -dev
echo "# placeholder v2.1" > scheduling/skills/foo.md
git add -A
if git commit -q -m "case2" 2>/dev/null; then
  assert "1" "0" "Case 2 (plugin change + no bumps): denied"
else
  assert "0" "0" "Case 2 (plugin change + no bumps): denied"
fi
git restore --staged scheduling/skills/foo.md
git checkout -- scheduling/skills/foo.md

# Case 3: bump to -dev, then commit a follow-up without further bump
cat > scheduling/.claude-plugin/plugin.json <<'EOF'
{
  "name": "scheduling",
  "version": "1.0.0-dev"
}
EOF
cat > .claude-plugin/marketplace.json <<'EOF'
{
  "version": "1.0.0-dev",
  "plugins": [
    {
      "name": "scheduling",
      "source": "./scheduling",
      "version": "1.0.0-dev"
    }
  ]
}
EOF
git add -A
git commit -q -m "bump to dev" --no-verify
echo "# placeholder v3" > scheduling/skills/foo.md
git add -A
if git commit -q -m "case3" 2>/dev/null; then
  assert "0" "0" "Case 3 (-dev exemption): allowed without bump"
else
  assert "1" "0" "Case 3 (-dev exemption): allowed without bump"
fi

echo
echo "$passes passed, $fails failed"
[ "$fails" -eq 0 ]
