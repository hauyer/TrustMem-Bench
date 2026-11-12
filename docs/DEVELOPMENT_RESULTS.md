# Executed development calibrations

2026-11-12. Machine-readable results: [development-v0.2.json](../reports/development-v0.2.json). These are development and interface checks, not held-out confirmation or a method comparison.

## Ordinary policies

Three authored engineering streams × four policies × eight related requests completed with supported correct delivery in every slot (each policy 8/8 within each stream). They exercise joint counts, thresholds and signed interval sums. Twelve successful runs do not imply twelve independent workflows.

Two already studied native producers were then executed with source changes and later reuse. Each row is a complete eight-request stream. Initial history scanning, source-identity checking, memory and agent overhead remain separate from the following post-history source-read metric:

| Native stream | Policy | Supported correct | Post-history source bytes |
|---|---|---:|---:|
| GH Archive | always_verify | 8/8 | 532,969,323 |
| GH Archive | lazy_group | 8/8 | 178,508,331 |
| GH Archive | lazy_full | 8/8 | 127,140,855 |
| GH Archive | eager_full | 8/8 | 51,367,476 |
| Wikimedia | always_verify | 8/8 | 345,605,428 |
| Wikimedia | lazy_group | 8/8 | 55,967,774 |
| Wikimedia | lazy_full | 8/8 | 86,550,094 |
| Wikimedia | eager_full | 8/8 | 43,572,521 |

The group/full lazy-cache ordering differs across producers. That is a descriptive result under the two layouts and request streams, not an isolated causal estimate of layout. Early materialization is a strong reference: it captures initial full observations from the common historical scan and later acquires the changed source only once. These ordinary successes are retained.

Fewer source bytes must not be reported as lower total latency or API cost. Results include policy-phase and controller wall time, common scanning, identity verification, memory payload I/O, process calls and observation transport. Runs were sequential in a fixed order, with other development work on the host; timing values are diagnostic, not a randomized speed ranking.

## External DeepSeek adapter

All calls used `deepseek-flash`, non-thinking mode, temperature 0, at most 384 output tokens. The service returned the model field `deepseek-flash`; an alias does not independently certify underlying weights.

| Batch | Stream | Received replies | Supported correct | Interface failures | Memory payload saved | Post-history source bytes |
|---|---|---:|---:|---:|---:|---:|
| Initial interface pilot | authored cross | 12 | 2/8 | 6 | 161 B | 146 |
| Flat-schema recovery | same authored cross | 19 | 8/8 | 0 | 0 B | 1,022 |
| Native interface pilot | Wikimedia | 29 | 8/8 | 0 | 0 B | 259,650,282 |

The first pilot emitted nested action JSON. It remains in the record, with all eight planned requests. Recovery changed only the system instruction to explicitly specify flat action objects; it is a separately frozen engineering recovery, not a new independent test or retry-selection result. All raw requests, responses and usage remain in [the pilot report directories](../reports).

The recovered and native model pilots completed by querying without saving new observations. This demonstrates that correctness alone does not show durable memory maintenance in these runs. It does not establish a new mechanism need: ordinary retention already succeeds, and tiny fixtures are not qualified expensive-verification workloads. Native differences likewise need whole-system costs and stronger automatic-consolidation comparisons before any algorithm claim.

Across the three batches there were **60 API attempts and 60 received responses**, peak-rate estimate **USD 0.0116901**, with no unknown-usage reserve. This is not an invoice. Frozen caps were checked before each separate batch; later caps plus actual prior spending remained below the series USD 0.10 ceiling. Model ledgers are distinct from process-invocation counts. [Pricing source](https://api-docs.deepseek.com/quick_start/pricing/)

## Integrity and fixes

The initial engineering tests exposed unclosed SQLite connections during Windows temporary-directory cleanup. Explicit transaction commits and connection closing resolved that issue; it was an engineering failure, not a model result. Engineering-v1 code snapshots and original results remain locally preserved.

Independent same-family review identified and checked corrections for bootstrap failures losing their planned denominator, executable launch errors, incomplete terminal summaries, and under-reported non-scan costs. Sixteen offline tests now include enumerated small tables, signed intervals, threshold boundaries, source mismatch, persistence, lucky unsupported answers, wrong-value commits, step limits, bootstrap failure, and metered-client mocks. Mock provider responses are unit-test fixtures and are not included in the 60 real API calls.

The review also confirmed the important limitation: this is a cooperating subprocess interface, not an OS sandbox. Evidence support follows the public structured contract; only numerical truth uses an independent SQL implementation. Current results do not certify top-venue novelty or an unrestricted semantic memory evaluator.

## Subsequent ordinary-cache control

The above original runs disabled automatic tool-backend caching. A separately frozen zero-API, fixed-action replay has now added that ordinary control. Both arms preserve the exact original actions and 8/8 deliveries; post-history source reads become 259,650,282 B versus 86,550,094 B, with 4 cache hits and 2 misses. Backend persistent state is included in the cost vector. This limits the earlier no-save observation: missing agent saves do not by themselves imply missing whole-system memory or a novel mechanism need. The native pilot also contains nine recoverable invalid phase actions, despite zero terminal interface failures. [Protocol, costs and limitations](TOOL_CACHE_CONTROL.md)

The updated suite has 19 offline tests. The new result-to-claim review could not complete due to reviewer usage limits and remains REVIEW_UNAVAILABLE; prior v0.2 review should not be treated as a review of this new control.
