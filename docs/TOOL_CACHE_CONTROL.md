# Ordinary backend-cache control

This development control fixes every action previously produced in the Wikimedia model pilot, including nine recoverable invalid `start` operations. It compares actual source execution with an ordinary persistent query-observation cache enabled or disabled. There are no new API calls or model samples.

The cache keys complete observations by immutable source and scope. It can serve a group request from a complete full-source observation; a group observation cannot satisfy a full-source request or a different group. A previously unseen source identity must miss. Both versions can remain available for a later return. The cache starts empty and is populated only after query scans; it receives neither an S0 full-table prefill nor reference answers.

| Metric | Cache off | Cache on |
|---|---:|---:|
| Supported correct deliveries | 8/8 | 8/8 |
| Fixed policy invocations | 29 | 29 |
| Post-history source bytes | 259,650,282 | 86,550,094 |
| Backend hits / misses | — | 4 / 2 |
| Backend payload bytes written | 0 | 112,871 |
| Backend payload bytes read | 0 | 225,742 |
| Backend SQLite size | 0 | 131,072 |
| Explicit agent-memory payload written | 0 | 0 |
| Recoverable tool errors | 9 | 9 |

The post-history read reduction is 173,100,188 B (two thirds). Both conditions additionally execute their common historical scan (42,977,573 B) and source-identity checks (86,550,094 B); the percentage is not a whole-system cost or dollar reduction. Backend state is real persistent memory and is counted separately from explicit agent memory.

The arms ran with overlapping execution. Their wall times are retained only as technical diagnostics. They do not establish a causal speed estimate. Every query and submission action is fixed from the saved plan. A new autonomous model could react differently to cache-hit feedback; this is a fixed-plan tool-layer intervention, not a counterfactual model run.

## Interpretation

Ordinary backend caching explains much of this particular trace's repeated source reading without an explicit agent save. The remaining two scans acquire the initial missing joint observations and the changed snapshot. Existing ordinary targeted-query and S0 materialization references may do less work still. No new memory algorithm is justified by this control.

The previous native pilot also contains nine recoverable, out-of-phase `start` operations. Its earlier zero terminal interface-failure count does not mean zero tool errors. These errors remain in both replay arms and must not be attributed to memory maintenance.

Future method comparisons must declare common backend caching and include all durable state in memory/cost accounting. A claim about missing agent writeback must survive ordinary automatic retention or transparent query caching before being used as a method motivation. This is a correction to baseline completeness, not a new research principle.

## Reproduction and evidence

The `run` and `suite` CLIs now accept `--tool-cache`; suite uses one common backend setting for all policies. Defaults remain cache-off to preserve the original development setup; common backend settings must be frozen when comparing methods. A deterministic `trustmem_runtime.replay_agent` executes saved decisions and is explicitly not a language model.

Complete [protocol, plan, code snapshots, both results and metrics](../reports/tool-cache-replay-v1) are retained. The source case is regenerated with the native importer and the original bound files. Published tests reconcile actions, source costs, code identities, source changes and persistent-cache size. The original v0.2 records remain unchanged.

Independent same-family result-to-claim review was requested but could not complete because the reviewer service hit its usage limit. Status: **REVIEW_UNAVAILABLE**. Local numerical and boundary checks are complete; they do not substitute for independent semantic review. This result remains development evidence pending that review.

When caching is enabled, the legacy `always_verify` policy name denotes requesting a full query at every task. The backend may satisfy that request from cache; it must not be described as an actual source revalidation on every call. Read the backend flag, hit/miss counts and source work together.
