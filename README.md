# TrustMem-Bench

**Executable development release 0.3.** A research environment for evidence-grounded memory reuse across sessions. Agents acquire observations, persist them, submit actual outputs and reuse saved evidence after a source or task change. Version 0.3 adds decision-level quality gates, a pinned native prediction importer, evidence-conflict diagnostics, and automatic Markdown/CSV suite reports.

## Run without API keys or dependencies

Python 3.10+ and its standard library are sufficient. From the repository root:

```bash
python -B -m unittest discover -s tests
python -B -m trustmem_runtime.fixtures --output local-runs/cases
python -B -m trustmem_runtime.suite --cases local-runs/cases/cross.case.json local-runs/cases/threshold.case.json local-runs/cases/range.case.json local-runs/cases/quality.case.json --output local-runs/results
```

Outputs are created once; choose a new directory for each run. No existing run is overwritten. Every stream runs four ordinary policies: full verification, group lazy cache, full lazy cache and early full materialization. Each policy may retain the full table from the common historical scan before seeing future tasks. No artificial latency or tight memory restriction makes the baselines fail.

Each suite produces `SUMMARY.md`, per-task `tasks.csv`, full result JSON, code/case snapshots, independent scoring files and raw process traces. Source bytes, history construction, memory, backend caching and external-model accounting remain separate.

## Decision-level evidence: the new quality family

A historical summary can leave exact accuracy unknown yet already justify a 90% release gate. A 99% gate may need another observation. The new family tests this distinction, empty populations, source changes, persistent reuse and return to an older source. The shared calculator uses ordinary count bounds; it is available to every compared agent.

The importer below binds the previously studied seven-class OpenML run10160807 prediction file. It does not download or redistribute data:

```bash
python -B -m trustmem_runtime.prepare_confidence --predictions /path/to/predictions.arff --output local-runs/confidence
python -B -m trustmem_runtime.suite --cases local-runs/confidence/quality.case.json --output local-runs/confidence-results
```

See the [quality-gate protocol](docs/QUALITY_GATE_PROTOCOL.md) for the exact contract. Native predictions and authored request streams are distinguished; the full observation is the contracted contingency table, not the full raw ARFF.

## Evaluate an external agent

```bash
python -B -m trustmem_runtime.run --case local-runs/cases/cross.case.json --output local-runs/my-agent --agent-config agent-config.json
```

`agent-config.json` contains a command list such as `{"command":["python","/absolute/path/to/my_agent.py"]}`. The process receives one JSON observation on stdin and returns one JSON action on stdout. Queries are actually executed; observations persist only after a save operation in the cooperative interface. See the [agent protocol](docs/AGENT_PROTOCOL.md). The local process is not OS-sandboxed; trusted adapters must follow the documented file/state restrictions.

## Common tool caching

The query backend can retain complete source/scope-bound observations independently of explicit agent saves. Enable it with `--tool-cache` on `trustmem_runtime.run` or `trustmem_runtime.suite`; suite applies the same backend to every compared policy. Backend read/write payload and SQLite footprint are counted separately. The original v0.2 runs used cache-off; comparable methods must use the same declared backend settings.

A zero-API [fixed-action control](docs/TOOL_CACHE_CONTROL.md) reduced one saved Wikimedia trace's post-history source reads from 259,650,282 B to 86,550,094 B while preserving all actions and 8/8 supported deliveries. It demonstrates an ordinary-backend explanation, not a new autonomous model trajectory or method advantage.

## Native public archives

Four already studied GH Archive and Wikimedia snapshots can be imported from local files. Exact URLs, names, SHA256 bindings and grouping rules are documented in the [data card](docs/DATACARD.md). This command does not download data:

```bash
python -B -m trustmem_runtime.prepare_public --data-dir /path/to/archive-files --output local-runs/native-cases
python -B -m trustmem_runtime.suite --cases local-runs/native-cases/gh.case.json local-runs/native-cases/wiki.case.json --output local-runs/native-results
```

The raw data are real, while the request streams are constructed. Both producers share the joint-count mechanism and are previously seen development sources. Numeric reference answers use separate raw-data parsers and SQLite after the stream. The shared public calculator checks the explicit evidence contract; this is not independent natural-language annotation.

