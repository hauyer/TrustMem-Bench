#!/usr/bin/env bash
set -euo pipefail

# Fully automated ModelScope 192GB AMD GPU runner for TrustMem-Bench P4b (P3 Official Extension).
# Workflows: backup_recovery (all 10 P3 openings: T05, T06, T08-T15) + railway_ticketing (T09-T16).
# Models: identical 3 open-weight families as P4 (Qwen3-32B, Mistral-Small-24B, Llama-3.3-70B).
# Runs: Gate 2 Qualification (backup_recovery-T11) -> 18-Opening Matrix -> Zero-GPU Replay -> Summary -> Tarball.
#
# Usage:
#   nohup bash /mnt/workspace/p4b_audit/run_all_amd_p4b.sh > /mnt/workspace/p4b_master.log 2>&1 &
#   tail -f /mnt/workspace/p4b_master.log
#
# Optional env overrides:
#   SLOTS="A C B"                 (default: "A C B" — 32B/24B first, 70B last)
#   SUITE="all"                   (default: "all"; or "backup_recovery" / "railway_ticketing")
#   CLEAN_WEIGHTS=1               (default: 1 — remove temp model weights after each slot)
#   RUNS_DIR=/mnt/workspace/p4b_runs
#   PORT=8000

AUDIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNS_DIR="${RUNS_DIR:-/mnt/workspace/p4b_runs}"
LOG_DIR="${RUNS_DIR}/logs"
PORT="${PORT:-8000}"
BASE_URL="http://127.0.0.1:${PORT}/v1"
CLEAN_WEIGHTS="${CLEAN_WEIGHTS:-1}"
SLOTS="${SLOTS:-A C B}"
SUITE="${SUITE:-all}"
VLLM_PID=""

mkdir -p "${RUNS_DIR}" "${LOG_DIR}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

stop_vllm() {
  if [[ -n "${VLLM_PID}" ]] && kill -0 "${VLLM_PID}" 2>/dev/null; then
    log "Stopping vLLM (PID=${VLLM_PID})..."
    kill "${VLLM_PID}" 2>/dev/null || true
    for _ in $(seq 1 30); do
      if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        break
      fi
      sleep 2
    done
    kill -9 "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
    VLLM_PID=""
    sleep 8
  fi
}

trap stop_vllm EXIT

free_gb() {
  df -BG --output=avail "$1" 2>/dev/null | tail -n 1 | tr -dc '0-9'
}

pick_weights_root() {
  local best_dir="/mnt/workspace/p4b_models_tmp"
  local best_gb=0
  for candidate in /tmp /root /mnt/workspace; do
    if [[ -d "${candidate}" && -w "${candidate}" ]]; then
      local g
      g="$(free_gb "${candidate}")"
      g="${g:-0}"
      if (( g > best_gb )); then
        best_gb="${g}"
        best_dir="${candidate}/p4b_models_tmp"
      fi
    fi
  done
  mkdir -p "${best_dir}"
  echo "${best_dir}"
}

download_model() {
  local repo_id="$1"
  local target_dir="$2"
  log "Downloading ${repo_id} -> ${target_dir}..."
  for attempt in 1 2 3; do
    if modelscope download --model "${repo_id}" --local_dir "${target_dir}"; then
      return 0
    fi
    log "Download attempt ${attempt} failed for ${repo_id}; retrying in 10s..."
    sleep 10
  done
  return 1
}

start_vllm() {
  local model_dir="$1"
  local served_name="$2"
  local parser="$3"
  local extra_flags="$4"
  local log_file="$5"

  stop_vllm
  log "Starting vLLM: model=${served_name}, parser=${parser}, log=${log_file}"
  # shellcheck disable=SC2086
  vllm serve "${model_dir}" \
    --served-model-name "${served_name}" \
    --host 127.0.0.1 --port "${PORT}" \
    --enable-auto-tool-choice --tool-call-parser "${parser}" \
    --max-model-len 24576 --dtype bfloat16 \
    --gpu-memory-utilization 0.90 \
    ${extra_flags} > "${log_file}" 2>&1 &
  VLLM_PID=$!

  local waited=0
  local max_wait=2400
  while (( waited < max_wait )); do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
      log "ERROR: vLLM exited prematurely! Last 50 lines of ${log_file}:"
      tail -n 50 "${log_file}" || true
      VLLM_PID=""
      return 1
    fi
    if curl -sf --noproxy '*' "http://127.0.0.1:${PORT}/v1/models" | grep -q "${served_name}"; then
      log "vLLM ready for ${served_name} after ${waited}s."
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done
  log "ERROR: Timed out waiting ${max_wait}s for vLLM (${served_name}). Last 40 lines:"
  tail -n 40 "${log_file}" || true
  stop_vllm
  return 1
}

qualify_passed() {
  local verdict_json="$1"
  python3 -c "import json, sys; d=json.load(open(sys.argv[1], encoding='utf-8')); sys.exit(0 if d.get('passed') else 1)" "${verdict_json}"
}

