# Agent interface

The runner calls a cooperating executable once per decision. Standard input is one JSON observation; standard output must be exactly one JSON action. Diagnostics belong on stderr. Example configuration:

```json
{"command": ["python", "my_agent.py"]}
```

Use absolute paths for external programs that require them. The runner does not use a shell. It records the input, stdout, stderr, return code and duration. A malformed response, process timeout or launch error is retained as a failure. There is no automatic retry or best-of-N selection.

## Observations and operations

Bootstrap receives the historical observations, source identity and an opportunity to capture the full table from the actual shared history scan. It does not receive the future requests. Return `{"action":"start"}` or `{"action":"capture_full"}`.

Each later task receives the current source identity, current request, ordinary historical observations, saved receipt metadata, the current task's tool transcript, and remaining decision steps. There is no pre-inserted sufficiency/action label or SQL reference answer. A common exact calculator is available to every policy.

| Operation | JSON fields | Effect |
|---|---|---|
| `calculate` | `evidence`: list of IDs | Compute from those observations if supported under the public contract; otherwise return null. |
| `query` | `scope`: `group` or `full` | Actually read the current source, acquire a scoped observation, and compute the current requested value. |
| `save` | `receipt_id`: acquired ID | Write the observation to SQLite for later tasks. |
| `submit` | `value`: integer, `evidence`: list of IDs | Commit the supplied deliverable; no automatic correction or safety gate. |
| `abstain` | — | End without a deliverable. |

Transient observations disappear between tasks. `save` persists the data, not just a note or a claimed citation. The next task reopens SQLite and the agent is again a new process. Both old and new source observations may coexist, allowing a return to the previous version without needless deletion. The calculator rejects observations tied to a different current source.

## Metrics

`correct` counts numeric matches to independent SQL truth. `supported_correct` additionally requires that the declared evidence determines the answer. `unsupported_correct` explicitly preserves lucky correct answers. `incorrect_submissions`, `unsupported_submissions`, abstentions, process failures and step limits remain separate. These metrics concern declared support under the specified algebra, not unrestricted semantic validity or causal use of a memory.

Read cost is actual logical source bytes returned to the reader (including gzip read-ahead). Other dimensions include common history scanning, source-identity checks, stored/read memory payload, SQLite file size, policy invocations, observation transport, policy-phase wall time and controller/scoring time. Do not turn fewer source bytes into a claim of lower overall latency or dollars. Per-decision process startup is part of this harness and is not an optimized deployment bound.

## Trust boundary

This is a cooperative JSON interface, not an OS sandbox. External programs have ordinary local filesystem permissions and must not open controller manifests, source files outside tools, grading outputs, or keep out-of-band state. A remote language-model adapter that only forwards the observation and returns an action naturally satisfies this narrower interface; arbitrary local programs require auditing or a separately isolated environment. The present release does not claim protection from a malicious local solver.

Paid API adapters must independently enforce model/call/token/USD limits and preserve usage plus raw replies. The environment's process-call count is not an API-call meter. No credentials are bundled in this repository.

## Optional ordinary backend cache

With `--tool-cache`, `query` may reuse a previous complete scan of the same immutable source and sufficient scope. The tool transcript declares cache hits; the cache is initially empty and is not prefilled by S0. This state is separate from agent `save` and is fully costed. Default cache-off preserves the original release's conditions. New comparisons must declare a common backend for all methods; cache-off is an ablation rather than a sufficient claim about the best ordinary system.

`trustmem_runtime.replay_agent` is a deterministic saved-action runner for tool-layer controls. Its outcomes must not be labeled as new model inference or adaptive model behavior.
# Quality-gate extension (0.3)

The existing integer submission and acquire/save/calculate actions also support `kind: quality`. A request supplies `a`, an integer `cutoff`, and rational `numerator`/`denominator`. Return 1 iff the population with `b >= cutoff` is nonempty and its share in group a reaches the ratio; return 0 otherwise. A source-matching margin can certify this decision without certifying an exact joint count. The shared calculator is available equally to all adapters. Group acquisition may require combining the new receipt with current-source margins; the tool returns the evidence IDs used. Full acquisition supplies the complete contracted contingency table. Only saved receipts survive in explicit agent memory.

Suites distinguish an insufficient declared evidence set from a submitted value that contradicts a sufficient declared set. Neither is silently repaired. Current contracts are exact structured observations; a free-text memory adapter requires additional semantics and calibration.
