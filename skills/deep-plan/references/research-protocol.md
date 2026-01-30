# Research Protocol

This document defines the research decision and execution flow for steps 6-7 of the deep-plan workflow.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│  RESEARCH FLOW                                              │
│                                                             │
│  Step 6: Decide what to research                            │
│    - Codebase research? (existing patterns/conventions)     │
│    - Web research? (best practices, SOTA approaches)        │
│                                                             │
│  Step 7: Execute research (parallel if both selected)       │
│    - Subagents return results                               │
│    - Main Claude combines and writes claude-research.md     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 6: Research Decision

### 6.1 Read and Analyze the Spec File

Read the spec file (from `initial_file` in task context items) and extract potential research topics by identifying:

- **Technologies mentioned** (React, Python, PostgreSQL, Redis, etc.)
- **Feature types** (authentication, file upload, real-time sync, caching, etc.)
- **Architecture patterns** (microservices, event-driven, serverless, etc.)
- **Integration points** (third-party APIs, OAuth providers, payment gateways, etc.)

Generate 3-5 research topic suggestions based on what you find. Format them as searchable queries with year for recency:
- "React authentication patterns 2025"
- "PostgreSQL full-text search best practices"
- "Redis session storage patterns"
- "File upload security considerations"

If the spec is vague with no clear technologies, fall back to generic options:
- "General best practices for {detected_language/framework}"
- "Security considerations for {feature_type}"
- "Performance optimization patterns"

### 6.2 Ask About Codebase Research

Use AskUserQuestion to determine if there's existing code to analyze:

```
question: "Is there existing code I should research first?"
header: "Codebase"
options:
  - label: "Yes, research the codebase"
    description: "Analyze existing patterns, conventions, dependencies, and testing setup"
  - label: "No existing code"
    description: "This is a new project or standalone feature"
```

### 6.3 Ask About Web Research

Present the derived topics as multi-select options:

```
question: "Should I research current best practices for any of these topics?"
header: "Web Research"
multiSelect: true
options:
  - label: "{derived_topic_1}"
    description: "Based on spec mention of {X}"
  - label: "{derived_topic_2}"
    description: "Based on spec mention of {Y}"
  - label: "{derived_topic_3}"
    description: "Based on spec mention of {Z}"
  - label: "Other (I'll specify)"
    description: "Enter custom research topics"
```

If user selects "Other", follow up with a free-text question to get their custom topics.

### 6.4 Handle "No Research" Case

If user selects:
- "No existing code" AND
- No web research topics

Then skip step 7 entirely. But still ask about testing preferences for new projects:
- What testing framework to use (or recommend based on language/framework)
- Any testing conventions to follow

Note these preferences in `claude-research.md`.

---

## Step 7: Execute Research

### Critical Pattern: Subagents Return Results, Parent Writes Files

**DO NOT** have subagents write to files directly. This is important because:

1. **Avoids race conditions** - Parallel subagents writing to the same file would overwrite each other
2. **Context isolation** - Subagents keep verbose output in their own context, returning only summaries
3. **Parent control** - Main Claude decides final structure and handles file operations

```
┌─────────────────────────────────────────────────────────────┐
│  PARALLEL RESEARCH EXECUTION                                │
│                                                             │
│  Task 1: Explore ──────────┐                                │
│    (returns codebase       │                                │
│     findings as markdown)  ├──→ Main Claude combines       │
│                            │    and writes single          │
│  Task 2: web-search ───────┘    claude-research.md         │
│    (returns best practices                                  │
│     findings as markdown)                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.1 Codebase Research (if selected)

Launch Task tool with `subagent_type=Explore`:

```
Task tool:
  subagent_type: Explore
  description: "Research codebase patterns"
  prompt: |
    Research this codebase to understand:
    - Project structure and architecture
    - Existing patterns and conventions
    - Dependencies and how they're used
    - Testing setup (framework, patterns, utilities, how tests are run)

    Focus areas from user: {user_specified_areas_if_any}

    Return your findings as markdown. Structure it however makes sense for what you find.

    DO NOT write to any files. Return your findings in your response.
```

### 7.2 Web Research (if topics selected)

Launch Task tool with `subagent_type=web-search-researcher`:

```
Task tool:
  subagent_type: web-search-researcher
  description: "Research best practices"
  prompt: |
    Research current best practices for the following topics:
    {selected_topics_list}

    For each topic:
    1. Use WebSearch to find authoritative sources (official docs, respected blogs, recent articles)
    2. Use WebFetch on promising results to extract specific recommendations
    3. Cross-validate information across sources
    4. Synthesize findings with clear recommendations

    Return your findings as markdown. Structure it however makes sense.
    Always cite sources with URLs.

    DO NOT write to any files. Return your findings in your response.
```

### 7.3 Parallel Execution

If both codebase and web research are needed, launch **both Task tools in a single message**. This enables parallel execution.

```
# Single message with multiple tool calls:
[Task tool call 1: Explore subagent]
[Task tool call 2: web-search-researcher subagent]
```

Wait for both to complete, then proceed to combining results.

### 7.4 Combine Results and Write File

After collecting results from all subagents, combine them into `<planning_dir>/claude-research.md`.

Structure the file however makes sense for the findings. The goal is to capture useful research that will inform the implementation plan - there's no required format.

---

## Edge Cases

| Case | Handling |
|------|----------|
| Spec file is vague | Present generic options based on any detected language/framework |
| User selects no research | Skip step 7, proceed to step 8 (interview). Still capture testing preferences for new projects. |
| Web research subagent fails | Log warning, write file with only codebase research (if it succeeded) |
| Both subagents fail | Log error, ask user if they want to retry or proceed without research |
| Only one research type selected | Run single subagent, write file with just that content |
| WebFetch returns truncated content | Subagent handles internally - notes incomplete info and tries additional sources |

---

## Example Flow

**User runs:** `/deep-plan @planning/auth-feature-spec.md`

**Spec file contains:**
```markdown
# Authentication Feature

Add OAuth2 login with Google and GitHub providers.
Store sessions in Redis. Use JWT for API authentication.
```

**Step 6 - Claude extracts topics:**
- "OAuth2 implementation best practices 2025"
- "JWT vs session authentication trade-offs"
- "Redis session storage patterns"

**Step 6 - Claude asks:**
```
Q1: Is there existing code I should research first?
  → User selects: "Yes, research the codebase"

Q2: Should I research best practices for any of these topics?
  → User selects:
    ✓ "OAuth2 implementation best practices 2025"
    ✓ "JWT vs session authentication trade-offs"
    ✗ "Redis session storage patterns"
```

**Step 7 - Claude launches parallel tasks:**
```
# Single message:
Task(subagent_type=Explore, prompt="Research codebase...")
Task(subagent_type=web-search-researcher, prompt="Research OAuth2, JWT...")
```

**Step 7 - After both complete:**
Main Claude combines both results and writes single `claude-research.md`.
