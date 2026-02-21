#!/bin/bash
# Test script for resolve_script_path function

set -e

# Define the resolve_script_path function (copied from SKILL.md)
resolve_script_path() {
  local script_rel_path="$1"  # e.g., "scripts/checks/validate-env.sh"
  local script_path=""

  # Strategy 1: Use CLAUDE_PLUGIN_ROOT (most reliable)
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    local candidate="$CLAUDE_PLUGIN_ROOT/$script_rel_path"
    if [ -f "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  fi

  # Strategy 2: Search from pwd (development fallback)
  local pwd_result="$(find "$(pwd)" -path "*/$script_rel_path" -type f 2>/dev/null | head -n1)"
  if [ -n "$pwd_result" ]; then
    # Warn if CLAUDE_PLUGIN_ROOT was set but didn't work
    if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
      echo "⚠️  Using workspace copy: $pwd_result (CLAUDE_PLUGIN_ROOT path not found)" >&2
    fi
    echo "$pwd_result"
    return 0
  fi

  # Strategy 3: Search from CLAUDE_PLUGIN_ROOT parent (edge case)
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    local plugin_root_result="$(find "$CLAUDE_PLUGIN_ROOT" -path "*/$script_rel_path" -type f 2>/dev/null | head -n1)"
    if [ -n "$plugin_root_result" ]; then
      echo "$plugin_root_result"
      return 0
    fi
  fi

  # Not found
  echo "ERROR: $script_rel_path not found" >&2
  echo "  CLAUDE_PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT:-<not set>}" >&2
  echo "  Current directory: $(pwd)" >&2
  echo "  This usually means the plugin isn't properly installed or loaded." >&2
  return 1
}

# Test 1: With CLAUDE_PLUGIN_ROOT set correctly
echo "Test 1: CLAUDE_PLUGIN_ROOT set correctly"
export CLAUDE_PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
result=$(resolve_script_path "scripts/checks/validate-env.sh")
if [ -f "$result" ]; then
  echo "✓ Found script via CLAUDE_PLUGIN_ROOT: $result"
else
  echo "✗ Failed to find script"
  exit 1
fi

# Test 2: Without CLAUDE_PLUGIN_ROOT (fallback to find)
echo -e "\nTest 2: Without CLAUDE_PLUGIN_ROOT (fallback)"
unset CLAUDE_PLUGIN_ROOT
cd "$(dirname "$0")/.."
result=$(resolve_script_path "scripts/checks/validate-env.sh")
if [ -f "$result" ]; then
  echo "✓ Found script via find fallback: $result"
else
  echo "✗ Failed to find script"
  exit 1
fi

# Test 3: Script not found
echo -e "\nTest 3: Script not found"
if resolve_script_path "nonexistent/script.sh" 2>/dev/null; then
  echo "✗ Should have failed but didn't"
  exit 1
else
  echo "✓ Correctly failed for nonexistent script"
fi

echo -e "\n✓ All tests passed!"
