# Independent experiment integrity review

**Verdict: WARN.** Deterministic integrity checks pass. The retained evidence supports a reusable native Mem0 adapter and an actual model-writer → persistent store → native search → model reader/tools/submission → new-experience lifecycle. Error attribution, generality and total-cost claims require the limits below.

Generated 2026-11-13T06:42:12.247286+00:00. Requested reviewer: **gpt-6.1-sol / ultra**. Actual exact model/effort: **not independently attested**; reviewer is a fresh native Codex worker. Review independence: **same-family**; acceptance: **provisional**. No audit network/API calls, paid replays or native-store reopen were performed. Inputs, raw outputs and stored native data were preserved.

## Verified evidence

All **43/43 preflight** and **44/44 reader** frozen hash entries match, including selected Mem0 SDK source and all pinned offline embedding assets. Installed mem0ai 1.0.11, fastembed 0.8.0, qdrant-client 1.20.0 and pydantic 2.13.5 match the freeze. Current runner, adapter and protocol equal their reader snapshots. Snapshot imports and the child PYTHONPATH are explicit (`snapshot/run.py:22`, `:58`, `:102`); provenance does not freeze every transitive package/source or hardware detail.

The adapter invokes actual SDK `add(..., infer=True)`, default extraction/consolidation prompts, native search/ranking, Qdrant disk persistence and history storage (`snapshot/trustmem_diagnostics/native_mem0.py:74`, `:86`, `:95`; pinned `mem0/memory/main.py:515`, `:590`). The zero-API scripted preflight is interface calibration only: two scripted responses, ADD/search/explicit UPDATE, same ID and changed marker after new-process reopen. Paid writing is unscripted and shows native ADD and UPDATE. Each retained Mem0 session's fresh-process search matches delivered notes; inventory is stored separately and is absent from every reader payload (`snapshot/run.py:225`, `:238`). Search actually returned every then-current inventory item in all six sessions. Reopen uses a genuinely new Python process, not an independently operating external agent.

Ground truth is the authored four-row table per version, not generated from model outputs. Controller SQL is invoked only after all policy execution ends (`snapshot/trustmem_runtime/grading.py:55`; `snapshot/run.py:287`). Independent raw-JSONL integer arithmetic reproduces **[1,0,0,1,1,0]** and all 12 grades. Raw results and graded results differ only by grading fields; every saved reader input/response matches its metered API entry, and submitted values are unchanged. No prediction-based normalization or phantom reported metric was found.

| Backend | Correct | Wrong | Query calls | Cache hits/misses | Task source bytes |
|---|---:|---:|---:|---:|---:|
| Mem0 | 4/6 | 2/6 | 3 | 1/2 | 308 |
| Full verbatim notes | 3/6 | 3/6 | 2 | 0/2 | 308 |

These are descriptive counts from one authored two-version workload with six correlated ordered sessions per backend. Initial text, reader system and legal tools are equal; different acquisitions follow actual actions. Each backend uses the same source-bound cache implementation with its own persistent cache (`snapshot/run.py:191`, `:198`, `:258`). The fixed seeded order ran Mem0 before verbatim, once. No independent causal ranking or population success rate follows.

## Important findings

1. **All five wrong submissions received sufficient correct current-source information.** Mem0 s02/s05 and verbatim s02/s05 received the complete source-A table: 76/(76+4)=95%, so the 99% gate is 0, yet submitted 1. Verbatim s00 received intact margins; selected correct is at least 95+80−100=75 of 80, or 93.75%, so the 90% gate is 1, yet submitted 0. These errors cannot be described as observed retrieval nondelivery or missing source facts. The traces do not identify calculation error, threshold interpretation or another reader failure. See `models/mem0/s02/t0-input.json:25`, `models/mem0/s05/t0-input.json:25`, `models/verbatim/s00/t0-input.json:13`, `models/verbatim/s02/t0-input.json:17`, and `models/verbatim/s05/t0-input.json:17`.

2. **One consolidation omission is directly observed.** In Mem0 s00, extraction includes the acquired joint cells (API log line 5), but the consolidation response retains the old marginal text (line 6; `models/mem0/s00/write-result.json:5`; `models/mem0/mem0-s00-inventory.json:16`). Thus s01 notes are insufficient at 99%, even though prior ingestion contained full cells. S01 queries a source-bound cache, correctly submits 0 and its following update stores the complete table. This is an observed writer omission, not a retrieval miss, and it does not explain the later errors after those full values are delivered. No counterfactual error-reduction effect is established.

3. **The public exact calculator is not selectable by this reader.** Current legal actions are submit/query/abstain; `calculate` is only used after query (`snapshot/run.py:29`, `:255`, `:265`). Earlier structured policies can select it (`snapshot/trustmem_runtime/agent.py:21`; `snapshot/trustmem_runtime/run.py:185`). Within this pilot both arms have the same tools, and full verbatim notes are a strong storage control. Current errors remain confounded with ordinary reader reasoning, and scores cannot directly establish an advantage over the earlier calculator-enabled baseline.

