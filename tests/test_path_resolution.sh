#!/bin/bash
# Test script for resolve_script_path function

set -euo pipefail

# Define the resolve_script_path function (copied from SKILL.md)
resolve_script_path() {
  local script_rel_path="$1"  # e.g., "scripts/checks/validate-env.sh"

  # Strategy 1: Use CLAUDE_PLUGIN_ROOT (official + most reliable)
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    local candidate="$CLAUDE_PLUGIN_ROOT/$script_rel_path"
    if [ -f "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  fi

  # Strategy 2: Search known Claude plugin install/cache roots
  local root
  for root in "$HOME/.claude/plugins/cache" "$HOME/.claude/plugins"; do
    if [ -d "$root" ]; then
      local installed_result
      installed_result="$(find "$root" -path "*/deep-plan/*/$script_rel_path" -type f 2>/dev/null | sort | head -n1)"
      if [ -n "$installed_result" ]; then
        echo "$installed_result"
        return 0
      fi
    fi
  done

  # Strategy 3: Search from pwd (development fallback)
  local pwd_result
  pwd_result="$(find "$(pwd)" -path "*/$script_rel_path" -type f 2>/dev/null | head -n1)"
  if [ -n "$pwd_result" ]; then
    echo "$pwd_result"
    return 0
  fi

  # Not found
  echo "ERROR: $script_rel_path not found" >&2
  echo "  CLAUDE_PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT:-<not set>}" >&2
  echo "  Current directory: $(pwd)" >&2
  echo "  Attempted roots:" >&2
  echo "    - ${CLAUDE_PLUGIN_ROOT:-<unset>}" >&2
  echo "    - $HOME/.claude/plugins/cache" >&2
  echo "    - $HOME/.claude/plugins" >&2
  echo "    - $(pwd)" >&2
  echo "  Next steps:" >&2
  echo "    - Reinstall plugin: /plugin install deep-plan" >&2
  echo "    - Or run with local plugin: claude --plugin-dir /path/to/deep-plan" >&2
  return 1
}

ORIG_HOME="$HOME"
TMP_HOME="$(mktemp -d)"
TMP_WORKSPACE="$(mktemp -d)"

cleanup() {
  export HOME="$ORIG_HOME"
  rm -rf "$TMP_HOME" "$TMP_WORKSPACE"
}
trap cleanup EXIT

# Test 1: With CLAUDE_PLUGIN_ROOT set correctly
echo "Test 1: CLAUDE_PLUGIN_ROOT set correctly"
export CLAUDE_PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
result="$(resolve_script_path "scripts/checks/validate-env.sh")"
if [ -f "$result" ]; then
  echo "✓ Found script via CLAUDE_PLUGIN_ROOT: $result"
else
  echo "✗ Failed to find script"
  exit 1
fi

# Test 2: Without CLAUDE_PLUGIN_ROOT (installed cache fallback)
echo -e "\nTest 2: Without CLAUDE_PLUGIN_ROOT (installed cache fallback)"
unset CLAUDE_PLUGIN_ROOT
export HOME="$TMP_HOME"
installed_script="$HOME/.claude/plugins/cache/mock-market/deep-plan/0.0.0/scripts/checks/validate-env.sh"
mkdir -p "$(dirname "$installed_script")"
printf '#!/bin/bash\n' > "$installed_script"
chmod +x "$installed_script"
cd "$TMP_WORKSPACE"
result="$(resolve_script_path "scripts/checks/validate-env.sh")"
if [ "$result" = "$installed_script" ]; then
  echo "✓ Found script via installed cache fallback: $result"
else
  echo "✗ Expected installed cache fallback path"
  echo "  expected: $installed_script"
  echo "  got: $result"
  exit 1
fi

# Test 3: Without CLAUDE_PLUGIN_ROOT and without installed roots (pwd fallback)
echo -e "\nTest 3: Without CLAUDE_PLUGIN_ROOT and installed roots (pwd fallback)"
rm -rf "$HOME/.claude/plugins/cache" "$HOME/.claude/plugins"
local_script="$TMP_WORKSPACE/local/scripts/checks/validate-env.sh"
mkdir -p "$(dirname "$local_script")"
printf '#!/bin/bash\n' > "$local_script"
cd "$TMP_WORKSPACE/local"
result="$(resolve_script_path "scripts/checks/validate-env.sh")"
if [ "$result" = "$local_script" ]; then
  echo "✓ Found script via pwd fallback: $result"
else
  echo "✗ Expected pwd fallback path"
  echo "  expected: $local_script"
  echo "  got: $result"
  exit 1
fi

# Test 4: Script not found
echo -e "\nTest 4: Script not found"
rm -f "$local_script"
if resolve_script_path "nonexistent/script.sh" 2>/dev/null; then
  echo "✗ Should have failed but didn't"
  exit 1
else
  echo "✓ Correctly failed for nonexistent script"
fi

echo -e "\n✓ All tests passed!"
