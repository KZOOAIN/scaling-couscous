---
name: resumable-pipeline
version: 1.0.0
description: |
  Start and drive a resumable multi-phase pipeline for long-running work
  (white papers, research plans, audits). After each phase, writes state.yaml +
  STATE.md so any future session can resume exactly where this one stopped.
  Integrates with doc-criteria (T1-T5) for measurable phase acceptance gates.
  Use when asked to "start a pipeline", "resumable pipeline", or "run <X> as a pipeline".
  Pair with /resume to continue across session boundaries. (gstack)
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
  - start pipeline
  - resumable pipeline
  - new pipeline
  - run as pipeline
  - pipeline for
---

## Preamble (run first)

```bash
_UPD=$(~/.claude/skills/gstack/bin/gstack-update-check 2>/dev/null || .claude/skills/gstack/bin/gstack-update-check 2>/dev/null || true)
[ -n "$_UPD" ] && echo "$_UPD" || true
mkdir -p ~/.gstack/sessions
touch ~/.gstack/sessions/"$PPID"
_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "BRANCH: $_BRANCH"
_TEL_START=$(date +%s)
_SESSION_ID="$$-$(date +%s)"
PIPELINE_PY="$HOME/.claude/skills/resumable-pipeline/pipeline.py"
echo "PIPELINE_PY: $PIPELINE_PY"
python3 "$PIPELINE_PY" --self-test > /dev/null 2>&1 && echo "pipeline.py: OK" || echo "pipeline.py: WARN self-test failed"
```

---

## Step 0 — Gather inputs

Ask for the following (use AskUserQuestion with D1/D2 format):

**D1: What are we building?**
- Title: human-readable name for the pipeline (e.g., "CFO White Paper v2")
- Slug: kebab-case identifier (e.g., "cfo-white-paper-v2") — auto-derive from title if not given
- Brief: path to an existing plan/brief file, or "none"
- Phases: comma-separated list, or use this default for document pipelines:
  `research,outline,draft,doc-criteria-validation,final-review`

**D2: Parallel pipelines?**
- If the user wants multiple independent pipelines run in parallel (e.g., CFO white paper
  AND KAI thesis simultaneously), confirm which slugs to run in parallel.
- Parallel means: launch both with `Agent(run_in_background=True)`, each managing its own
  state.yaml. Not the same as parallelizing phases within one document pipeline
  (document phases are sequential by nature).

---

## Step 1 — Initialize

```bash
python3 "$PIPELINE_PY" init \
  --slug "<slug>" \
  --title "<title>" \
  --phases "<p1,p2,p3,...>" \
  [--brief "<brief-path>"]
```

Print the created paths. Confirm pipeline is visible:
```bash
python3 "$PIPELINE_PY" read "<slug>" | head -20
```

---

## Step 2 — Execute phases in order

For each phase, follow this loop:

### 2a. Mark phase in-progress
```bash
python3 "$PIPELINE_PY" update-phase "<slug>" "<phase>" --status in-progress
```

### 2b. Do the work
Execute the phase work directly (editing files, writing sections, running acceptance tests).

For long independent phases that can run concurrently with another pipeline:
use `Agent(run_in_background=True)`. Each parallel agent reads its own state.yaml.
State files are atomic (temp+rename) so concurrent writes to *different* pipelines
are safe.

### 2c. Collect artifacts
List all files created or modified during this phase.

### 2d. Run phase acceptance criteria
```bash
python3 "$PIPELINE_PY" run-criteria "<slug>" "<phase>"
```

For document phases, always include a `doc-criteria` criterion that invokes acceptance.py.
If criteria fail, report failures with fix_hints and stay in-progress — do not advance.
Fix and re-run until passing.

### 2e. Mark phase complete with artifacts
```bash
python3 "$PIPELINE_PY" update-phase "<slug>" "<phase>" \
  --status complete \
  --artifacts /path/to/artifact1.md /path/to/artifact2.md
```

This records sha256 hashes so /resume can detect if artifacts were modified between sessions.

### 2f. Check session budget
After each phase, assess remaining work. If budget is tight:
- Print: `"Phase '<name>' complete. STATE.md saved. Run /resume <slug> to continue."`
- Do NOT stop mid-phase. Always complete the current phase before pausing.

---

## Step 3 — Completion

When all phases complete:
```bash
python3 "$PIPELINE_PY" read "<slug>"
```
Print a final summary table: phase | status | criteria | key artifacts.

If this was a document pipeline and a PDF was not yet generated, offer:
"Run /make-pdf on the final artifact?"

---

## Phase criteria design guide

Each phase should have 1-3 measurable criteria. Choose the right assertion type:

| Situation | Type | Example |
|-----------|------|---------|
| Document structural requirement | `grep` | `## Risks` section present |
| External JSON config valid | `json-valid` | `openclaw.json` parses |
| Config value correct | `jq` | `.status == "active"` |
| Full doc-criteria suite | `doc-criteria` | T1-T5 all pass |
| Anything else | `shell` | `test -f output.pdf` |

**For document pipelines, add doc-criteria criterion on the final draft phase:**
```yaml
criteria:
  - id: doc-criteria-full
    type: doc-criteria
    description: "5/5 acceptance tests pass (sources, diagram, exec summary, risks, stakeholder Qs)"
    draft: /path/to/draft.md
    brief: /path/to/brief.md
```

**T2_ascii_first requires an ASCII or box-drawing diagram as the very first content block.**
This is non-negotiable. Add the diagram during the `outline` or `ascii-structure` phase,
not as an afterthought in final-review.

---

## Important rules

- NEVER overwrite v1 documents — always work on a copy with a `_v2` or `_draft` suffix.
- NEVER advance a phase to `complete` until its criteria pass.
- NEVER stop mid-phase — finish the current phase so STATE.md is consistent.
- Run `pipeline.py --self-test` at skill start; if it fails, fix before proceeding.
- After marking a phase complete, always run `pipeline.py render <slug>` to refresh STATE.md.
- STATE.md is a generated view — never hand-edit it; edit state.yaml via pipeline.py commands.
