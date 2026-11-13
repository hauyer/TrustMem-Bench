# Known engineering limits

Version0.3. This page separates supported experiments from robustness work still to do.

- **Numeric range admission:** the SQLite reference requires individual weights and relevant aggregate magnitudes to fit signed 64-bit integers. The supplied fixtures and pinned native sources satisfy this. A custom source with weight 2^63 was reproduced during review: the policy can commit a correct gate before SQLite reference insertion raises OverflowError, leaving traces but no final result.json. Arbitrarily large custom integers are not supported, and an early all-source range-admission check is still needed. Do not score such incomplete runs as zero or silently remove them.
- **Structured memory:** current runnable tasks use exact source-bound observations. Native free-text writer/retriever behavior requires an actual system adapter and semantic calibration; the public calculator is not a general entailment judge.
- **Cooperative processes:** external agents retain local filesystem permissions. The JSON contract hides future tasks only for cooperating adapters; no operating-system isolation is claimed.
- **Cost scope:** source-read bytes count logical acquisition reads. History formation, identity checks, reference scoring, storage, transport and model accounting remain separate; no total physical-I/O or production speedup guarantee.
- **Development scope:** sources and request patterns have been inspected. The released results are calibration, not held-out model/system generalization. Independent confirmation and licenses remain release/publication work.

The numeric issue is an admission robustness item, not evidence of a memory algorithm failure. Preserve current valid results and add a separately versioned regression when the admission path is hardened.
