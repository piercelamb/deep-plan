# Section Index Creation

Create `<planning_dir>/sections/index.md` to define implementation sections.

## Input Files

- `<planning_dir>/claude-plan.md` - implementation plan
- `<planning_dir>/claude-plan-tdd.md` - test stubs mirroring plan structure

## Output

```
<planning_dir>/sections/
└── index.md
```

## Required Blocks

index.md MUST contain two blocks at the top:

1. **PROJECT_CONFIG** - Project-level settings for implementation
2. **SECTION_MANIFEST** - List of section files to implement

---

## PROJECT_CONFIG Block

**index.md MUST start with a PROJECT_CONFIG block:**

```markdown
<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->
```

### PROJECT_CONFIG Fields

| Field | Required | Description | Examples |
|-------|----------|-------------|----------|
| `runtime` | Yes | Language and tooling | `python-uv`, `python-pip`, `typescript-npm`, `typescript-pnpm`, `rust-cargo`, `go` |
| `test_command` | Yes | Command to run tests | `uv run pytest`, `npm test`, `cargo test`, `go test ./...` |

### PROJECT_CONFIG Rules

- Must be at the TOP of index.md (before SECTION_MANIFEST)
- One field per line, format: `key: value`
- Keys are lowercase with underscores
- Values can contain spaces (e.g., `uv run pytest -v`)
- This block is parsed by setup scripts

### Common Runtime Values

| Runtime | Test Command |
|---------|--------------|
| `python-uv` | `uv run pytest` |
| `python-pip` | `pytest` or `python -m pytest` |
| `typescript-npm` | `npm test` |
| `typescript-pnpm` | `pnpm test` |
| `rust-cargo` | `cargo test` |
| `go` | `go test ./...` |

---

## SECTION_MANIFEST Block

**index.md MUST start with a SECTION_MANIFEST block:**

```markdown
<!-- SECTION_MANIFEST
section-01-foundation
section-02-config
section-03-parser
section-04-api
END_MANIFEST -->

# Implementation Sections Index

... rest of human-readable content ...
```

### SECTION_MANIFEST Rules

- Must be at the TOP of index.md (before any other content)
- One section per line, format: `section-NN-name` (e.g., `section-01-foundation`)
- Section numbers must be two digits with leading zero (01, 02, ... 12)
- Section names use lowercase with hyphens (no spaces or underscores)
- Numbers should be sequential (01, 02, 03...)
- This block is parsed by scripts - the rest of index.md is for humans

### Validation

Scripts parse the SECTION_MANIFEST block to:
- Track which sections are defined
- Detect completion progress
- Determine next section to write

If the manifest is invalid (missing, malformed, or has errors), `check-sections.py` returns `state: "invalid_index"` with error details.

## Human-Readable Content

After the manifest block, include:

### Dependency Graph

Table showing what blocks what:

```markdown
| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-foundation | - | section-02, section-03 | Yes |
| section-02-config | section-01 | section-04 | No |
| section-03-parser | section-01 | section-04 | Yes |
| section-04-api | section-02, section-03 | - | No |
```

### Execution Order

Which sections can run in parallel:

```markdown
1. section-01-foundation (no dependencies)
2. section-02-config, section-03-parser (parallel after section-01)
3. section-04-api (requires section-02 AND section-03)
```

### Section Summaries

Brief description of each section:

```markdown
### section-01-foundation
Initial project setup and configuration.

### section-02-config
Configuration loading and validation.
```

## Guidelines

- **Natural boundaries**: Split by component, layer, feature, or phase
- **Focused sections**: One logical unit of work each
- **Parallelization**: Consider which sections can run independently
- **Dependency direction**: Earlier sections should not depend on later sections

## Example index.md

```markdown
<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-foundation
section-02-core-libs
section-03-env-validation
section-04-llm-clients
section-05-skill-orchestrator
section-06-integration
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-foundation | - | all | Yes |
| section-02-core-libs | 01 | 03, 04 | No |
| section-03-env-validation | 02 | 05 | Yes |
| section-04-llm-clients | 02 | 05 | Yes |
| section-05-skill-orchestrator | 03, 04 | 06 | No |
| section-06-integration | 05 | - | No |

## Execution Order

1. section-01-foundation (no dependencies)
2. section-02-core-libs (after 01)
3. section-03-env-validation, section-04-llm-clients (parallel after 02)
4. section-05-skill-orchestrator (after 03 AND 04)
5. section-06-integration (final)

## Section Summaries

### section-01-foundation
Directory structure, config files, test fixtures.

### section-02-core-libs
Config loader, prompt utilities.

### section-03-env-validation
Environment checks, context estimation.

### section-04-llm-clients
Gemini and ChatGPT API clients.

### section-05-skill-orchestrator
Main skill file and orchestration agent.

### section-06-integration
End-to-end integration tests.
```
