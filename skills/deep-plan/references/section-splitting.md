# Parallel Section File Writing

Write section files using parallel subagents. By this point you have:
- Expected tasks from step 19 including batch coordination tasks (`batch-N`)
- Individual section tasks (`section-{name}`) for each section
- All sections within a batch depend on the batch task (parallel within batch)

**How it works:** A `SubagentStop` hook automatically writes section files when subagents complete. Claude launches subagents and verifies files exist - no manual JSON parsing needed.

## Task Structure

Section tasks use batch parallelism:
- **Batch tasks** (`batch-1`, `batch-2`, etc.) coordinate each batch
- **Section tasks** (`section-01-setup`, etc.) depend only on their batch task, not on each other
- This means all sections in a batch can run in parallel

```
batch-1 (depends on create-section-index)
 ├─► section-01-setup ─┐
 ├─► section-02-core  ─┼─► (all parallel, all depend on batch-1)
 └─► section-03-api   ─┘

batch-2 (depends on batch-1)
 ├─► section-04-tests ─┐
 └─► section-05-docs  ─┴─► (all parallel, all depend on batch-2)

final-verification (depends on last batch)
output-summary (depends on final-verification)
```

## Batch Execution Loop

For each batch:

### 1. Mark Batch Task In Progress

Find the batch task by subject "Run batch N section subagents" and mark it in progress:
```
TaskUpdate(taskId=<batch_task_id>, status="in_progress")
```

### 2. Run generate-batch-tasks.py

```bash
uv run {plugin_root}/scripts/checks/generate-batch-tasks.py \
  --planning-dir "<planning_dir>" \
  --batch-num N
```

The script outputs JSON with `prompt_files` - an array of paths to the prompt files for this batch.

### 3. Launch Parallel Task Subagents

**IMPORTANT:** Launch ALL Task calls in a single message to run them in parallel.

For each prompt file path in the `prompt_files` array, make a Task call:
- `subagent_type`: "section-writer"
- `description`: "Write {section_filename}" (extract from the prompt file name)
- `prompt`: "Read {prompt_file_path} and execute the instructions."

Example: If the JSON output has 5 prompt files, send a single message with 5 Task tool calls.

### 4. Verify Files Were Written

**The SubagentStop hook writes files automatically.** When each subagent completes, a hook:
1. Parses the subagent's transcript for JSON output
2. Extracts `sections_dir`, `filename`, and `content`
3. Writes the file to `{sections_dir}/{filename}`

**You must verify the files exist** - hooks run in isolation and don't report back to Claude.

After all subagents in the batch complete, check which files were created:

```bash
ls {planning_dir}/sections/
```

Compare against expected filenames from the batch. For each file that exists:
- Mark the section task complete (find task by subject "Write {filename}"):
  ```
  TaskUpdate(taskId=<section_task_id>, status="completed")
  ```

### 5. Handle Missing Files

If any expected files are missing after subagents complete:

**Step 1: Retry the subagent**
Re-run `generate-batch-tasks.py --batch-num N` - it automatically generates prompts only for missing sections. Launch the subagent again.

**Step 2: Manual fallback**
If the file is still missing after retry, fall back to manual file writing:
1. The subagent's response contains JSON with `content` field
2. Parse the JSON and extract content
3. Write to `{planning_dir}/sections/{filename}` using the Write tool

### 6. Mark Batch Complete

After all section files in the batch are verified, mark the batch task complete:
```
TaskUpdate(taskId=<batch_task_id>, status="completed")
```

### 7. Next Batch

If there are more batches, repeat from step 1 with the next batch number.

## Final Verification

After all batches complete, run check-sections.py to confirm `state == "complete"`:

```bash
uv run {plugin_root}/scripts/checks/check-sections.py --planning-dir "<planning_dir>"
```

## Section File Requirements

Each section file must be **completely self-contained**. The implementer should be able to read only that section file, create a task list, and start implementing immediately without referencing any other documents.

## Debugging

If sections aren't being written:

1. **Check sections dir:** `ls {planning_dir}/sections/` - see what was written
2. **Check tracking files:** `ls ~/.claude/section-writer-agents/` (should be empty after cleanup)
3. **Check prompt files:** `{planning_dir}/sections/.prompts/` - review what was sent to subagent
4. **Check subagent output:** The Task tool response contains the subagent's JSON output for manual fallback

## Prompt Files

The script writes full prompt files to `<planning_dir>/sections/.prompts/`. These persist (not temporary) and can be reviewed for debugging if a subagent produces unexpected output.
