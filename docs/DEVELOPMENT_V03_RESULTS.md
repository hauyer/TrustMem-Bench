# Version 0.3: decision-level gates and transparent suite reports

2026-11-13. Benchmark-first engineering increment. These are deterministic calibration runs, not a new author method or a model leaderboard.

## Delivered capabilities

- Quality gates can be justified by nondegenerate count bounds when exact joint accuracy is unknown. Same public calculation and acquisition apply to all policies.
- Existing JSON-agent interface, hidden sequential requests, real source reads, SQLite save/reopen, source changes and return to old sources.
- Pinned native OpenML prediction import without download; a separate raw parser and SQLite numerical reference.
- Evidence-conflicting submissions remain committed and are counted separately from missing-evidence submissions.
- Automatic per-suite `SUMMARY.md` and per-task `tasks.csv`; duplicate case filenames are bound by suite position and preserved as separate snapshots.
- Raw result event/action traces, deliveries, independent scoring and code/case snapshots are byte-preserved in [the compact export](../reports/development-v0.3/manifest.json). Detailed invocation stdout/stderr stay in the original local runs.

## Executed streams

[Machine-readable summary](../reports/development-v0.3.json).

| Condition | Streams × policies | Planned / supported correct | Meaning |
|---|---:|---:|---|
| Common tool cache off | 5 × 4 = 20 | 160 / 160 | Four authored fixture streams and one already exposed native prediction stream |
| Common tool cache on | 1 × 4 = 4 | 32 / 32 | Same authored quality stream, separate matched backend-cache control |

Every policy completed 8/8. These are 24 related policy streams and 192 request opportunities, not 192 independent histories. The native source contains 191,733 original predictions; eight future requests were constructed. New external model calls and USD: zero. Previous model experiments remain in their original reports.

## Observable quality/cost distinctions

For the native OpenML stream, each policy pays the common historical scan of 8,591,823 B. Post-history logical source reads are:

| Ordinary policy | Supported correct | Additional source reads |
|---|---:|---:|
| Always verify | 8/8 | 68,734,584 B |
| Group lazy cache | 8/8 | 8,591,823 B |
| Full lazy cache | 8/8 | 8,591,823 B |
| Eager complete observation | 8/8 | 0 B |

Eager capture retains the complete **contracted contingency table** during the historical scan; it does not retain the entire raw ARFF for free. Memory writes, payload reads, SQLite size, identity checks, scoring and invocation transport remain separately recorded. Identical correctness can coexist with different acquisition work; this calibrates measurement, not algorithm novelty or deployment savings.

For the authored quality stream, always-verify source reads fall from 1,232 B to 308 B when the ordinary common tool cache is enabled. It has two misses and six hits. The lazy policies already read 308 B and eager capture reads 154 B under either backend. This distinguishes explicit saved observations from ordinary automatic persistence. No model behavior or memory causality is inferred from this fixed deterministic policy control.

## Reproduction and scope

The [README](../README.md) provides self-contained fixture and native-import commands. [The frozen family contract](QUALITY_GATE_PROTOCOL.md) defines the binary nonempty-population decision and numerical support. All four ordinary policies use the same public bounds, full-history access and current-source identity. No model was selected to lose and no ordinary cache was removed from a declared comparison.

The runtime covers exact structured observations in cooperative subprocess agents. It has not yet run native free-text writers/retrievers in Mem0/Letta/LangMem. The complete quality family remains a contingency-table projection; new task semantics are not a new independent native mechanism. Current data are exposed development sources, with no held-out confirmation claim. This increment strengthens a reusable instrument and supports a benchmark/system-evaluation paper route; a verified distinct evaluation contribution and broader system evidence remain research work.

Review also reproduced a custom integer-range failure outside the provided data: weight2^63 can overflow the SQLite reference after a policy commits. [The admission limit](KNOWN_LIMITS.md) is retained as an engineering backlog item. All 24 published streams remain within range and unchanged.