run_one_slot() {
  local slot="$1"
  local repo_id="$2"
  local parser="$3"
  local need_gb="$4"
  local extra_vllm_flags="$5"
  local extra_body="$6"

  local safe_name
  safe_name="$(echo "${repo_id}" | tr '/:' '__')"
  local model_dir="${WEIGHTS_ROOT}/${safe_name}"
  local qual_dir="${RUNS_DIR}/p4b_slot${slot}_${safe_name}_qualify"
  local main_dir="${RUNS_DIR}/p4b_slot${slot}_${safe_name}_main"
  local vllm_log="${LOG_DIR}/p4b_slot${slot}_${safe_name}_vllm.log"

  log "============================================================"
  log "P4b SLOT ${slot}: ${repo_id} (parser=${parser}, suite=${SUITE}, need~${need_gb}GB)"
  log "============================================================"

  if [[ -f "${main_dir}_replay_check/REPLAY_VERIFICATION.json" ]]; then
    log "Slot ${slot} (${repo_id}) already completed and replay-verified. Skipping."
    return 0
  fi

  local avail
  avail="$(free_gb "${WEIGHTS_ROOT}")"
  log "Free disk in ${WEIGHTS_ROOT}: ${avail} GB (needed: ${need_gb} GB)"
  if (( avail < need_gb )) && [[ ! -d "${model_dir}" ]]; then
    log "SKIP: Not enough disk space (${avail}GB < ${need_gb}GB) for ${repo_id}."
    return 2
  fi

  if ! download_model "${repo_id}" "${model_dir}"; then
    log "ERROR: Could not download ${repo_id}."
    return 1
  fi

  if ! start_vllm "${model_dir}" "${repo_id}" "${parser}" "${extra_vllm_flags}" "${vllm_log}"; then
    log "ERROR: vLLM failed to start for ${repo_id}."
    if [[ "${CLEAN_WEIGHTS}" == "1" ]]; then
      rm -rf "${model_dir}"
    fi
    return 1
  fi

  local common_args=(--base-url "${BASE_URL}" --model "${repo_id}" --slot "${slot}" --max-output-tokens 384)
  if [[ -n "${extra_body}" ]]; then
    common_args+=(--extra-body "${extra_body}")
  fi

  log "Running P4b Gate 2 qualification (backup_recovery-T11) for Slot ${slot}..."
  python3 "${AUDIT_DIR}/run_p4b_p3_extension.py" qualify "${common_args[@]}" --out "${qual_dir}"

  if qualify_passed "${qual_dir}/QUALIFICATION_VERDICT.json"; then
    log "Gate 2 PASSED for Slot ${slot}. Running P4b suite=${SUITE}..."
    python3 "${AUDIT_DIR}/run_p4b_p3_extension.py" run "${common_args[@]}" --suite "${SUITE}" --out "${main_dir}"
  else
    log "Gate 2 DISQUALIFIED for Slot ${slot} (${repo_id}). Skipping full matrix and retaining verdict."
  fi

  stop_vllm

  log "Running zero-GPU offline replay verification for Slot ${slot}..."
  python3 "${AUDIT_DIR}/run_p4b_p3_extension.py" replay \
    --run-dir "${qual_dir}" --out "${qual_dir}_replay_check"
  if [[ -d "${main_dir}" ]]; then
    python3 "${AUDIT_DIR}/run_p4b_p3_extension.py" replay \
      --run-dir "${main_dir}" --out "${main_dir}_replay_check"
  fi

  if [[ "${CLEAN_WEIGHTS}" == "1" ]]; then
    log "Cleaning temporary model weights at ${model_dir}..."
    rm -rf "${model_dir}"
  fi
  return 0
}

# ==================== Startup Environment Checks ====================
log "Starting TrustMem-Bench P4b Automated Multi-Model Pipeline (backup_recovery + railway_ticketing)"
df -h /mnt/workspace /tmp / || true
rocm-smi || amd-smi || nvidia-smi || true
python3 -c "import torch; print('torch:', torch.__version__, 'hip:', getattr(torch.version, 'hip', None), 'avail:', torch.cuda.is_available(), 'count:', torch.cuda.device_count())"

if ! command -v modelscope >/dev/null 2>&1; then
  log "Installing modelscope CLI..."
  pip install -q modelscope
fi

if ! python3 -c "import vllm" >/dev/null 2>&1; then
  log "vLLM not detected; installing..."
  pip install -q vllm
fi
python3 -c "import vllm; print('vllm version:', vllm.__version__)"

cd "${AUDIT_DIR}"
python3 "${AUDIT_DIR}/run_p4b_p3_extension.py" verify-bundle

WEIGHTS_ROOT="$(pick_weights_root)"
log "Selected temp model weight cache: ${WEIGHTS_ROOT} (free: $(free_gb "${WEIGHTS_ROOT}") GB)"

# ==================== Execute Requested Slots (Exact P4 3-Family Checkpoints) ====================
for slot in ${SLOTS}; do
  case "${slot}" in
    A)
      run_one_slot "A" "Qwen/Qwen3-32B" "hermes" 75 "" '{"chat_template_kwargs":{"enable_thinking":false}}' || true
      ;;
    C)
      run_one_slot "C" "mistralai/Mistral-Small-24B-Instruct-2501" "mistral" 55 "" "" || true
      ;;
    B)
      run_one_slot "B" "LLM-Research/Llama-3.3-70B-Instruct" "llama3_json" 155 "" "" || true
      ;;
    *)
      log "Unknown slot '${slot}', skipping."
      ;;
  esac
done

# ==================== Master Summary & Final Tarball ====================
log "Building P4b cross-model master summary..."
python3 "${AUDIT_DIR}/summarize_p4_matrix.py" --runs-dir "${RUNS_DIR}" --out-dir "${RUNS_DIR}"
cat "${RUNS_DIR}/P4_MASTER_SUMMARY.md" || true

FINAL_TAR="/mnt/workspace/p4b_all_results.tar.gz"
log "Packaging all P4b results into ${FINAL_TAR}..."
tar -czf "${FINAL_TAR}" -C "$(dirname "${RUNS_DIR}")" "$(basename "${RUNS_DIR}")"
ls -lh "${FINAL_TAR}"
log "ALL DONE! Download ${FINAL_TAR} back to your local machine (and remember to STOP the AMD GPU instance)."
