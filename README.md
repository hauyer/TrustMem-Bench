# TrustMem-Bench

**Executable development release 0.2.** A research environment for evidence-grounded memory reuse across sessions. Agents can acquire observations, persist them, submit actual outputs and reuse saved observations after a source or task change. This remains a development benchmark: top-venue novelty, held-out generalization and a new memory method have not been established.

## Run without API keys or dependencies

Python 3.9+ and its standard library are sufficient. From the repository root:

```bash
python -B -m unittest discover -s tests
python -B -m trustmem_runtime.fixtures --output local-runs/cases
python -B -m trustmem_runtime.suite --cases local-runs/cases/cross.case.json local-runs/cases/threshold.case.json local-runs/cases/range.case.json --output local-runs/results
```

Outputs are created once; choose a new directory for each run. No existing run is overwritten. Every stream runs four ordinary policies: full verification, group lazy cache, full lazy cache and early full materialization. Each policy may retain the full table from the common historical scan before seeing future tasks. No artificial latency or tight memory restriction makes the baselines fail.

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

- Correct submissions and correct submissions with sufficient declared evidence.
- Lucky unsupported answers, wrong answers, unsupported declarations, abstention, launch/format failure and step limits.
- Actual source reads, common history scanning, identity checking, memory payload reads/writes, SQLite size, agent invocations, observation transport and wall time. These units are not collapsed into one cost.
- Actual SQLite persistence and later declared reuse. A citation is not proof of causal use.

The three small fixture streams instantiate joint counts, numeric thresholds and signed interval sums. They are engineering controls, not three independent native task families. Ordinary success is a required reference, not evidence of author-method superiority. See [development protocol](docs/DEVELOPMENT_PROTOCOL.md), [data card](docs/DATACARD.md), and [research positioning](docs/POSITIONING.md).

## Retained legacy catalog

```bash
python trustmem.py summary
python trustmem.py inspect legacy/dev-007
```

`catalog.json` preserves the earlier 31 directory records (7 cases and 24 sequence positions), five source families and eight archive groups. They are not 31 independent trajectories. They remain a legacy inventory and are not automatically executable in the new runtime. No former development record is relabeled as a held-out test.

## Release status

[Development results](docs/DEVELOPMENT_RESULTS.md) record executed calibrations and their limitations. Raw local runs, credentials and source datasets are excluded from Git. The repository remains private. Code/data licensing is pending; native datasets retain their providers' terms.
