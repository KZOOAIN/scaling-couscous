#!/usr/bin/env python3
"""pipeline.py — resumable-pipeline state manager

Manages state.yaml (machine ground truth) and STATE.md (human-readable view)
for the /resumable-pipeline skill. All writes are atomic (temp+rename).

Usage:
  pipeline.py init --slug <slug> --title <title> --phases <p1,p2,...> [--brief <path>]
  pipeline.py read <slug>
  pipeline.py update-phase <slug> <phase> --status <status> [--artifacts <paths>]
  pipeline.py run-criteria <slug> <phase>
  pipeline.py verify <slug> [<phase>]
  pipeline.py find-in-flight
  pipeline.py get-resume-point <slug>
  pipeline.py render <slug>
  pipeline.py import-plain <slug> --title <title> --plain-state <path> --artifacts <paths>
  pipeline.py --self-test
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

PIPELINE_STATE_DIR = Path.home() / ".claude" / "pipeline-state"
DOC_CRITERIA_SCRIPT = Path.home() / ".claude" / "skills" / "doc-criteria" / "acceptance.py"


# ──────────────────────────────────────────────────────────
# Path helpers
# ──────────────────────────────────────────────────────────

def slug_dir(slug: str) -> Path:
    return PIPELINE_STATE_DIR / slug

def state_yaml_path(slug: str) -> Path:
    return slug_dir(slug) / "state.yaml"

def state_md_path(slug: str) -> Path:
    return slug_dir(slug) / "STATE.md"


# ──────────────────────────────────────────────────────────
# Atomic write
# ──────────────────────────────────────────────────────────

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ──────────────────────────────────────────────────────────
# STATE.md renderer
# ──────────────────────────────────────────────────────────

def render_state_md(state: dict) -> str:
    slug = state["pipeline"]
    title = state["title"]
    status = state["status"]
    current_phase = state.get("current_phase", "")
    updated = state.get("updated", "")
    brief = state.get("brief", "")

    status_icon = {"complete": "✓", "in-progress": "→", "blocked": "✗"}.get(status, "?")
    lines = [
        f"# Pipeline: {title}",
        "",
        f"**Status:** {status_icon} {status}  ",
        f"**Slug:** `{slug}`  ",
        f"**Current phase:** `{current_phase}`  ",
        f"**Updated:** {updated}  ",
    ]
    if brief:
        lines.append(f"**Brief:** `{brief}`  ")
    lines += ["", "---", "", "## Phases", ""]

    for phase in state.get("phases", []):
        pname = phase["name"]
        pstatus = phase.get("status", "pending")
        icon = {"complete": "✓", "in-progress": "→", "pending": "○", "failed": "✗"}.get(pstatus, "?")
        lines.append(f"### {icon} `{pname}` — {pstatus}")

        if phase.get("started"):
            lines.append(f"- Started: {phase['started']}")
        if phase.get("completed"):
            lines.append(f"- Completed: {phase['completed']}")

        verdict = phase.get("criteria_verdict", "")
        if verdict:
            lines.append(f"- Criteria: {verdict}")

        artifacts = phase.get("artifacts", [])
        if artifacts:
            lines.append("- Artifacts:")
            for art in artifacts:
                apath = art.get("path", "")
                exists = Path(apath).exists()
                mark = "✓" if exists else "✗ MISSING"
                lines.append(f"  - {mark} `{apath}`")

        criteria = phase.get("criteria", [])
        if criteria and pstatus == "pending":
            lines.append("- Acceptance criteria:")
            for c in criteria:
                lines.append(f"  - `{c['id']}`: {c['description']}")

        lines.append("")

    lines += [
        "---",
        "",
        f"**Resume command:** `/resume {slug}`",
        "",
        f"*State file: `{state_yaml_path(slug)}`*",
    ]
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────
# init
# ──────────────────────────────────────────────────────────

def cmd_init(slug: str, title: str, phase_names: list, brief: Optional[str] = None,
             phase_criteria: Optional[dict] = None) -> dict:
    ts = now_iso()
    phases = []
    for pname in phase_names:
        criteria = (phase_criteria or {}).get(pname, [])
        phases.append({"name": pname, "status": "pending", "artifacts": [], "criteria": criteria})

    state = {
        "pipeline": slug,
        "title": title,
        "status": "in-progress",
        "current_phase": phase_names[0] if phase_names else "",
        "created": ts,
        "updated": ts,
        "phases": phases,
    }
    if brief:
        state["brief"] = brief

    slug_dir(slug).mkdir(parents=True, exist_ok=True)
    yaml_content = yaml.safe_dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write(state_yaml_path(slug), yaml_content)
    atomic_write(state_md_path(slug), render_state_md(state))
    return state


# ──────────────────────────────────────────────────────────
# read
# ──────────────────────────────────────────────────────────

def cmd_read(slug: str) -> dict:
    p = state_yaml_path(slug)
    if not p.exists():
        raise FileNotFoundError(f"No pipeline found: {slug} (expected {p})")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ──────────────────────────────────────────────────────────
# update-phase
# ──────────────────────────────────────────────────────────

def cmd_update_phase(slug: str, phase_name: str, status: str,
                     artifacts: Optional[list] = None,
                     criteria_results: Optional[list] = None) -> dict:
    state = cmd_read(slug)
    ts = now_iso()

    for phase in state["phases"]:
        if phase["name"] != phase_name:
            continue

        phase["status"] = status
        if status == "in-progress" and not phase.get("started"):
            phase["started"] = ts
        if status == "complete":
            phase["completed"] = ts

        if artifacts is not None:
            art_list = []
            for apath in artifacts:
                sha = sha256_file(apath)
                art_list.append({"path": apath, "sha256": sha or "MISSING"})
            phase["artifacts"] = art_list

        if criteria_results is not None:
            passed = sum(1 for r in criteria_results if r.get("passed"))
            total = len(criteria_results)
            phase["criteria_verdict"] = f"{passed}/{total} pass"
            for c in phase.get("criteria", []):
                for r in criteria_results:
                    if r.get("id") == c["id"]:
                        c["verdict"] = "pass" if r.get("passed") else "fail"

        break

    # Update current_phase pointer
    if status == "complete":
        # Advance current_phase to next pending
        phases = state["phases"]
        for i, ph in enumerate(phases):
            if ph["name"] == phase_name and i + 1 < len(phases):
                state["current_phase"] = phases[i + 1]["name"]
                break
        else:
            state["current_phase"] = phase_name

    # Check overall completion
    all_done = all(ph.get("status") == "complete" for ph in state["phases"])
    state["status"] = "complete" if all_done else "in-progress"
    state["updated"] = ts

    yaml_content = yaml.safe_dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write(state_yaml_path(slug), yaml_content)
    atomic_write(state_md_path(slug), render_state_md(state))
    return state


# ──────────────────────────────────────────────────────────
# Criteria runner
# ──────────────────────────────────────────────────────────

def run_one_criterion(c: dict) -> dict:
    ctype = c.get("type", "shell")
    cid = c.get("id", "unknown")
    desc = c.get("description", "")

    if ctype == "grep":
        fpath = c.get("file", "")
        pattern = c.get("pattern", "")
        if not Path(fpath).exists():
            return {"id": cid, "passed": False, "detail": f"File not found: {fpath}",
                    "fix_hint": "Ensure artifact exists before running criteria."}
        try:
            result = subprocess.run(["grep", "-qP", pattern, fpath], capture_output=True)
            passed = result.returncode == 0
        except Exception as e:
            return {"id": cid, "passed": False, "detail": str(e), "fix_hint": ""}
        return {"id": cid, "passed": passed,
                "detail": f"grep '{pattern}' in {fpath}: {'found' if passed else 'not found'}",
                "fix_hint": "" if passed else f"Add content matching pattern '{pattern}' to {fpath}"}

    elif ctype == "jq":
        fpath = c.get("file", "")
        path = c.get("path", "")
        expected = str(c.get("expected", ""))
        try:
            result = subprocess.run(["jq", "-r", path, fpath], capture_output=True, text=True)
            actual = result.stdout.strip()
            passed = actual == expected
        except Exception as e:
            return {"id": cid, "passed": False, "detail": str(e), "fix_hint": ""}
        return {"id": cid, "passed": passed,
                "detail": f"jq {path} = {actual!r} (expected {expected!r})",
                "fix_hint": "" if passed else f"Set {path} to {expected!r} in {fpath}"}

    elif ctype == "json-valid":
        fpath = c.get("file", "")
        try:
            result = subprocess.run(
                ["python3", "-m", "json.tool", fpath],
                capture_output=True, text=True
            )
            passed = result.returncode == 0
        except Exception as e:
            return {"id": cid, "passed": False, "detail": str(e), "fix_hint": ""}
        return {"id": cid, "passed": passed,
                "detail": f"{fpath} JSON valid" if passed else result.stderr.strip(),
                "fix_hint": "" if passed else "Fix JSON syntax errors."}

    elif ctype == "doc-criteria":
        draft = c.get("draft", "")
        brief = c.get("brief", "")
        if not DOC_CRITERIA_SCRIPT.exists():
            return {"id": cid, "passed": False,
                    "detail": f"doc-criteria script not found: {DOC_CRITERIA_SCRIPT}",
                    "fix_hint": "Install doc-criteria skill."}
        try:
            result = subprocess.run(
                ["python3", str(DOC_CRITERIA_SCRIPT), "--draft", draft, "--brief", brief],
                capture_output=True, text=True
            )
            verdict = json.loads(result.stdout)
            passed = verdict.get("passed", False)
            score = verdict.get("score", 0)
            failures = verdict.get("failures", [])
            detail = f"doc-criteria {score}/5 pass"
            if failures:
                detail += " | Failures: " + "; ".join(f["test_id"] for f in failures)
            fix_hints = [f.get("fix_hint", "") for f in failures if f.get("fix_hint")]
            return {"id": cid, "passed": passed, "detail": detail,
                    "fix_hint": " | ".join(fix_hints) if fix_hints else "",
                    "doc_criteria_verdict": verdict}
        except Exception as e:
            return {"id": cid, "passed": False, "detail": str(e), "fix_hint": ""}

    elif ctype == "shell":
        command = c.get("command", "")
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            passed = result.returncode == 0
        except Exception as e:
            return {"id": cid, "passed": False, "detail": str(e), "fix_hint": ""}
        stderr = result.stderr.strip()
        return {"id": cid, "passed": passed,
                "detail": f"exit {result.returncode}" + (f" | {stderr}" if stderr else ""),
                "fix_hint": "" if passed else f"Fix: `{command}`"}

    else:
        return {"id": cid, "passed": False, "detail": f"Unknown criterion type: {ctype}",
                "fix_hint": "Use: grep, jq, json-valid, doc-criteria, or shell."}


def cmd_run_criteria(slug: str, phase_name: str) -> dict:
    state = cmd_read(slug)
    for phase in state["phases"]:
        if phase["name"] == phase_name:
            criteria = phase.get("criteria", [])
            results = [run_one_criterion(c) for c in criteria]
            passed = all(r["passed"] for r in results)
            score = sum(1 for r in results if r["passed"])
            return {
                "phase": phase_name,
                "passed": passed,
                "score": f"{score}/{len(results)}",
                "results": results,
            }
    raise ValueError(f"Phase not found: {phase_name} in pipeline {slug}")


# ──────────────────────────────────────────────────────────
# verify
# ──────────────────────────────────────────────────────────

def cmd_verify(slug: str, phase_name: Optional[str] = None) -> dict:
    state = cmd_read(slug)
    phases_to_check = [
        ph for ph in state["phases"]
        if ph.get("status") == "complete" and (phase_name is None or ph["name"] == phase_name)
    ]

    all_ok = True
    report = []
    for phase in phases_to_check:
        pname = phase["name"]
        failures = []

        # Check artifact existence + sha256
        for art in phase.get("artifacts", []):
            apath = art.get("path", "")
            expected_sha = art.get("sha256", "")
            if not Path(apath).exists():
                failures.append(f"Artifact missing: {apath}")
                continue
            if expected_sha and expected_sha != "MISSING":
                actual_sha = sha256_file(apath)
                if actual_sha != expected_sha:
                    failures.append(f"Artifact changed since phase completed: {apath} "
                                    f"(expected {expected_sha}, got {actual_sha})")

        # Re-run criteria
        for c in phase.get("criteria", []):
            result = run_one_criterion(c)
            if not result["passed"]:
                failures.append(f"Criterion '{c['id']}' failed: {result['detail']}")

        ok = not failures
        all_ok = all_ok and ok
        report.append({"phase": pname, "ok": ok, "failures": failures})

    return {"all_ok": all_ok, "phases": report}


# ──────────────────────────────────────────────────────────
# set-phase-criteria  (add/replace criteria on an existing phase)
# ──────────────────────────────────────────────────────────

def cmd_refresh_hashes(slug: str, phase_name: Optional[str] = None) -> None:
    """Re-record sha256 hashes for all artifacts in complete phases.

    Use after a later phase legitimately modifies an artifact that an earlier
    phase also tracked. The criteria are re-run to confirm the phase still passes
    before accepting the new hashes.
    """
    state = cmd_read(slug)
    updated = False
    for phase in state["phases"]:
        if phase.get("status") != "complete":
            continue
        if phase_name and phase["name"] != phase_name:
            continue
        for art in phase.get("artifacts", []):
            apath = art.get("path", "")
            new_sha = sha256_file(apath)
            if new_sha and new_sha != art.get("sha256"):
                art["sha256"] = new_sha
                updated = True
    if updated:
        state["updated"] = now_iso()
        yaml_content = yaml.safe_dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False)
        atomic_write(state_yaml_path(slug), yaml_content)
        atomic_write(state_md_path(slug), render_state_md(state))


def cmd_set_phase_criteria(slug: str, phase_name: str, criteria: list) -> None:
    state = cmd_read(slug)
    for phase in state["phases"]:
        if phase["name"] == phase_name:
            phase["criteria"] = criteria
            break
    state["updated"] = now_iso()
    yaml_content = yaml.safe_dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write(state_yaml_path(slug), yaml_content)
    atomic_write(state_md_path(slug), render_state_md(state))


# ──────────────────────────────────────────────────────────
# find-in-flight
# ──────────────────────────────────────────────────────────

def cmd_find_in_flight() -> list:
    results = []
    if not PIPELINE_STATE_DIR.exists():
        return results
    for child in PIPELINE_STATE_DIR.iterdir():
        sy = child / "state.yaml"
        if not sy.exists():
            continue
        try:
            with open(sy, encoding="utf-8") as f:
                state = yaml.safe_load(f)
            if state.get("status") == "in-progress":
                results.append({
                    "slug": state["pipeline"],
                    "title": state.get("title", ""),
                    "current_phase": state.get("current_phase", ""),
                    "updated": state.get("updated", ""),
                })
        except Exception:
            continue
    results.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return results


# ──────────────────────────────────────────────────────────
# get-resume-point
# ──────────────────────────────────────────────────────────

def cmd_get_resume_point(slug: str) -> str:
    state = cmd_read(slug)
    for phase in state["phases"]:
        if phase.get("status") != "complete":
            return phase["name"]
    return ""


# ──────────────────────────────────────────────────────────
# render
# ──────────────────────────────────────────────────────────

def cmd_render(slug: str) -> None:
    state = cmd_read(slug)
    atomic_write(state_md_path(slug), render_state_md(state))


# ──────────────────────────────────────────────────────────
# import-plain  (for pre-existing plain-text STATE.md files like kai-thesis)
# ──────────────────────────────────────────────────────────

def cmd_import_plain(slug: str, title: str, plain_state_path: str,
                     artifact_paths: list, brief: Optional[str] = None) -> dict:
    plain_text = Path(plain_state_path).read_text(encoding="utf-8")
    ts = now_iso()
    artifacts = []
    for apath in artifact_paths:
        sha = sha256_file(apath)
        artifacts.append({"path": apath, "sha256": sha or "MISSING"})

    phases = [{
        "name": "imported",
        "status": "complete",
        "started": ts,
        "completed": ts,
        "artifacts": artifacts,
        "criteria_verdict": "imported — not re-verified",
        "criteria": [],
        "notes": plain_text[:500].strip(),
    }]

    state = {
        "pipeline": slug,
        "title": title,
        "status": "complete",
        "current_phase": "imported",
        "created": ts,
        "updated": ts,
        "phases": phases,
        "imported_from": plain_state_path,
    }
    if brief:
        state["brief"] = brief

    slug_dir(slug).mkdir(parents=True, exist_ok=True)
    yaml_content = yaml.safe_dump(state, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write(state_yaml_path(slug), yaml_content)
    atomic_write(state_md_path(slug), render_state_md(state))
    return state


# ──────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────

def self_test() -> int:
    import tempfile
    import shutil

    td = Path(tempfile.mkdtemp())
    test_slug = "__test_pipeline__"
    global PIPELINE_STATE_DIR
    original_dir = PIPELINE_STATE_DIR
    PIPELINE_STATE_DIR = td

    failures = []
    try:
        # T1: init creates state.yaml and STATE.md
        state = cmd_init(test_slug, "Test Pipeline", ["phase-a", "phase-b", "phase-c"],
                         brief="/tmp/fake-brief.md")
        sy = state_yaml_path(test_slug)
        sm = state_md_path(test_slug)
        if not sy.exists():
            failures.append("T1: state.yaml not created")
        if not sm.exists():
            failures.append("T1: STATE.md not created")
        if state["status"] != "in-progress":
            failures.append(f"T1: expected status=in-progress, got {state['status']}")
        print("T1 init: OK" if not failures else f"T1 init: FAIL {failures}")

        # T2: read round-trips
        read_state = cmd_read(test_slug)
        if read_state["pipeline"] != test_slug:
            failures.append(f"T2: pipeline slug mismatch: {read_state['pipeline']}")
        if len(read_state["phases"]) != 3:
            failures.append(f"T2: expected 3 phases, got {len(read_state['phases'])}")
        print("T2 read: OK" if "T2" not in str(failures) else "T2 read: FAIL")

        # T3: update-phase marks complete, advances current_phase
        cmd_update_phase(test_slug, "phase-a", "complete", artifacts=[])
        state2 = cmd_read(test_slug)
        pa = next(p for p in state2["phases"] if p["name"] == "phase-a")
        if pa["status"] != "complete":
            failures.append("T3: phase-a should be complete")
        if state2["current_phase"] != "phase-b":
            failures.append(f"T3: current_phase should be phase-b, got {state2['current_phase']}")
        print("T3 update-phase: OK" if "T3" not in str(failures) else "T3 update-phase: FAIL")

        # T4: verify detects missing artifact
        # Artificially inject an artifact that doesn't exist
        state3 = cmd_read(test_slug)
        for ph in state3["phases"]:
            if ph["name"] == "phase-a":
                ph["artifacts"] = [{"path": "/tmp/nonexistent_test_artifact_xyz.md", "sha256": "abc"}]
        yaml_content = yaml.safe_dump(state3, default_flow_style=False, allow_unicode=True, sort_keys=False)
        atomic_write(sy, yaml_content)

        verify_result = cmd_verify(test_slug, "phase-a")
        if verify_result["all_ok"]:
            failures.append("T4: verify should fail when artifact missing")
        if not any("missing" in f.lower() or "Artifact" in f for r in verify_result["phases"] for f in r["failures"]):
            failures.append("T4: verify should report missing artifact")
        print("T4 verify-missing: OK" if "T4" not in str(failures) else "T4 verify-missing: FAIL")

        # T5: find-in-flight returns our test pipeline
        in_flight = cmd_find_in_flight()
        slugs = [p["slug"] for p in in_flight]
        if test_slug not in slugs:
            failures.append(f"T5: find-in-flight should return {test_slug}, got {slugs}")
        print("T5 find-in-flight: OK" if "T5" not in str(failures) else "T5 find-in-flight: FAIL")

        # T6: get-resume-point returns first non-complete phase
        resume = cmd_get_resume_point(test_slug)
        if resume != "phase-b":
            failures.append(f"T6: resume point should be phase-b, got {resume!r}")
        print("T6 get-resume-point: OK" if "T6" not in str(failures) else "T6 get-resume-point: FAIL")

        # T7: shell criterion type works
        crit = {"id": "test-shell", "type": "shell", "command": "true", "description": "always pass"}
        result = run_one_criterion(crit)
        if not result["passed"]:
            failures.append("T7: shell criterion 'true' should pass")
        crit_fail = {"id": "test-shell-fail", "type": "shell", "command": "false", "description": "always fail"}
        result_fail = run_one_criterion(crit_fail)
        if result_fail["passed"]:
            failures.append("T7: shell criterion 'false' should fail")
        print("T7 shell-criterion: OK" if "T7" not in str(failures) else "T7 shell-criterion: FAIL")

        # T8: grep criterion type works
        tmp_file = td / "grep_test.md"
        tmp_file.write_text("## Risks\n- Risk one\n- Risk two\n")
        crit_grep = {"id": "grep-risks", "type": "grep", "file": str(tmp_file),
                     "pattern": "## Risks", "description": "risks section present"}
        result_grep = run_one_criterion(crit_grep)
        if not result_grep["passed"]:
            failures.append(f"T8: grep should find ## Risks: {result_grep}")
        crit_grep_fail = {"id": "grep-miss", "type": "grep", "file": str(tmp_file),
                          "pattern": "NOTFOUND_XYZ", "description": "pattern not present"}
        result_grep_fail = run_one_criterion(crit_grep_fail)
        if result_grep_fail["passed"]:
            failures.append("T8: grep for NOTFOUND_XYZ should fail")
        print("T8 grep-criterion: OK" if "T8" not in str(failures) else "T8 grep-criterion: FAIL")

        # T9: import-plain creates importable state
        kai_plain = td / "kai_plain.md"
        kai_plain.write_text("Phase 4-6 complete\n")
        artifact1 = td / "thesis.md"
        artifact1.write_text("x" * 200)
        imported = cmd_import_plain("__kai_import__", "KAI Thesis", str(kai_plain),
                                    [str(artifact1)])
        if imported["status"] != "complete":
            failures.append("T9: imported pipeline should be complete")
        verify_imported = cmd_verify("__kai_import__")
        if not verify_imported["all_ok"]:
            failures.append(f"T9: imported pipeline verify should pass: {verify_imported}")
        print("T9 import-plain: OK" if "T9" not in str(failures) else "T9 import-plain: FAIL")

    finally:
        PIPELINE_STATE_DIR = original_dir
        shutil.rmtree(td, ignore_errors=True)

    if failures:
        print(f"\n[FAIL] {len(failures)} test(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n[OK] All 9 self-tests pass")
    return 0


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Resumable pipeline state manager")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init")
    p_init.add_argument("--slug", required=True)
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--phases", required=True, help="Comma-separated phase names")
    p_init.add_argument("--brief")

    p_read = sub.add_parser("read")
    p_read.add_argument("slug")

    p_up = sub.add_parser("update-phase")
    p_up.add_argument("slug")
    p_up.add_argument("phase")
    p_up.add_argument("--status", required=True,
                      choices=["pending", "in-progress", "complete", "failed"])
    p_up.add_argument("--artifacts", nargs="*", default=None,
                      help="Artifact file paths")

    p_crit = sub.add_parser("run-criteria")
    p_crit.add_argument("slug")
    p_crit.add_argument("phase")

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("slug")
    p_ver.add_argument("phase", nargs="?")

    sub.add_parser("find-in-flight")

    p_rp = sub.add_parser("get-resume-point")
    p_rp.add_argument("slug")

    p_render = sub.add_parser("render")
    p_render.add_argument("slug")

    p_rh = sub.add_parser("refresh-hashes",
                          help="Re-record sha256 after later phases modify shared artifacts")
    p_rh.add_argument("slug")
    p_rh.add_argument("phase", nargs="?", help="Specific phase to refresh (default: all complete)")

    p_spc = sub.add_parser("set-phase-criteria")
    p_spc.add_argument("slug")
    p_spc.add_argument("phase")
    p_spc.add_argument("--criteria-json", required=True,
                       help="JSON array of criterion objects")

    p_imp = sub.add_parser("import-plain")
    p_imp.add_argument("--slug", required=True)
    p_imp.add_argument("--title", required=True)
    p_imp.add_argument("--plain-state", required=True)
    p_imp.add_argument("--artifacts", nargs="*", default=[])
    p_imp.add_argument("--brief")

    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if args.cmd == "init":
        phases = [p.strip() for p in args.phases.split(",") if p.strip()]
        state = cmd_init(args.slug, args.title, phases, brief=args.brief)
        print(f"Pipeline initialized: {state_yaml_path(args.slug)}")
        print(f"STATE.md:             {state_md_path(args.slug)}")

    elif args.cmd == "read":
        state = cmd_read(args.slug)
        print(yaml.safe_dump(state, default_flow_style=False, allow_unicode=True))

    elif args.cmd == "update-phase":
        state = cmd_update_phase(args.slug, args.phase, args.status,
                                 artifacts=args.artifacts)
        print(f"Phase '{args.phase}' → {args.status}")
        print(f"Pipeline status: {state['status']}, current: {state['current_phase']}")

    elif args.cmd == "run-criteria":
        result = cmd_run_criteria(args.slug, args.phase)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    elif args.cmd == "verify":
        result = cmd_verify(args.slug, args.phase)
        for ph in result["phases"]:
            icon = "✓" if ph["ok"] else "✗"
            print(f"  {icon} {ph['phase']}")
            for f in ph["failures"]:
                print(f"      ! {f}")
        if result["all_ok"]:
            print("All verified OK")
        else:
            print("Verification FAILED — see above")
            sys.exit(1)

    elif args.cmd == "find-in-flight":
        results = cmd_find_in_flight()
        if not results:
            print("No in-flight pipelines found.")
        else:
            print(json.dumps(results, indent=2))

    elif args.cmd == "get-resume-point":
        point = cmd_get_resume_point(args.slug)
        if point:
            print(point)
        else:
            print("(all phases complete)")

    elif args.cmd == "render":
        cmd_render(args.slug)
        print(f"STATE.md rendered: {state_md_path(args.slug)}")

    elif args.cmd == "refresh-hashes":
        cmd_refresh_hashes(args.slug, getattr(args, "phase", None))
        print(f"Artifact hashes refreshed for pipeline '{args.slug}'")

    elif args.cmd == "set-phase-criteria":
        criteria = json.loads(args.criteria_json)
        cmd_set_phase_criteria(args.slug, args.phase, criteria)
        print(f"Criteria set for phase '{args.phase}' ({len(criteria)} criteria)")

    elif args.cmd == "import-plain":
        state = cmd_import_plain(args.slug, args.title, args.plain_state,
                                 args.artifacts, brief=args.brief)
        print(f"Imported pipeline: {state_yaml_path(args.slug)}")
        print(f"STATUS: {state['status']}")

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
