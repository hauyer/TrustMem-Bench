# TrustMem-Bench 1.0.0-rc7.3

This supplementary review package contains the native audit code, aggregate paper tables, publication figure PDFs/SVGs, table-number mapping, and hash-pinned upstream reproduction recipes for *Does Making a Historical Receipt Available Avoid Its Verification Cost? Counterfactual Auditing of Agent Memory under Shared Budgets*.

## Quick checks (stdlib only, <5 seconds, 0 GPU, 0 API)

Install Python 3.11 or newer and Git. Standard-library Python runs `reproduce.py verify` and `trustmem_bench/p3_submission.py`. Native upstream P3/P4/P4b simulation requires `python -m pip install -r requirements.txt` (`jsonschema==4.26.0`), and redrawing publication figures requires `matplotlib` (e.g., `matplotlib==3.10.8`).

```sh
python reproduce.py verify
```

The verification command checks all packaged file digests against `RELEASE_LOCK.json` and recomputes cross-table consistency checks across P3, P4, P4b, SkillHorizon, and `tables/FIGURE_DATA.json` (including `Forms T14` and `Railway Ticketing`).

## Manuscript table & figure map (`tables/TABLE_NUMBER_MAP.csv`)

| Manuscript artifact | Packaged data / verification source | Notes |
|---|---|---|
| Figure 1b (`Forms T14`) | `tables/FIGURE_DATA.json`, `tables/NATIVE_OPENINGS.csv` | Same opening, 5-unit reread, `keep` repeats + `sham` agree (`Llama` 1/1/2, `Mistral` 3/1/1, `Qwen` 1/1 swap) |
| Tables 2–5, 11 (P3 & diagnosis) | `tables/P3_*.csv`, `reproduce.py p3` | Rebuilt from pinned upstream ReScopeBench + SkillHorizon; 128 total pairs (112 released), 68 fee pairs (60 released) |
| Table 6 & Figure 3a–c (P4 released) | `tables/P4_NATIVE_MODELS.csv`, `tables/FIGURE_DATA.json` | 12 released P4 openings per model (`forms`, `medical_appointment`); `fee_outside_additions` uses all verified fee branches (e.g., Mistral 5/11) |
| Table 7 (receipt vs. single fee waiver) | `tables/NATIVE_OPENINGS.csv`, `tables/NATIVE_CONTROL_STRATA.csv`, `tables/RECEIPT_FEE_PAIRED.csv` | Stratified by control availability: P3 `68` (all five) / `60` (released four); P4 sham-matched `25`; P4b sham-matched `4`; P4b sham-unavailable `14` (`29` sham-matched span `15` distinct openings in `3` workflows; `8` fee-only outside gains span `5` openings; `5` receipt-only span `5` openings) |
| Tables 8–9 & Figure 3d–f (P4/P4b arms) | `tables/ARCHIVE_THREE_ARMS.csv`, `tables/NATIVE_OPENINGS.csv`, `tables/FIGURE_DATA.json` | Forms 24 requests/arm, Railway Ticketing 32 requests/arm (`0/8` sham), Qwen menu vs. native on Forms |

*Denominator clarification*: `tables/RECEIPT_FEE_PAIRED.csv` keeps the legacy P3 `all_five` row (`68`, including candidate `api_reliability`) alongside the three P4 released-workflow rows (`25` sham-matched total: Qwen `8`, Llama `11`, Mistral `6`). Notice Mistral has `11` verified fee branches in Table 6 / Figure 3c (`5/11` fee outside additions) of which `6` pass both `keep`-repeat and `sham` agreement in Table 7 (`3` receipt-only + `3` three-distinct, `0` fee-only).

## Redraw the figures from aggregate data

Install Matplotlib (`3.10.x`), then run:

```sh
python scripts/plot_trustmem_submission.py --data tables/FIGURE_DATA.json --out rendered
```

(If `--data` is omitted inside the extracted review archive, the script automatically falls back to `tables/FIGURE_DATA.json`.)

## Rebuild the P3 native adjudication (~30–50 minutes on CPU)

```sh
python reproduce.py p3 --out native-p3
```

