# Context Check Protocol

Before critical operations, optionally prompt the user about context management.

## Key Insight

**File-based recovery is the real resilience mechanism, not compaction.**

- `scan_planning_files()` detects what's been created
- `infer_resume_step()` determines where to resume
- SKILL.md is freshly loaded on re-run
- Tasks get reconciled from file state

Compaction keeps the session alive but may cause instruction loss. `/clear` + re-run gives a clean slate with full instructions.

## Quick Check: Context Task

After step 4 (setup-planning-session), look for the context task:
```
review_mode=external_llm (or other value)
```

Check session config for `context_check_enabled`. If `false`, skip context checks entirely.

## Running the Script

If context checks are enabled (or you're unsure), run:

```bash
uv run {plugin_root}/scripts/checks/check-context-decision.py \
  --planning-dir "<planning_dir>" \
  --upcoming-operation "<operation_name>"
```

## Handling Script Output

| action | What to do |
|--------|------------|
| `skip` | Prompts disabled - proceed immediately |
| `prompt` | Use AskUserQuestion with `prompt.message` and `prompt.options` |

### Option Handling

**If user chooses "Continue":**
- Proceed with the operation
- Auto-compact will trigger at ~95% context if needed
- If Claude gets confused after auto-compact, user can `/clear` and re-run

**If user chooses "/clear + re-run":**
- User will run `/clear` then re-run `/deep-plan @<spec-file>`
- This gives a fresh context window with full instructions
- Progress is preserved - file-based recovery resumes where they left off

## Trade-offs Explained

| Option | Benefit | Trade-off |
|--------|---------|-----------|
| Continue | No interruption | May hit auto-compact later |
| /clear + re-run | Fresh context, full instructions | Loses conversation history |

**Why we don't recommend manual /compact:**
- Same instruction-loss risk as auto-compact
- No additional benefit over letting auto-compact happen naturally
- If you're going to interrupt, `/clear` + re-run is cleaner

## When to Run Context Checks

- Before External LLM Review (upcoming operation: "External LLM Review")
- Before Section Split (upcoming operation: "Section splitting")

## Configuration

In `config.json`:
```json
{
  "context": {
    "check_enabled": true
  }
}
```

Set `check_enabled` to `false` to skip all context prompts.
