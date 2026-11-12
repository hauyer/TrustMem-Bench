# TrustMem-Bench

Development-stage benchmark assets for studying whether evidence retained across agent sessions supports a changed task. This repository currently provides a task catalog and inspection tools; an end-to-end agent environment, independent test split, and method comparison are not yet available.

The catalog contains 31 records (7 earlier development cases and 24 positions in constructed task sequences), drawn from 5 source families and 8 archive groups. These are not 31 independent trajectories. The task relationships and inputs have been used during development.

## Quick start

Requires Python 3.9 or later; no third-party packages or API keys.

```bash
python trustmem.py summary
python trustmem.py inspect legacy/dev-007
python -m unittest discover -s tests
```

## Scope and status

The intended research question is how an agent determines whether prior evidence supports a new action, acquires missing evidence, and makes revisions available to later sessions. Existing experiments include ordinary summaries, direct verification, materialization, and lazy caches. In tested settings, ordinary baselines already solve the specified tasks; a novel method advantage has not been established.

The catalog does not contain ground-truth answers or executable source artifacts. It is a development inventory, not a standalone evaluation dataset or a leaderboard. Different task records may share a history or be positions in the same sequence. A future release must include documented source acquisition and licensing, separate scoring artifacts, executable adapters, and held-out histories before external evaluation is supported.

## Sources

Task families refer to [NYC TLC trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), [Calgary GTFS](https://data.calgary.ca/), Dask flight-data workflows, [GH Archive](https://www.gharchive.org/), and [Wikimedia pageviews](https://dumps.wikimedia.org/other/pageviews/). Source data are not redistributed here; consult each provider's applicable terms before acquisition or reuse.

## Status

Research prototype. Results and proposed methods are exploratory. No license is granted by this repository at present; source datasets retain their respective providers' terms.
