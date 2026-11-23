# P4b Protocol: Multi-Family Autonomous Native Tool-Calling Audit on P3 Official Released Workflows (`backup_recovery` & `railway_ticketing`)

- **Experiment ID**: `P4B_P3_OFFICIAL_WORKFLOWS_NATIVE_AUDIT`
- **Status**: Pre-registered & frozen before GPU execution
- **External Paid API Spend Cap**: **`USD 0.00`** (`paid_api_funding_approved = false`, `api_usd_cap = 0`; executed locally via vLLM on ModelScope free 192GB AMD GPU)
- **Non-interference**: Zero edits to frozen P4 code/manifests (`native_audit.py`, `run_p4_modelscope_audit.py`, `P4_MODELSCOPE_FREEZE.json`) and zero edits to Task 1 manuscript files.

---

## 1. Scientific Motivation & Competing Hypotheses

In P4 (`forms` T11–T16, `medical_appointment` T11–T16, `api_reliability` T09–T16), three open-weight LLM families (`Qwen/Qwen3-32B`, `LLM-Research/Llama-3.3-70B-Instruct`, `mistralai/Mistral-Small-24B-Instruct-2501`) demonstrated cross-request spillover under unconstrained native tool calling (`450/450` zero-GPU replay match, `0` parse errors across `2,982` turns). However, a strict reviewer can still ask:

> *Only one of P4's two officially released workflows (`medical_appointment`) came from the prospective P3 cohort. Do autonomous native tool-calling LLMs also exhibit cross-request spillover—and especially the P3 headline `backup_recovery-T08` non-monotonic fee reversal (`2/4 -> 1/4`) and fixed-order admission swaps (`T09`, `T12`, `T15`)—on P3's two largest officially released workflows (`backup_recovery` and `railway_ticketing`)?*

### Competing Hypotheses

- **`H-DevOnly` (Null / Development-Artifact Hypothesis)**: Cross-request spillover under autonomous native tool calling is confined to small-tool-count development/medical workflows (`3–4` tools) and disappears—or collapses into tool-schema failure—on P3's larger multi-tool released workflows (`backup_recovery`, `14` tools; `railway_ticketing`, `18` tools); in particular, autonomous LLMs never reproduce non-monotonic fee-waiver loss or outside-scope rescue on `backup_recovery` or `railway_ticketing`.
- **`H-P3Close` (P3–P4 Closure Hypothesis)**: Across the exact frozen P3 opening snapshots of `backup_recovery` (all `10` P3 openings) and `railway_ticketing` (first `8` contiguous P3 openings), autonomous native tool-calling models from multiple families exhibit verifiable outside-scope completion changes under paired receipt removal and/or single-charge `fee_only` waivers (with `100%` non-accounting tool-response invariance and `0` offline replay mismatches), while exposing concrete family-level differences in passive-memory compliance, active `lookup_archive` usage, and behavior on `backup_recovery-T08` / `T09` / `T12` / `T15`.

---

## 2. Frozen Cohort (18 Openings, 100% Upstream-Released P3 Official Workflows)

No cherry-picking: we take **all `10` P3 eligible openings** of `backup_recovery` and the **first `8` contiguous P3 eligible openings** of `railway_ticketing`, directly from the frozen P3 checkpoints in `artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/CHECKPOINTS/`:

1. **`backup_recovery`** (`ReleasedCase`, `14` native tools, budget `126`, focal tool `search_protection_policy_evidence` [cost `20`]):
   - `T05`, `T06`, **`T08`** *(P3 non-monotonic fee reversal `2/4 -> 1/4`)*, **`T09`** *(P3 admission swap)*, `T10`, `T11`, **`T12`** *(P3 admission swap)*, `T13`, `T14`, **`T15`** *(P3 admission swap)*.
   - Exact P3 `focal_key`, `direct_targets`, and `sham_key` (`5/10` openings have `sham`: `T05`, `T10`, `T11`, `T13`, `T14`; `5/10` have `sham = None`: `T06`, `T08`, `T09`, `T12`, `T15`).
2. **`railway_ticketing`** (`ReleasedCase`, `18` native tools, budget `48`, focal tool `list_stations` [cost `8`]):
   - Contiguous prefix **`T09`–`T16`** (`8` openings; includes P3 fee gains `T11, T12, T14, T15`, P3 order interactions `T11, T12, T14`, P3 swap `T13`, and P3 unchanged `T10, T16`).
   - Exact P3 `focal_key` and `direct_targets`; `sham_key = None` on all `8` openings (identical to P3, because all `4` cached origin stations appear in the batch).

### Arms Per Opening

- `keep_r0`, `keep_r1`, `keep_r2` (`3` repeatability controls with full opening memory)
- `sham` (run where `sham_key is not None`; cleanly recorded as `ineligible_no_sham_key` otherwise)
- `remove` (designated `focal_key` removed from `active_memory`)
- `archive` (designated `focal_key` removed from `active_memory`; zero-cost content-addressed `lookup_archive` tool exposed)
- `fee_only` (prefix-pinned post-charge counterfactual fork derived from `remove`; waives ONLY the first same-value positive-charge reread of `focal_key`, asserting `charged == 0` and exact non-accounting tool response match)

---

## 3. Model Matrix (Identical 3 Open-Weight Families as P4)

| Slot | Model Checkpoint | vLLM Tool Parser | Serving Config |
|---|---|---|---|
| **Slot A** | `Qwen/Qwen3-32B` | `hermes` | BF16, `--max-model-len 24576`, `enable_thinking=false`, `temperature=0.0`, `max_output_tokens=384` |
| **Slot C** | `mistralai/Mistral-Small-24B-Instruct-2501` | `mistral` | BF16, `--max-model-len 24576`, `temperature=0.0`, `max_output_tokens=384` |
| **Slot B** | `LLM-Research/Llama-3.3-70B-Instruct` | `llama3_json` | BF16, `--max-model-len 24576`, `max_wait=2400s`, `temperature=0.0`, `max_output_tokens=384` |

---

## 4. Stopping Gates & Verification Rules

- **Gate 0 (Local Offline Verification)**: `test_native_llm_audit_p4b.py` passes `100%` on real ReScopeBench drivers—explicitly verifying `backup_recovery-T08` non-monotonic `2/4 -> 1/4` fee waiver, `backup_recovery-T05` sham/archive/fee_only, `railway_ticketing-T11` `3/4 -> 2/4 -> 3/4` rescue, and clean-room ZIP unpack (`verify-bundle` + `replay`: `0` mismatches).
- **Gate 2 (Per-Slot Interface Smoke on `backup_recovery-T11`)**: All 3 P4b checkpoints already passed P4 Gate 2 (`0.0%` parse errors across `2,982` turns). P4b smoke qualification verifies `parse_error_rate <= 0.25` and valid grading across `backup_recovery-T11` while logging `keep_r0`, `keep_r1`, `remove`, and `archive` completions (avoiding false disqualification when passive memory causes `keep = 0/4` while `remove = 1/4`, as observed on `Qwen3-32B` initial smoke). Tool schemas passed to vLLM strip only `"uniqueItems"` (unimplemented in vLLM xgrammar on Mistral) while keeping the simulator's native `jsonschema.validate` strictly unchanged.
- **Zero-GPU Replay Gate**: Every recorded branch across all completed slots must verify with `0` mismatches via `RecordedReplayAdapter` on BOTH ModelScope Linux and local Windows 11.
- **Honest Null/Failure Retention**: All zero-completion workflows, `sham`-unavailable denominators, `keep` instabilities, and non-monotonic cells are reported transparently alongside exact denominators.
