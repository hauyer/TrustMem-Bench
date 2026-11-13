# Development benchmark results

Each row is one complete correlated stream. No pooled independent-sample or novel-method claim.

Source bytes below are post-history logical file reads. Initial history, identity checks, scoring, memory, transport and model costs remain separate in the original JSON. Missing metrics are unknown, not zero.

| Case | Policy | Supported correct / planned | Wrong | Deferred | Unfinished | Unsupported submits | Evidence conflicts | Source bytes after history | Initial history bytes | Memory DB bytes | Backend DB bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| engineering-cross | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 1168 | 146 | 12288 | 0 |
| engineering-cross | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 146 | 146 | 12288 | 0 |
| engineering-cross | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 292 | 146 | 12288 | 0 |
| engineering-cross | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 438 | 146 | 12288 | 0 |
| engineering-threshold | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 1608 | 201 | 12288 | 0 |
| engineering-threshold | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 201 | 201 | 12288 | 0 |
| engineering-threshold | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 402 | 201 | 12288 | 0 |
| engineering-threshold | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 603 | 201 | 12288 | 0 |
| engineering-range | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 2101 | 263 | 12288 | 0 |
| engineering-range | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 262 | 263 | 12288 | 0 |
| engineering-range | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 525 | 263 | 12288 | 0 |
| engineering-range | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 787 | 263 | 12288 | 0 |
| engineering-quality | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 1232 | 154 | 12288 | 0 |
| engineering-quality | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 154 | 154 | 12288 | 0 |
| engineering-quality | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 308 | 154 | 12288 | 0 |
| engineering-quality | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 308 | 154 | 12288 | 0 |
| openml-confidence-gates | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 68734584 | 8591823 | 12288 | 0 |
| openml-confidence-gates | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 0 | 8591823 | 12288 | 0 |
| openml-confidence-gates | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 8591823 | 8591823 | 12288 | 0 |
| openml-confidence-gates | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 8591823 | 8591823 | 12288 | 0 |

External process invocations are not model calls. Raw `result.json`, per-task deliveries, observations and process traces remain the authority. Tool caches are common persistent state, not proof of explicit agent memory use.
