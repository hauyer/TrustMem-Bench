# Development data card

## Assets and experimental units

1. `catalog.json` retains the earlier 31 task-directory records: 7 legacy cases plus 24 sequence positions, five source families and eight archive groups. It is descriptive and is not automatically runnable by the new environment. The old records have not become held-out test data.
2. `trustmem_runtime.fixtures` generates four small engineering streams, each with eight sequential requests and two source versions. They instantiate joint counts, thresholds, signed interval sums and quality gates. Their weights are explicitly authored control data. These are not naturally occurring agent histories.
3. `trustmem_runtime.prepare_public` admits four already studied native archive files and constructs two eight-request development streams. GH Archive and Wikimedia are different producers but instantiate the same joint-count mechanism. Future requests and source transitions are researcher-constructed; the underlying observations are actual public archive records.
4. `trustmem_runtime.prepare_confidence` admits the pinned prediction ARFF for OpenML run10160807 (task75193, Covertype1596), SHA256 `8d7d4637968d2ac309531fcbc3ed49414e5d748327cfcdb4ce80b50c90e9fce7`. Its 191,733 real predictions become correctness/confidence contingency counts; eight authored sequential requests use rational decision gates. The source was already exposed during development. The profile is the fixed 13-column, seven-class prediction schema; it is not a general ARFF reader or a production memory history. Group scans still parse the complete file. No data are bundled.

The unit for paired policy comparison is the complete stream. Repeated requests, policies, source versions and tasks within one stream are correlated. Do not sum legacy catalog records and new execution opportunities into a dataset size or independent sample count. No formal train/dev/test split or confidence interval is supplied by this development release.

## Native source acquisition

Use the URLs and exact SHA256 values in `trustmem_runtime/prepare_public.py`. Save the files as `gh-0601.gz`, `gh-0602.gz`, `wiki-0601.gz`, `wiki-0602.gz`. Then run the importer with `--data-dir` pointing to that directory. It performs no network calls. Source data are not redistributed. Native raw files retain provider terms; linking to them does not grant a new data license.

The pinned prediction file's recorded upstream address is [OpenML predictions file21242529](https://openml.org/data/download/21242529/predictions.arff). Its original run metadata and intake receipts are retained in the research workspace. The importer checks SHA256 before writing a case; it does not silently substitute a newer file.

GH Archive observations group event type and ASCII repository owner (lowercased), with unit weights. Wikimedia observations group raw domain and whether the title contains a colon, weighted by views. This lexical title grouping must not be interpreted as a complete MediaWiki namespace classifier. The current contracts assume immutable source identity and a trusted declaration of the current source.

Query keys come from the initial marginal rank, including a confirmed absent-key control. They are not selected by joint values or policy success. Wikimedia group early stopping requires an independent contiguity pass bound to the source file. Preparation and admission are common work, recorded outside policy-runtime cost; each policy still executes its own actual historical scan.

## Labels and validation

Numerical truth is computed with separate parsers and SQLite aggregation after policy execution. The publicly shared evidence calculator implements the declared weighted-count and interval contracts. Small-table enumeration, interval enumeration, source-change, absent-key, persistence and lucky-answer tests check important boundaries. They do not certify arbitrary natural-language entailment or open-world memory correctness.

Current sources, task mechanisms and implementations have been inspected during development. Contamination-free generalization is not claimed. Native data can contain repository identifiers; the repository ships aggregate summaries rather than raw archive contents or usernames. There is no human annotation or inter-annotator agreement estimate yet.

## Intended use and remaining work

Use this version for interface development, reproducibility and ordinary-baseline calibration. Scientific publication still needs a demonstrated evaluation gap, more independent native task mechanisms, frozen held-out histories, systematic model/system comparisons, independent semantic calibration, qualified cost workloads, and a finalized code/data licensing decision. No new memory method is established by this runtime.

The current memory API retains exact structured observations. Arbitrary natural-language memory compression, third-party graph stores and note rewriting are not yet evaluated. Integrating those systems requires additional audited adapters and semantic references; this prototype must not be ranked as if it already measured them.

Quality-gate reference scoring uses a separate float/CSV parser and SQLite, while runtime acquisition uses Decimal parsing and source-matching count bounds. Empty selected populations return decision 0 under the declared nonempty-release contract. Wrong submitted decisions remain committed, and contradiction with sufficient declared evidence is a separate diagnostic. See [the frozen family protocol](QUALITY_GATE_PROTOCOL.md).

The subsequent tool-cache control fixes one previously generated model plan; its two conditions are not new autonomous model runs or new histories. Automatic backend state is included in the persistent-memory cost vector and is distinct from agent save actions. See [the control report](TOOL_CACHE_CONTROL.md).
