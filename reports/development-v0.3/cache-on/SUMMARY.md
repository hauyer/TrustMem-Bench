# Development benchmark results

Each row is one complete correlated stream. No pooled independent-sample or novel-method claim.

Source bytes below are post-history logical file reads. Initial history, identity checks, scoring, memory, transport and model costs remain separate in the original JSON. Missing metrics are unknown, not zero.

| Case | Policy | Supported correct / planned | Wrong | Deferred | Unfinished | Unsupported submits | Evidence conflicts | Source bytes after history | Initial history bytes | Memory DB bytes | Backend DB bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| engineering-quality | always_verify | 8/8 | 0 | 0 | 0 | 0 | 0 | 308 | 154 | 12288 | 16384 |
| engineering-quality | eager_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 154 | 154 | 12288 | 16384 |
| engineering-quality | lazy_full | 8/8 | 0 | 0 | 0 | 0 | 0 | 308 | 154 | 12288 | 16384 |
| engineering-quality | lazy_group | 8/8 | 0 | 0 | 0 | 0 | 0 | 308 | 154 | 12288 | 16384 |

External process invocations are not model calls. Raw `result.json`, per-task deliveries, observations and process traces remain the authority. Tool caches are common persistent state, not proof of explicit agent memory use.