4. **Citations do not establish causal use or current-source support.** Both source-change sessions correctly query B. Mem0 s03 nevertheless cites an A note; the current tool trace supports its correct B answer (`models/mem0/s03/event.json:1`). Historical A/B coexistence is legitimate. For the wrong return-to-A cases the declared citation matches A, so stale-source substitution is not demonstrated.

The separate `CASE_DIAGNOSIS.json` and `.md` cover every retained case. Their semantic sufficiency judgments are **posthoc fresh-reviewer manual calibration**, not an independently human-labeled population score or a newly automated support metric. No independent human annotation was obtained. Frozen `native_text_support=unassessed` fields remain unchanged.

## Call, cost and measurement accounting

All **25** API entries have monotonic global IDs 1–25, received responses and normal stop finishes, `max_tokens=1536`, thinking disabled and both requested/reported model `deepseek-flash`. The retained responses do not attest an immutable server deployment identity. All first responses are preserved, including native writer calls; the adapter tracks transport failures that Mem0 might swallow (`snapshot/trustmem_diagnostics/native_mem0.py:26`, `:86`). This guard does not detect every possible SDK semantic parse/action failure. All actual retained writer JSON parses and operations are accounted for here.

| Stage | Calls | Prompt tokens | Completion tokens | Prompt cache hit/miss tokens | Estimated peak USD |
|---|---:|---:|---:|---:|---:|
| Mem0 writer, including initial write | 8 | 10,897 | 1,242 | 7,163 / 3,734 | 0.002653578 |
| Mem0 reader | 9 | 7,885 | 245 | 2,688 / 5,197 | 0.001869228 |
| Verbatim reader | 8 | 5,347 | 114 | 3,072 / 2,275 | 0.000837732 |
| Total | 25 | 24,129 | 1,601 | 12,923 / 11,206 | **0.005360538** |

Totals reproduce `models/metrics.json` using the frozen rate constants, below 48 calls / USD 0.10. These are token-derived estimates, not invoice-verified charges; rates were not reverified during this no-network audit. Cache discounts depend on actual provider behavior and fixed execution order. The common initial historical source scan cost **154 bytes once** (`models/initial_experience.json:3`); task scans add 308 bytes per backend, so this experiment's task-plus-common-setup scans total **770 bytes**. Allocating 154 setup bytes to each arm would yield 462 per arm but double-count common setup if summed. Source identity hash reads and independent reference reads also perform I/O outside the task-scan counter (`snapshot/trustmem_runtime/run.py:40`; `snapshot/run.py:287`). Memory read/write bytes, offline embedding work and full end-to-end latency are not measured. The API log's call latency is transport timing only.

## Audit checklist and claim boundaries

| Check | Result | Basis |
|---|---|---|
| A. Ground-truth provenance | PASS | Exact authored source bytes; independent SQL and direct arithmetic; no model-derived gold. |
| B. Score normalization | PASS | Raw counts independently reproduced. |
| C. Result existence | PASS | All 12 cases, 17 reader calls and 8 native writer calls are retained. |
| D. Reported metric execution | PASS | Reported score/count/cost code is active; no claimed automatic text-support score. |
| E. Scope | WARN | One authored environment, one fixed history/order, six correlated sessions per arm. |
| F. Evaluation classification | WARN | Authored synthetic engineering environment with actual native system/model operations; not production-history or human evaluation. |

The new adapter and actual native lifecycle are supported engineering results. The 4/6 versus 3/6 counts and the one consolidation omission may be reported descriptively with scope. Claims that the observed wrong outputs are caused by lost/stale memory, that a new method beats a stronger baseline, that total system cost is lower, or that performance generalizes are unsupported by this batch. Future attribution work should predefine equivalent arithmetic assistance and independent semantic calibration; no additional paid calls are needed to complete this audit.

## Hashes and reproducibility

Reader freeze SHA-256: `fd720a6211725e277792d2db171a14dd44cbaea7e8beef5007a031dabac7bb1e`. Preflight freeze SHA-256: `10cb15de5058ba293e7c271597229d450d1eb52dcf3014457c88526ac1a8623f`. Reader runner SHA-256: `c9c67d9623cf20e43cc7e172fa26af1f1d671b3c3d8b0f82c1575d6080b788cd`. Native adapter SHA-256: `d01f6fa133cb2d8ed10fd096794de489edaff896825551d19a16865867707bc3`.

The full audited input hash map is in `INTEGRITY_REVIEW.json`; reproducible read-only comparisons are in `.aris/traces/experiment-audit/20261113_native_mem0/DETERMINISTIC_CHECKS.json` and `audit_checks.py`. File references in this report are relative to this reader artifact directory unless prefixed with a repository path. The pinned SDK path is `memory-revocation-research/.venv-mem0-probe/Lib/site-packages/mem0/memory/main.py` relative to project root.
