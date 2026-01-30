# External Review Protocol

This step sends `claude-plan.md` for independent review. The review mode determines how the review is performed.

## Review Modes

Check `review_mode` from task context (e.g., `review_mode=opus_subagent`).

| Mode | When Used | Action |
|------|-----------|--------|
| `external_llm` | External LLMs configured (default) | Run review.py |
| `opus_subagent` | No external LLMs, user chose Opus | Launch subagent |
| `skip` | User chose to skip review | Skip to step 16 |

---

## Mode: external_llm (Default)

Run unified review script:
```bash
uv run --directory {plugin_root} scripts/llm_clients/review.py --planning-dir "{planning_dir}"
```

The script automatically:
- Detects which LLMs are available (Gemini, OpenAI, or both)
- Runs available reviewers in parallel (if both) or single-threaded (if one)
- Writes results to `{planning_dir}/reviews/`

### Output Format

The script returns JSON:
```json
{
  "reviews": {
    "gemini": {"success": true, "provider": "gemini", "model": "...", "analysis": "..."},
    "openai": {"success": true, "provider": "openai", "model": "...", "analysis": "..."}
  },
  "files_written": ["reviews/iteration-1-gemini.md", "reviews/iteration-1-openai.md"],
  "gemini_available": true,
  "openai_available": true
}
```

### Handling Failures

- If one LLM fails, the other still runs
- Script exits 0 if at least one review succeeds, 1 if all fail

---

## Mode: opus_subagent

Print status:
```
═══════════════════════════════════════════════════════════════
STEP 13/22: OPUS PLAN REVIEW
═══════════════════════════════════════════════════════════════
Launching Claude Opus subagent for plan review...
```

**Steps:**

1. Launch subagent (passes file path, not content):
```
Task(
  subagent_type: "opus-plan-reviewer",
  model: "opus",
  prompt: "Review the implementation plan at: {planning_dir}/claude-plan.md"
)
```

2. Create reviews directory if needed:
```bash
mkdir -p "{planning_dir}/reviews"
```

3. Write subagent output to `{planning_dir}/reviews/iteration-1-opus.md`:
```markdown
# Opus Review

**Model:** claude-opus-4
**Generated:** {ISO timestamp}

---

{subagent_output}
```

4. Proceed to step 14 (integrate feedback)

---

## Mode: skip

Print status:
```
═══════════════════════════════════════════════════════════════
STEP 13/22: EXTERNAL REVIEW - SKIPPED
═══════════════════════════════════════════════════════════════
External review skipped per user choice.
Proceeding to TDD planning.
───────────────────────────────────────────────────────────────
```

Skip directly to step 16 (TDD approach). Steps 14-15 are not applicable.

---

## Output Location

All modes write to `{planning_dir}/reviews/`:
- `iteration-1-gemini.md` - Gemini review (external_llm mode)
- `iteration-1-openai.md` - OpenAI review (external_llm mode)
- `iteration-1-opus.md` - Opus review (opus_subagent mode)
