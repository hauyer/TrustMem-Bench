# TrustMem-Bench

Supporting code, executable benchmark release (`RC7.3`), per-arm completed request-set review table, and publication figures for:

> **Do Receipt Restoration and Verification Fee Waivers Deliver the Same Requests? Auditing Agent Memory under Shared Budgets**  
> **Authors:** Hao Zhou\*, Xinyuan Li  
> **Affiliation:** Beijing University of Posts and Telecommunications, Beijing, China  
> **Corresponding author:** Hao Zhou (`2024212291@bupt.cn`)  
> **Target journal:** *Applied Intelligence*

---

## Repository Layout

| Path | Description |
|---|---|
| `article/NATIVE_REQUEST_SETS_REVIEW.csv` | 90-row per-arm completed request-set identity table covering all P4 (36) and P4b (54) model × opening combinations (`{}` = zero delivered requests; `NA` = unavailable arm or repeat). |
| `article/verify_table7_from_request_sets.py` | Zero-dependency Python stdlib verifier that independently re-adjudicates Table 7 directly from completed request-set identities (rather than completion counts). |
| `article/Fig1.pdf` – `article/Fig3.pdf` | Publication vector figures embedded in the submitted manuscript, together with `article/FIGURE_DATA.json`, `article/plot_trustmem_submission.py`, and `article/TABLE_NUMBER_MAP.csv`. |
| `benchmark/` | Exact unpacked `TrustMem-Bench 1.0.0-rc7.3` executable benchmark release (89 locked files in `RELEASE_LOCK.json`, pinned upstream reconstruction recipes, P3/P4/P4b audit tables, and scoring scripts). |

*(The earlier development catalog snapshot from November 2026 is preserved in git history under tag `v0.3-dev-catalog`.)*

---

## Quick Verification (No GPUs or Model API Calls Required)

### 1. Independently re-adjudicate Table 7 from per-arm request-set identities (<1 s, Python stdlib only)

```bash
cd article
python verify_table7_from_request_sets.py
```

This checks all 90 rows of `article/NATIVE_REQUEST_SETS_REVIEW.csv` and verifies the 29 sham-matched native-model comparisons across 15 distinct openings:
- **16/29** pairs deliver different completed request sets between receipt retention (`keep_r0`) and fee waiver (`fee_only`), spanning **10 of 15** distinct openings across 3 workflows (`8` fee-only outside-scope gains, `5` receipt-only shifts, `3` all-distinct), and **13/29** all-equal pairs (`0` pairs where both arms changed to the same set), alongside 14 sham-unavailable P4b pairs and 47 excluded rows.

To compute counts on any other CSV using the same schema:

```bash
python verify_table7_from_request_sets.py --csv other.csv --summary-only
```

### 2. Verify all 89 locked files in the executable benchmark (`TrustMem-Bench 1.0.0-rc7.3`)

```bash
cd benchmark
python reproduce.py verify
```

To rebuild deterministic native P3 outcomes from pinned upstream materials, follow `benchmark/README.md` and run:

```bash
python reproduce.py p3 --out native-p3
```

### 3. Redraw all three publication figures (`matplotlib >= 3.10`)

```bash
cd article
python plot_trustmem_submission.py --data FIGURE_DATA.json --out rendered
```

---

## Raw Branch-Level Decision Recordings & Licensing

- **Raw model decision recordings:** Replaying individual tool responses or inspecting raw model transcripts for P4 and P4b requires the original decision recordings and scoring reports. Requests may be addressed to the corresponding author (`2024212291@bupt.cn`), specifying the run and intended use, subject to applicable upstream terms and permission to share.
- **Licenses:** Original benchmark code and documentation are released under `LICENSE`; third-party notices and pinned upstream references are documented in `benchmark/THIRD_PARTY_NOTICES.md`.