`reproduce.py p3` retrieves 417 pinned ReScopeBench files by immutable URL and SHA-256 (with automatic per-file retries and resumable caching via optional `--cache-dir DIR` or `--p3-sources DIR`) and checks out the pinned SkillHorizon revision (`1749e7439fdafb75426d7bfecbd4b657509ebe1c`, or local `--skill-checkout DIR`). Expected runtime on a single CPU workstation is **30–50 minutes** after downloads complete.

`docs/P3_EXTERNAL_DIAGNOSIS.md` documents the standalone single-trajectory prediction interface (`export`, `run`, `score`) using `--archive native-p3/organizer-p3.zip`. Note that `"RC6"` inside `p3_submission.py` refers to the immutable sealed P3 adjudication cohort (198 locked files) rebuilt verbatim by this `1.0.0-rc7.3` recipe.

## Rebuild and replay P4 and P4b (CPU replay; raw tapes requested separately)

What you can verify **using only this public package**:
1. Integrity of all packaged files, scripts, and table cross-checks (`python reproduce.py verify`).
2. Full native reconstruction of P3 (198 locked files), SkillHorizon C95/C96 cutoffs, and end-to-end single-trajectory participant evaluation (`export` -> custom predictor -> `score`).
3. Full recomputation of all Table 7 autonomous-model denominators (`25 / 4 / 14`, `29` sham-matched across `15` openings) from `tables/NATIVE_OPENINGS.csv`, plus figure redrawing from `tables/FIGURE_DATA.json`.
4. Reconstruction of the frozen P4 (`261` files) and P4b (`210` files) runtimes for executing fresh inference against your own OpenAI-compatible model endpoint.

What requires **separately requested raw model recordings** (`p4_all_results.tar.gz`, SHA-256 `d86e8da54d101a1b8a88721285496fe7bb7bb45a4b34f4fe3df36c8de5f7ada6`; `p4b_all_results.tar.gz`, SHA-256 `f2347193cffaec118a6d68f5f3942ac75f097c4bfe088e82f07fb924b25015fd`):
- Deterministic zero-GPU replay of recorded P4 (`450` branches) and P4b (`396` branches) model tapes, or recounting `tables/NATIVE_OPENINGS.csv` from single episode logs.
- Requests for these recordings and associated scoring reports may be addressed to the corresponding author at the email on the manuscript title page, specifying the run and intended use, subject to applicable upstream terms.

```sh
# P4 runtime staging & recorded replay (with separately obtained P4 tapes)
python reproduce.py stage-p4 --out p4-runtime
python p4-runtime/run_p4_modelscope_audit.py replay --run-dir /path/to/permitted-p4-tape-dir --out p4-replay
python p4-runtime/p4_review_scores.py --run-dir /path/to/permitted-p4-tape-dir --replay-report p4-replay/REPLAY_VERIFICATION.json --out strict-p4.json
python scripts/paired_receipt_fee.py --scores /path/to/scores --runs /path/to/p4_runs --p3-table tables/P3_NATIVE_CONTROLS.csv --out recounted

# P4b runtime staging & recorded replay (with separately obtained P4b tapes)
python reproduce.py stage-p4b --p3-run native-p3 --out native-p4b
python native-p4b/run_p4b_p3_extension.py replay --run-dir /path/to/permitted-p4b-tape-dir --out p4b-replay
python scripts/receipt_fee_extension.py --p4 /path/to/p4_all_results.tar.gz --p4b /path/to/p4b_all_results.tar.gz --out raw-recount
```

## Rebuild the SkillHorizon integration evidence

```sh
python reproduce.py skillhorizon --out native-skill
```

Checks out the pinned revision (`1749e7439fdafb75426d7bfecbd4b657509ebe1c`, or `--skill-checkout DIR`) and regenerates C95 and C96 locally, verifying the 150-cutoff digest against `locks/NATIVE_EXPECTED.json`.

## Provenance note on packaged protocol logs

All user-facing instructions (`README.md`, `docs/EVALUATION_CARD.md`, `docs/P3_EXTERNAL_DIAGNOSIS.md`, `THIRD_PARTY_NOTICES.md`) are in English. Several historical freeze protocol documents under `experiments/memory_correctability/` and `modules/p4/` are preserved verbatim in their original authoring language (Chinese) to maintain hash-locked provenance; use `reproduce.py` and the English docs above for all execution commands.
