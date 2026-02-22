![deep-plan hero](assets/hero.jpeg)

# /deep-plan, a Claude Code plugin

![Version](https://img.shields.io/badge/version-0.3.1-blue)
![Status](https://img.shields.io/badge/status-beta-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

> **Blog posts:**
> - [Building /deep-plan](https://pierce-lamb.medium.com/building-deep-plan-a-claude-code-plugin-for-comprehensive-planning-30e0921eb841) - The story behind this plugin
> - [The Deep Trilogy](https://pierce-lamb.medium.com/the-deep-trilogy-claude-code-plugins-for-writing-good-software-fast-33b76f2a022d) - How the three plugins work together
> - [What I Learned](https://pierce-lamb.medium.com/what-i-learned-while-building-a-trilogy-of-claude-code-plugins-72121823172b) - Technical lessons from plugin development

`/deep-plan` transforms vague feature requests into detailed, production-ready implementation plans through AI-assisted research, stakeholder interviews, and multi-LLM review.

[`/deep-implement`](https://github.com/piercelamb/deep-implement), its companion plugin, takes these section files and implements them with TDD methodology, integrated code review, and atomic commits.

For large projects with broad, vague requirements, use [`/deep-project`](https://github.com/piercelamb/deep-project) first to decompose into focused planning units before running `/deep-plan` on each.

This plugin started as an effort to automate the most time-intensive part of my Claude Code workflow that I had previously been doing manually. It is primarily targeted at Claude Code users that don't have strict token constraints and prefer deep planning/plan review before implementation. It's designed to speed up creating production-ready code within Claude Code without sacrificing an understanding of how it works.

## TL;DR
```
/plugin marketplace add piercelamb/deep-plan
/plugin install deep-plan
/plugin enable deep-plan
/deep-plan @planning/auth-spec.md
```

## Table of Contents

- [Overview](#overview)
- [The Deep Trilogy](#the-deep-trilogy)
- [Why deep-plan?](#why-deep-plan)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
- [Workflow Steps](#workflow-steps)
- [Output Files](#output-files)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Requirements](#requirements)
- [Best Practices](#best-practices)
- [Security & Privacy](#security--privacy)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Changelog](#changelog)

## Overview

**deep-plan** orchestrates a comprehensive planning workflow that ensures you think through implementation details *before* writing code:

```
Research → Interview → External LLM Review → TDD Plan → Section Splitting
```

The plugin guides you through:
- **Research Phase**: Analyze existing codebases and research the web for current best practices
- **Interview Phase**: Structured Q&A to surface hidden requirements and edge cases
- **External Review**: Independent feedback from Gemini, OpenAI, or an Opus subagent on your plan
- **TDD Phase**: Define test stubs before implementation
- **Section Phase**: Split into parallelizable, self-contained implementation units (written in parallel via subagents)

By the end, you have a complete planning directory with specs, research, reviews, and small, isolated implementation sections that any engineer (or Claude) can pick up cold.

## The Deep Trilogy

This plugin is part of a three-plugin pipeline for turning ideas into production code:

```
/deep-project (decompose) → /deep-plan (plan) → /deep-implement (build)
```

```
┌───────────────────────────────────────────────────────────────────┐
│                        THE DEEP TRILOGY                           │
│                From Vague Idea to Production Code                 │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│         "I want to build a SaaS platform"                         │
│                        │                                          │
│                        ▼                                          │
│      ┌─────────────────────────────────────┐                      │
│      │            /deep-project            │                      │
│      └─────────────────────────────────────┘                      │
│           │            │            │                             │
│           ▼            ▼            ▼                             │
│      ┌─────────┐  ┌─────────┐  ┌─────────┐                        │
│      │ 01-auth │  │ 02-bill │  │   ...   │                        │
│      │ spec.md │  │ spec.md │  │         │                        │
│      └─────────┘  └─────────┘  └─────────┘                        │
│           │            │            │                             │
│           ▼            ▼            ▼                             │
│      ┌─────────┐  ┌─────────┐  ┌─────────┐                        │
│      │ /deep-  │  │ /deep-  │  │   ...   │  ◀── YOU ARE HERE      │
│      │  plan   │  │  plan   │  │         │                        │
│      └─────────┘  └─────────┘  └─────────┘                        │
│         │   │       │ │ │           │                             │
│         ▼   ▼       ▼ ▼ ▼           ▼                             │
│      ┌────┐┌────┐┌────┐┌────┐┌────┐┌─────────┐                    │
│      │ 01 ││ 02 ││ 01 ││ 02 ││ 03 ││   ...   │                    │
│      └────┘└────┘└────┘└────┘└────┘└─────────┘                    │
│        │    │     │     │    │          │                         │
│        └─┬──┘     └──┬──┴────┘          │                         │
│          │           │                  │                         │
│          ▼           ▼                  ▼                         │
│      ┌─────────┐┌─────────┐        ┌─────────┐                    │
│      │ /deep-  ││ /deep-  │        │   ...   │                    │
│      │implement││implement│        │         │                    │
│      └─────────┘└─────────┘        └─────────┘                    │
│           │          │                  │                         │
│           ▼          ▼                  ▼                         │
│      ┌─────────┐┌─────────┐        ┌─────────┐                    │
│      │  auth   ││ billing │        │   ...   │                    │
│      │  code   ││  code   │        │         │                    │
│      └─────────┘└─────────┘        └─────────┘                    │
│           │          │                  │                         │
│           └──────────┴──────────────────┘                         │
│                          │                                        │
│                          ▼                                        │
│                 Production Codebase                               │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

| Plugin | Purpose | Input | Output |
|--------|---------|-------|--------|
| [`/deep-project`](https://github.com/piercelamb/deep-project) | Decompose | Vague requirements | Focused spec files |
| [`/deep-plan`](https://github.com/piercelamb/deep-plan) | Plan | Spec file | Section files with TDD |
| [`/deep-implement`](https://github.com/piercelamb/deep-implement) | Build | Section files | Production code |

**Where to start?**
- **Vague multi-component project?** Start with [`/deep-project`](https://github.com/piercelamb/deep-project)
- **Single focused feature?** Start here with `/deep-plan`
- **Already have section files?** Skip to [`/deep-implement`](https://github.com/piercelamb/deep-implement)

## Why deep-plan?

### Without deep-plan
```
You: "Claude, build me an auth system"
Claude: *immediately starts coding*
Result: Multiple iterations, missed requirements, rework
```

### With deep-plan
```
You: "/deep-plan @planning/auth-spec.md"
deep-plan: Research → Interview → External Review → TDD Plan → Sections
Result: Complete implementation plan reviewed by multiple LLMs, split into chunks that keep the context window monsters at bay
```

**Time Investment**: ~30 minutes of interview + review
**Time Saved**: Hours of rework and missed requirements

## When to Use

**Use deep-plan when:**
- You want to maintain a mental model of what's being created
- Requirements are vague and need fleshing out
- You want external validation before investing implementation time
- The feature is complex enough to benefit from deep planning

**Skip deep-plan when:**
- Simple bug fixes or one-file changes
- Requirements are already crystal clear
- Time pressure prevents thorough planning
- You are ready to open the Ralph Wiggum flood gates

## Quick Start

> **TL;DR**: Create a spec file, run the command, answer questions.

**1. Create a spec file:**

*Option A: Use your editor* — Create `planning/auth-spec.md` with your feature description.

*Option B: Command line:*
```bash
mkdir -p planning
cat > planning/auth-spec.md << 'EOF'
# Authentication Feature
Add OAuth2 login with Google and GitHub providers.
Store sessions in Redis. Use JWT for API authentication.
EOF
```

Spec files can be as dense or as sparse as you like. I've used `/deep-plan` with a few bullet points and also used it with structured, thorough documents.

**2. Run deep-plan:**
```
/deep-plan @planning/auth-spec.md
```

**3. Follow the prompts** through Research → Interview → Review → Output

That's it. Your planning directory will contain a complete implementation plan with TDD stubs and parallelizable sections.

> **Token & Cost Note**: This workflow is token-intensive (research, multi-turn interview, review). Run `/compact` before starting. If using external LLM reviews (Gemini/OpenAI), those will incur API costs on your accounts.

If you /compact or exit in the middle, `/deep-plan` can recover from the existing files.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        deep-plan workflow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   /deep-plan @spec.md                                           │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│   │   Research   │ ──▶ │  Interview   │ ──▶ │    Spec      │    │
│   │  (optional)  │     │  (5-10 Q&A)  │     │  Synthesis   │    │
│   └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                   │             │
│                                                   ▼             │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│   │   Section    │ ◀── │   TDD Plan   │ ◀── │   External   │    │
│   │  Splitting   │     │  Generation  │     │  LLM Review  │    │
│   └──────────────┘     └──────────────┘     └──────────────┘    │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  sections/section-01-*.md  sections/section-02-*.md ...  │  │
│   │  (Self-contained, parallel-ready implementation units)   │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.11+
- (Optional) External LLM API key for review:
  - **Gemini**: `GEMINI_API_KEY` ([get one](https://aistudio.google.com/apikey)) or Google Cloud ADC credentials
  - **OpenAI**: `OPENAI_API_KEY` ([get one](https://platform.openai.com/api-keys))
  - If no external keys configured, review can be performed via Opus subagent

### Install via Marketplace (Recommended)

**Option A: CLI commands**
```
/plugin marketplace add piercelamb/deep-plan
/plugin install deep-plan
/plugin enable deep-plan
```

**Option B: Via UI**
```
/plugin marketplace add piercelamb/deep-plan
/plugin install deep-plan
/plugins
```
Then scroll to "Installed", find `deep-plan`, and click "Enable".

### Manual Installation

**Option A: Via settings.json**

Clone the repo, then add to your project's `.claude/settings.json`:
```bash
git clone https://github.com/piercelamb/deep-plan.git /path/to/deep-plan
```

```json
{
  "plugins": {
    "paths": ["/path/to/deep-plan"]
  }
}
```

**Option B: Via --plugin-dir flag (development/testing)**

```bash
git clone https://github.com/piercelamb/deep-plan.git /path/to/deep-plan
claude --plugin-dir /path/to/deep-plan
```

### Configure API Keys (Optional)

For external LLM review via Gemini or OpenAI, set API keys. See [Environment Variables](#environment-variables) for all options.

```bash
export OPENAI_API_KEY="your-key"    # For OpenAI/ChatGPT
export GEMINI_API_KEY="your-key"    # For Gemini
```

The plugin also supports Application Default Credentials (ADC) for Gemini. If you use ADC, you'll need to set `GOOGLE_CLOUD_LOCATION` or set your project's location in the plugin's `config.json` file.

If no external LLM keys are configured, the plugin can perform review via an Opus subagent instead.

The plugin validates your configuration when `/deep-plan` first runs.  

## Usage

### Basic Invocation

```
/deep-plan @path/to/your-spec.md
```

The spec file can be as detailed or vague as you like. The planning directory is inferred from the spec file's parent directory.

### Resuming

If the workflow is interrupted (context limit, user pause), follow Claude's instructions or simply re-run with the same spec file:

```
/deep-plan @planning/auth-spec.md
```

The plugin detects existing artifacts and resumes from the appropriate step.

## Workflow Steps

The plugin runs a multi-phase workflow:

| Phase | What Happens |
|-------|--------------|
| **Setup** | Validate environment, check spec file, initialize session |
| **Research** | Codebase exploration, web research (optional, based on your choices) |
| **Interview** | Structured Q&A to clarify requirements |
| **Planning** | Synthesize spec, generate implementation plan |
| **Review** | External LLM review (Gemini/OpenAI or Opus subagent), integrate feedback, user review |
| **TDD** | Generate test stubs mirroring plan structure |
| **Sections** | Split into implementation sections, generate files in parallel via subagents |

## Output Files

After running deep-plan, your planning directory contains:

```
planning/
├── your-spec.md                 # Your original input
├── deep_plan_config.json        # Session state (for resume)
├── claude-research.md           # Web + codebase research findings
├── claude-interview.md          # Q&A transcript
├── claude-spec.md               # Synthesized specification
├── claude-plan.md               # ★ Primary deliverable
├── claude-integration-notes.md  # Feedback integration decisions
├── claude-plan-tdd.md           # Test stubs
├── reviews/
│   ├── gemini-review.md         # Gemini feedback (if using Gemini)
│   ├── openai-review.md         # OpenAI feedback (if using OpenAI)
│   └── opus-review.md           # Opus subagent feedback (if no external LLMs)
└── sections/
    ├── index.md                 # Section manifest
    ├── section-01-*.md          # Implementation unit 1
    ├── section-02-*.md          # Implementation unit 2
    └── ...
```

## Configuration

Edit `config.json` at the plugin root:

```json
{
  "context": {
    "check_enabled": true
  },
  "vertex_ai": {
    "project": null,
    "location": null
  },
  "external_review": {
    "alert_if_missing": true,
    "feedback_iterations": 1
  },
  "models": {
    "gemini": "gemini-3-pro-preview",
    "chatgpt": "gpt-5.2"
  },
  "llm_client": {
    "timeout_seconds": 120,
    "max_retries": 3
  }
}
```

| Setting | Default | Purpose |
|---------|---------|---------|
| `context.check_enabled` | `true` | Prompt before token-intensive operations |
| `vertex_ai.project` | `null` | GCP project for Vertex AI (falls back to gcloud config) |
| `vertex_ai.location` | `null` | GCP location for Vertex AI (falls back to `GOOGLE_CLOUD_LOCATION`) |
| `external_review.alert_if_missing` | `true` | Warn if no LLM API keys configured |
| `models.gemini` | `gemini-3-pro-preview` | Gemini model for external review |
| `models.chatgpt` | `gpt-5.2` | OpenAI model for external review |
| `llm_client.timeout_seconds` | `120` | API call timeout |
| `llm_client.max_retries` | `3` | Retry attempts for transient errors |

## Environment Variables

### Gemini (choose one)

**deep-plan specific variables (highest priority):**
- `DEEPPLAN_GEMINI_API_KEY` - Gemini API key for deep-plan (overrides `GEMINI_API_KEY`)
- `DEEPPLAN_GOOGLE_APPLICATION_CREDENTIALS` - ADC path for deep-plan (overrides `GOOGLE_APPLICATION_CREDENTIALS`)
- `DEEPPLAN_GOOGLE_CLOUD_PROJECT` - GCP project for deep-plan (overrides `GOOGLE_CLOUD_PROJECT`)
- `DEEPPLAN_GOOGLE_CLOUD_LOCATION` - GCP location for deep-plan (overrides `GOOGLE_CLOUD_LOCATION`)

**Standard Gemini/Google variables (fallback):**
- `GEMINI_API_KEY` - [AI Studio API key](https://aistudio.google.com/apikey)
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON
- Default ADC at `~/.config/gcloud/application_default_credentials.json` ([setup guide](https://cloud.google.com/docs/authentication/application-default-credentials))

For Vertex AI, also set (or set in `config.json`):
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`

### OpenAI

**deep-plan specific variables (highest priority):**
- `DEEPPLAN_OPENAI_API_KEY` - API key for deep-plan (overrides `OPENAI_API_KEY`)
- `DEEPPLAN_OPENAI_BASE_URL` - Custom API endpoint for deep-plan (overrides `OPENAI_BASE_URL`)
- `DEEPPLAN_OPENAI_MODEL` - Model name for deep-plan (overrides `OPENAI_MODEL`)
  - **Note:** Preflight validation (`/deep-plan`) tests the effective model after applying precedence: `DEEPPLAN_OPENAI_MODEL` > `OPENAI_MODEL` > `config.json`

**Standard OpenAI variables (fallback):**
- `OPENAI_API_KEY` - [OpenAI API key](https://platform.openai.com/api-keys)
- `OPENAI_BASE_URL` (optional) - Custom API endpoint for OpenAI-compatible services (SDK v1.0+)
  - Example: `https://openai.compatible.com` (LiteLLM)
  - Example: `http://localhost:4000` (LocalAI)
  - If not set, defaults to `https://api.openai.com/v1`
- `OPENAI_MODEL` (optional) - Override model from config.json

**Variable precedence:** `DEEPPLAN_OPENAI_*` variables take precedence over `OPENAI_*` variables. This allows you to use different settings for deep-plan while keeping your standard OpenAI configuration intact.

**Provider selection during preflight (`validate-env.sh`):**
- If any `DEEPPLAN_OPENAI_*` or Gemini-related `DEEPPLAN_*` variable is set, preflight validates only the explicitly scoped provider(s)
- If no provider-scoping `DEEPPLAN_*` variables are set, preflight falls back to generic provider discovery (`GEMINI_*` / `OPENAI_*`)
- This prevents non-target provider failures from blocking `/deep-plan` when you intentionally scope to one provider

**Note:** This plugin requires OpenAI SDK v1.0+. The legacy `OPENAI_API_BASE` environment variable is not supported.

### Using OpenAI-Compatible APIs

deep-plan supports any OpenAI-compatible API endpoint (LiteLLM, LocalAI, etc.):

**Example 1: Using deep-plan specific variables (recommended)**

```bash
# Use DEEPPLAN_OPENAI_* variables to keep deep-plan settings separate
export DEEPPLAN_OPENAI_BASE_URL="https://openai.compatible.com"
export DEEPPLAN_OPENAI_API_KEY="sk-your-api-key"
export DEEPPLAN_OPENAI_MODEL="gpt-4"
/deep-plan @planning/spec.md
```

**Example 2: Using standard OpenAI variables**

```bash
# Use OPENAI_* variables (shared with other tools)
export OPENAI_BASE_URL="https://openai.compatible.com"
export OPENAI_API_KEY="sk-your-api-key"
export OPENAI_MODEL="gpt-4"
/deep-plan @planning/spec.md
```

**Example: Using LocalAI**

```bash
export OPENAI_BASE_URL="http://localhost:8080/v1"
export OPENAI_API_KEY="dummy-key"  # LocalAI doesn't require real key
export OPENAI_MODEL="gpt-4"
/deep-plan @planning/spec.md
```

The `OPENAI_BASE_URL` environment variable allows routing OpenAI API calls through:
- **LiteLLM**: Unified API for 100+ LLMs (Claude, Gemini, etc.)
- **LocalAI**: Self-hosted OpenAI-compatible server
- **Azure OpenAI**: Enterprise OpenAI deployment
- **Custom proxies**: Rate limiting, caching, monitoring

## Requirements

- Claude Code
- Python >= 3.11
- uv package manager
- (Optional) External LLM API key (Gemini or OpenAI) for external review

### Python Dependencies

Managed via `pyproject.toml`:
- `google-genai >= 1.0.0`
- `openai >= 1.0.0`

## Best Practices

1. **Start with a spec file** - Even a vague one. The interview phase will extract details.

2. **Answer interview questions thoroughly** - This is where requirements get surfaced.

3. **Review external feedback critically** - LLM reviewers catch blind spots but may suggest unnecessary complexity.

4. **Use sections for parallel work** - Each section file is self-contained. Multiple engineers (or Claude sessions) can work in parallel.

5. **Compact before starting** - The workflow is token-intensive. Start with a fresh or compacted context.

## Security & Privacy

### What deep-plan does with your data

- **Spec files**: Read by Claude.
- **Interview answers**: Stored locally in your planning directory and read by Claude.
- **External LLM review**: The integrated plan Claude creates is sent to Gemini/OpenAI for review (you control which LLMs)

### API Key Handling

Your API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`) are:
- Read only by `validate-env.sh` to confirm connectivity
- Never logged or transmitted by deep-plan code
- Passed directly to official SDKs ([google-genai](https://pypi.org/project/google-genai/), [openai](https://pypi.org/project/openai/))

## Troubleshooting

### "No external LLM configured"

**Issue**: validate-env.sh reports no Gemini or OpenAI auth

**Solution** (choose one):
- Set `GEMINI_API_KEY` or `OPENAI_API_KEY` environment variable
- Configure Google Cloud ADC: `gcloud auth application-default login`
- Continue without external keys—the plugin will offer Opus subagent review instead

### "Spec file not found"

**Issue**: The @file path doesn't exist

**Solution**:
- Ensure the file path is correct and the file exists
- Use absolute paths if relative paths aren't resolving

### Workflow interrupted mid-section

**Issue**: Context limit hit during section generation

**Solution**:
- Follow Claude's instructions or
- Re-run `/deep-plan @your-spec.md`
- The plugin detects completed sections and resumes from the next one

### External review timeout

**Issue**: LLM API calls timing out

**Solution**:
- Increase `llm_client.timeout_seconds` in config.json
- Check your API quotas and rate limits

## Local Development

When developing deep-plan:

### Avoiding Path Conflicts

The plugin uses `CLAUDE_PLUGIN_ROOT` to locate its scripts. When you have both an installed plugin AND a local git clone, path resolution prioritizes the installed version to prevent version mismatches.

**Best practices:**

1. **Install as plugin** (marketplace or manual) for normal use
2. **Clone separately** for development: `git clone https://github.com/piercelamb/deep-plan.git ~/dev/deep-plan`
3. **Avoid**: Cloning deep-plan inside project directories where you use it

### Testing Local Changes

**Option A: Update installed plugin files directly**
```bash
# Edit files in your installed plugin location
vim ~/.claude/plugins/deep-plan/skills/deep-plan/SKILL.md
```

**Option B: Override CLAUDE_PLUGIN_ROOT**
```bash
# Point to your development copy
export CLAUDE_PLUGIN_ROOT=~/dev/deep-plan
/deep-plan @planning/test-spec.md
```

**Option C: Use --plugin-dir flag**
```bash
# Launch Claude Code with your development copy
claude --plugin-dir ~/dev/deep-plan
```

### Path Resolution Behavior

The plugin's path resolution follows this priority:

1. **CLAUDE_PLUGIN_ROOT** (most reliable) - Set by Claude Code when plugin is loaded
2. **Installed plugin roots** - Searches known Claude plugin install/cache locations (`~/.claude/plugins/cache`, `~/.claude/plugins`)
3. **Find from pwd** (development fallback) - Searches current directory tree

If resolution fails, preflight prints attempted roots and direct recovery steps (`/plugin install deep-plan` or `claude --plugin-dir <path>`).

## Testing

Run the test suite:

```bash
cd /path/to/deep-plan
uv run pytest tests/
```

## Project Structure

```
deep_plan/
├── .claude-plugin/plugin.json    # Plugin metadata
├── config.json                   # Global configuration
├── LICENSE                       # MIT License
├── README.md                     # This file
├── pyproject.toml               # Python dependencies
├── scripts/
│   ├── checks/                  # Validation & setup scripts
│   ├── lib/                     # Shared utilities
│   └── llm_clients/             # External LLM integration
├── skills/
│   └── deep-plan/
│       ├── SKILL.md             # Main skill definition
│       └── references/          # Protocol documents
├── prompts/                     # LLM review prompts
└── tests/                       # Test suite
```

## Contributing

Contributions welcome! Please:

1. Clone the repository
2. Create a feature branch
3. Run tests: `uv run pytest tests/`
4. Submit a pull request

## License

[MIT](./LICENSE)

## Author

Pierce Lamb

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Version

0.3.1
