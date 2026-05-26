#!/usr/bin/env bash
# Sentinel: security-process-anomaly
# Detects unexpected user-owned processes and unfamiliar listening ports
# by comparing against an allowlist baseline. Conservative: starts INFO/
# approval tier; promote severity after baselining real traffic.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/common.sh"
parse_dry_run_flag "$@"

BASELINE_DIR="${HOME}/.openclaw/sentinels/baseline/process-anomaly"
PROCESS_ALLOWLIST="${BASELINE_DIR}/process-allowlist.txt"
PORT_ALLOWLIST="${BASELINE_DIR}/port-allowlist.txt"
mkdir -p "$BASELINE_DIR" 2>/dev/null || true

check_process_allowlist() {
  # Snapshot process comm names owned by current user (deduped)
  local current
  current=$(ps -u "$USER" -o comm= 2>/dev/null | sort -u | grep -v '^$' || true)
  if [[ -z "$current" ]]; then
    write_result "process_allowlist" "warn" "WARNING" "security" \
      "ps returned no processes for user ${USER}" "approval" "" "Check ps tool availability"
    return 1
  fi

  if [[ ! -r "$PROCESS_ALLOWLIST" ]]; then
    if is_dry_run; then
      log "[security-process-anomaly] DRY-RUN: would initialize process allowlist"
    else
      echo "$current" > "$PROCESS_ALLOWLIST"
    fi
    local count
    count=$(echo "$current" | wc -l)
    write_result "process_allowlist" "pass" "INFO" "security" \
      "Process allowlist initialized with ${count} baseline entries" "auto" "" "" \
      "{\"baseline_initialized\": true}"
    return 0
  fi

  local unknown
  unknown=$(comm -23 <(echo "$current") <(sort -u "$PROCESS_ALLOWLIST"))
  if [[ -z "$unknown" ]]; then
    write_result "process_allowlist" "pass" "INFO" "security" \
      "All running processes match allowlist" "auto" "" ""
    return 0
  fi

  local joined
  joined=$(echo "$unknown" | head -10 | tr '\n' ',' | sed 's/,$//')
  local count
  count=$(echo "$unknown" | wc -l)
  write_result "process_allowlist" "warn" "WARNING" "security" \
    "${count} non-allowlisted user process(es): ${joined}" "approval" \
    "" "Review processes. If benign: append to ${PROCESS_ALLOWLIST}. If suspicious: kill via 'pkill <name>' and investigate." \
    "{\"iocs\": [\"process_names:${joined}\"], \"mitre_id\": \"T1059\", \"dedup_key\": \"process_allowlist_$(echo \"$joined\" | sha256sum | head -c 12)\"}"
  return 1
}

check_port_anomaly() {
  # Local listening ports owned by current user
  local current
  # grep before sort: filter to valid port numbers first, then sort -u (not -un)
  # comm -23 requires lexicographic order; -n would produce numeric order, breaking
  # the comparison for ports like [9,10,11] where lex and numeric order diverge.
  current=$(ss -tnlp 2>/dev/null | awk 'NR>1 {split($4,a,":"); print a[length(a)]}' | grep -E '^[0-9]+$' | sort -u || true)
  if [[ -z "$current" ]]; then
    write_result "port_anomaly" "pass" "INFO" "security" \
      "No listening TCP ports" "auto" "" ""
    return 0
  fi

  if [[ ! -r "$PORT_ALLOWLIST" ]]; then
    if is_dry_run; then
      log "[security-process-anomaly] DRY-RUN: would initialize port allowlist"
    else
      echo "$current" > "$PORT_ALLOWLIST"
    fi
    write_result "port_anomaly" "pass" "INFO" "security" \
      "Port allowlist initialized" "auto" "" "" "{\"baseline_initialized\": true}"
    return 0
  fi

  local unknown
  unknown=$(comm -23 <(echo "$current") <(sort -u "$PORT_ALLOWLIST"))
  if [[ -z "$unknown" ]]; then
    write_result "port_anomaly" "pass" "INFO" "security" \
      "All listening ports match allowlist" "auto" "" ""
    return 0
  fi

  local joined
  joined=$(echo "$unknown" | tr '\n' ',' | sed 's/,$//')
  write_result "port_anomaly" "warn" "WARNING" "security" \
    "Non-allowlisted listening port(s): ${joined}" "approval" \
    "" "Identify process: 'ss -tnlp sport = :PORT'. If benign: append to ${PORT_ALLOWLIST}. If rogue: kill the owning process." \
    "{\"iocs\": [\"ports:${joined}\"], \"mitre_id\": \"T1571\", \"dedup_key\": \"port_anomaly_${joined}\"}"
  return 1
}

check_parent_process_anomaly() {
  # Conservative: only flag user-owned processes whose parent is PID 1 (systemd)
  # and whose command isn't in the allowlist. PPID=1 + unknown comm = potential
  # daemonized rogue.
  if [[ ! -r "$PROCESS_ALLOWLIST" ]]; then
    write_result "parent_process_anomaly" "pass" "INFO" "security" \
      "Skipped: process allowlist not yet initialized" "auto" "" ""
    return 0
  fi
  local orphans
  orphans=$(ps -u "$USER" -o ppid,comm --no-headers 2>/dev/null | \
    awk '$1=="1" {print $2}' | sort -u | grep -v '^$' || true)
  if [[ -z "$orphans" ]]; then
    write_result "parent_process_anomaly" "pass" "INFO" "security" \
      "No user processes with PPID=1" "auto" "" ""
    return 0
  fi
  local unknown
  unknown=$(comm -23 <(echo "$orphans") <(sort -u "$PROCESS_ALLOWLIST"))
  if [[ -z "$unknown" ]]; then
    write_result "parent_process_anomaly" "pass" "INFO" "security" \
      "All PPID=1 processes are allowlisted" "auto" "" ""
    return 0
  fi
  local joined
  joined=$(echo "$unknown" | tr '\n' ',' | sed 's/,$//')
  write_result "parent_process_anomaly" "warn" "WARNING" "security" \
    "Daemonized non-allowlisted process(es): ${joined}" "approval" \
    "" "PPID=1 implies a daemon. Verify it's expected; if rogue, kill and audit how it was spawned." \
    "{\"iocs\": [\"daemons:${joined}\"], \"mitre_id\": \"T1543\"}"
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  is_dry_run && log "[security-process-anomaly] DRY-RUN mode"
  check_process_allowlist       &
  check_port_anomaly            &
  check_parent_process_anomaly  &
  wait
  log "[security-process-anomaly] complete"
fi
