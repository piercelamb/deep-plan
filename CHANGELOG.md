# Changelog

All notable changes to deep-plan will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.2] - 2026-02-28

### Fixed
- **Plugin root discovery** — SessionStart hook now injects `DEEP_PLUGIN_ROOT` into Claude's context via `additionalContext`, eliminating slow `find` commands for script discovery. Falls back to filename-based search that works with both hyphen and underscore directory naming (fixes marketplace install path mismatch). ([piercelamb/deep-project#3](https://github.com/piercelamb/deep-project/issues/3))

## [0.3.1] - 2026-02-11

### Fixed
- **Section file race condition** — SubagentStop hook now waits for transcript JSONL to finish writing before reading it. Previously, 64% of section files contained garbage because Claude Code fires the hook before the final transcript entries are flushed to disk. The fix polls file size stability (200ms threshold) before reading, with a 5s timeout fallback.

## [0.3.0] - 2026-01-30

### Changed
- **Unified session ID** - Changed `DEEP_PLAN_SESSION_ID` to shared `DEEP_SESSION_ID`
- **Normalized env var** - Changed `CLAUDE_SESSION_ID` to `DEEP_SESSION_ID` in env file writes and all scripts
- SessionStart hook now checks if `DEEP_SESSION_ID` already matches before outputting
- Prevents duplicate output when multiple deep-* plugins run together

## [0.2.0] - 2026-01-30

### Added
- **Parallel section writing** - Sections now written by concurrent `section-writer` subagents (batch size: 7)
- **No external LLMs mode** - Can run with Opus subagent for plan review instead of Gemini/OpenAI
- **SessionStart hook** - Captures session_id reliably via `additionalContext`
- **SubagentStop hook** - Automatically writes section files from subagent output
- New agent definitions: `section-writer.md`, `opus-plan-reviewer.md`
- Batch task generation script: `scripts/checks/generate-batch-tasks.py`
- Transcript parsing utilities: `scripts/lib/transcript_parser.py`, `scripts/lib/transcript_validator.py`
- New reference document: `plan-writing.md`

### Changed
- **TODOs to Tasks** - Migrated to native Claude Code Tasks with dependency tracking
- Tasks written directly to `~/.claude/tasks/` for deterministic state
- Section subagents no longer need Write tool access (more secure via hook capture)
- Updated `section-splitting.md` for parallel subagent batch loop
- Updated `external-review.md` with three review mode paths (external_llm, opus_subagent, skip)
- Updated `section-index.md` for task-based generation
- Updated `context-check.md` for new task system

### Removed
- Legacy `TodoWrite` system (`scripts/lib/todos.py`)
- `generate-section-todos.py` script
- `tests/test_generate_section_todos.py`

## [0.1.0] - 2025-01-01

### Added
- Initial release
- Complete planning workflow: Research -> Interview -> External Review -> TDD Plan
- Section splitting with index generation
- External LLM review via Gemini and OpenAI
- Context check system for token management
- File-based session resumption
