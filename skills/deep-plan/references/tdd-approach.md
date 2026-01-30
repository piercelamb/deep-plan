# TDD Approach Reference

This step creates `claude-plan-tdd.md` - a companion document that defines what tests to write BEFORE implementing each part of the plan.

## Prerequisites

- `claude-plan.md` exists with the implementation plan
- Step 6 determined whether this is an existing codebase or new project

## Step 1: Verify Testing Context

Check if `<planning_dir>/claude-research.md` contains testing information. You can also use this file to tell if you're operating on an existing codebase or a new project.


### For Existing Codebases

If no testing section exists, use Task tool with `subagent_type=Explore` to research:

- Testing framework used (pytest, jest, unittest, etc.)
- Test file locations and naming conventions (e.g., `tests/`, `*_test.py`)
- Existing fixtures, factories, or test utilities
- Mocking patterns (what libraries, how dependencies are mocked)
- How tests are run (commands, CI integration, coverage requirements)
- Any test configuration files (pytest.ini, conftest.py, jest.config.js)

Append findings to `<planning_dir>/claude-research.md` under "## Testing".

### For New Projects

If no testing preferences were captured in step 6, recommend a testing approach based on the language/framework:

| Language/Framework | Recommended Testing Setup |
|-------------------|--------------------------|
| Python | pytest with fixtures |
| TypeScript/JavaScript | jest or vitest |
| Go | standard testing package |
| Rust | built-in test framework |
| Java | JUnit 5 |

Document the chosen approach in `<planning_dir>/claude-research.md` under "## Testing Approach".

## Step 2: Create the TDD Plan

Read `<planning_dir>/claude-plan.md` and discover its structure (sections, phases, components - whatever organization it uses).

### Output File

Write `<planning_dir>/claude-plan-tdd.md` with:

1. **Mirror the plan's structure** - Use the same section headings from `claude-plan.md`
2. **Define test stubs** - For each implementation section, specify what tests to write BEFORE implementing
3. **Reference original sections** - Use the actual headings from the plan
4. **Follow project conventions**:
   - Existing codebase: Use the project's actual testing patterns - don't invent new conventions
   - New project: Use the recommended/chosen testing approach consistently
5. **Don't duplicate implementation details** - Just specify what to test, not how to implement

**CRITICAL - Stubs means stubs.** Test "stubs" are prose descriptions or minimal signatures explaining what to test - NOT full test implementations. Example:

```python
# Test: parse_company_page extracts name from JSON-LD
# Test: parse_company_page falls back to HTML when JSON-LD missing
# Test: parse_company_page logs warning when <50% fields populated
```

NOT full pytest functions with assertions, fixtures, and mocking. The implementer writes the actual test code.

## Usage in Step 18

Step 18 (Split Into Sections) uses both files:
- `claude-plan.md` - The implementation details
- `claude-plan-tdd.md` - The tests to write first

Each implementation section includes both what to implement AND what tests to write before implementing.
