# Preserve task-local model errors and continue untouched positions

2026-11-13 Asia/Shanghai. v3 stopped after7 positions because the seventh reader
returned valid JSON with `type:query` instead of the required `action:query`.
Keep that exact first response and interface failure. Do not translate the field,
retry that state, replace the task or rerun the6 earlier tasks.

Create a separate v4 continuation from the closed actual memory/cache/archive state.
Copy the original initial memory and processed branch byte-for-byte; start at the
first unexecuted position. Other reader branches still start from their original
bootstrap state, not the processed branch. Other memory backends form their own
originally scheduled bootstrap. All prompts, tasks, source data, recovery rights,
format validation and response values remain unchanged.

Stop-rule revision only: a decoded JSON object with a wrong action shape is a
task-local model failure. Record it and proceed to the next task. HTTP/transport,
truncation, malformed JSON from the client, native writer failures and budget
exhaustion still stop the entire batch. This is an adaptive development continuation,
not a pristine single-protocol confirmatory experiment. Report phases together with
their differences, retaining first outputs and the unrun denominator.

v2 rejected request reserveUSD0.0184866; v3 actual peak estimateUSD0.071423088.
Continuation caps585 new actual requests andUSD2.90, keeping all phases combined
within600 requests andUSD3.00 conservative estimate. Raw bills remain unobserved.
No per-error method, field normalizer, repair prompt or retry-until-success is added.