## What is measured

The new [diagnostic charter](docs/DIAGNOSTIC_CHARTER.md) fixes the research chain, evidence levels, component controls and scenario coverage. [Adapter capabilities](docs/ADAPTER_CAPABILITIES.md) distinguish implemented local stores from external systems that have only been reviewed. The [mechanism registry](docs/MECHANISM_REGISTRY.md) preserves cumulative hypotheses and ordinary explanations. These are development instruments; they do not establish comprehensive coverage or a novel method.

`trustmem_diagnostics` (Python 3.10+) adds explicit denominators/observability, read-only SAP trace analysis, native-operation hooks and sensitivity controls. Run `python -B -m trustmem_diagnostics.calibration --output local-runs/diagnostic-calibration.json` for authored instrument checks without API use. These controls are not estimates of model error rates.

An optional [native Mem0 OSS adapter and pilot](docs/NATIVE_MEM0_PILOT.md) now qualifies actual infer=True writing, native search/update and independent-process disk reopen. The default core install remains dependency-free; this optional path pins its own SDK and existing local embedding model. Its first small reader trial is an authored development workload, not a system ranking.

The [same-evidence calculator controls](docs/CALCULATOR_CONTROL.md) keep all12 real delivered-note inputs: tool availability did not cause tool use; instructed use separated arithmetic, parameter selection and unfinished delivery. Both the pure arithmetic helper and all-state completion diagnostics are reusable ordinary baseline components.

The [delivered-support diagnostic](docs/DELIVERED_SUPPORT.md) distinguishes actual reader inputs from generated tool results. The [shared native-note reader](docs/SHARED_READER.md) now gives note backends the same query/calculation/save/terminal contract; its70 scripted qualification deliveries are engineering checks, not additional model results. New confirmation candidates have been selected and constructed separately; no confirmation model results are claimed.

- Correct submissions and correct submissions with sufficient declared evidence.
- Lucky unsupported answers, wrong answers, unsupported declarations, abstention, launch/format failure and step limits.
- Actual source reads, common history scanning, identity checking, memory payload reads/writes, SQLite size, agent invocations, observation transport and wall time. These units are not collapsed into one cost.
- Actual SQLite persistence and later declared reuse. A citation is not proof of causal use.

The four small fixture streams instantiate joint counts, numeric thresholds, signed interval sums and decision-level quality gates. They are engineering controls, not four independent native task mechanisms. Ordinary success is a required reference. See [development protocol](docs/DEVELOPMENT_PROTOCOL.md), [data card](docs/DATACARD.md), and [research positioning](docs/POSITIONING.md).

## Retained legacy catalog

```bash
python trustmem.py summary
python trustmem.py inspect legacy/dev-007
```

`catalog.json` preserves the earlier 31 directory records (7 cases and 24 sequence positions), five source families and eight archive groups. They are not 31 independent trajectories. They remain a legacy inventory and are not automatically executable in the new runtime. No former development record is relabeled as a held-out test.

## Release status

The [bounded public pilot](docs/PUBLIC_PILOT.md) executed48 eligible positions and
keeps all format failures, an empty native intake and every first response. It
provides local source-validity and read-cost observations, not a system ranking
or independent confirmation. The current explicit-schema reader is a subsequent
engineering repair and has not been substituted into those results.

[Development results](docs/DEVELOPMENT_RESULTS.md) record executed calibrations and their limitations. Raw local runs, credentials and source datasets are excluded from Git. The repository remains private. Code/data licensing is pending; native datasets retain their providers' terms.

[Version 0.3 results](docs/DEVELOPMENT_V03_RESULTS.md) add 20 cache-off and four matched cache-on ordinary streams, all 192 planned requests completed with sufficient evidence. These are engineering/development denominators, not independent histories or a model comparison.

The benchmark-first program builds a useful reproducible instrument and diagnostic study independently of a new author algorithm. Untouched confirmation histories, native memory-system comparisons and a verified evaluation contribution remain publication work; current sources are development assets.

[Known limits](docs/KNOWN_LIMITS.md) include the supported SQLite integer range and an upfront custom-source admission check still to implement; supplied calibration inputs stay within that range.
