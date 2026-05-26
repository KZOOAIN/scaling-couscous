---
name: resume
version: 1.0.0
description: |
  Auto-discover the most recent in-flight pipeline and resume it from the last
  completed phase. Re-verifies all completed artifacts and acceptance criteria
  before continuing — so a missing or modified artifact is caught before any
  new work builds on broken foundations.
  Use when asked to "resume", "continue pipeline", or "/resume <slug>".
  Pair with /resumable-pipeline to start new pipelines. (gstack)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
triggers:
  - resume
  - resume pipeline
  - continue pipeline
  - pick up where
  - resume my work
---

## Preamble (run first)

```bash
_UPD=$(~/.claude/skills/gstack/bin/gstack-update-check 2>/dev/null || .claude/skills/gstack/bin/gstack-update-check 2>/dev/null || true)
[ -n "$_UPD" ] && echo "$_UPD" || true
PIPELINE_PY="$HOME/.claude/skills/resumable-pipeline/pipeline.py"
echo "PIPELINE_PY: $PIPELINE_PY"
```

---

## Step 1 — Discover in-flight pipelines

```bash
python3 "$PIPELINE_PY" find-in-flight
```

**If 0 results:**
"No in-flight pipelines found. Start one with /resumable-pipeline."
Stop.

**If 1 result:**
Auto-select it. Print: "Resuming pipeline: <title> (<slug>)"

**If >1 results:**
AskUserQuestion — present up to 4 pipelines sorted by most-recently-updated.
Let the user pick which to resume.

If the user invoked `/resume <slug>` with an explicit slug argument, skip discovery
and use that slug directly.

---

## Step 2 — Read + display current state

```bash
python3 "$PIPELINE_PY" read "<slug>"
```

Print a concise summary:
```
Pipeline: <title>
Current phase: <phase>
Phases: ✓ research | → draft | ○ final-review
```

---

## Step 3 — Verify all completed phases

For each phase with status=complete:
```bash
python3 "$PIPELINE_PY" verify "<slug>" "<phase>"
```

Report for each:
- `✓ <phase>` — all artifacts present, all criteria pass
- `✗ <phase>` — artifact missing or criterion regressed:
  - List each failure with its fix_hint

**If any phase fails verification:**
AskUserQuestion:
- "Re-run <phase> before continuing?" (recommended if artifacts are missing)
- "Skip verification failure and continue anyway?" (only safe if artifact was intentionally replaced)
- "Stop here and let me investigate."

Do not silently ignore verification failures. The whole point of STATE.md is to catch these.

---

## Step 4 — Resume from next pending phase

```bash
python3 "$PIPELINE_PY" get-resume-point "<slug>"
```

Execute phases from the resume point forward, following the same loop as
/resumable-pipeline Step 2:

For each remaining phase:
1. Mark in-progress
2. Do the work
3. Run phase criteria (fix until passing)
4. Mark complete with artifacts
5. Check session budget — if tight, pause cleanly after current phase

---

## Step 5 — Final check

When all phases complete:
```bash
python3 "$PIPELINE_PY" verify "<slug>"
```

All phases should now pass. Print final summary.
If this was a document pipeline, offer to run /make-pdf on the final artifact.

---

## Important rules

- NEVER skip Step 3 verification — it is the core value of the resumable pipeline.
- If a sha256 mismatch is detected (artifact was overwritten), report it explicitly;
  the user may have made manual edits that the pipeline criteria no longer reflect.
- Resuming does NOT mean re-doing completed work — only verify + advance.
- If a phase is currently `in-progress` (session died mid-phase), treat it as the
  resume point; re-run its work from scratch since it was never marked complete.
