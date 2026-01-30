# Changelog

All notable changes to deep-plan will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
