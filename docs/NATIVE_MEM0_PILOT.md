# Native Mem0: first persistent writer/search/reader development loop

2026-11-13. Optional adapter qualification, not a leaderboard or a memory-method win. Core benchmark execution still needs only Python's standard library. The adapter pins **mem0ai1.0.11, qdrant-client1.20.0, fastembed0.8.0, pydantic2.13.5**, with an existing offline BGE-small ONNX model (384 dimensions).

## What actually runs

`trustmem_diagnostics.native_mem0.Mem0Store` calls native infer=True add, native vector search, native explicit update and get_all. Qdrant and Mem0 history use real local disk paths. Default extraction/update prompts remain unchanged. The only provider substitutions route LLM text through a metered callable and embeddings through the pinned local model. Graph memory and reranking are not enabled. Mem0 transport failures remain visible even where the native updater catches an exception.

The public website currently describes different signatures/semantics; this adapter targets the installed version's source, not every current Mem0 platform/SDK. There is no silent version upgrade.

The zero-API smoke uses two declared scripted writer responses to exercise actual native extraction and ADD. It then performs native search, native explicit update and independent-process disk reopen. Scripted responses qualify transport/storage, not a model's ability. A portable zero-API smoke is available after installing the optional dependencies and supplying an existing offline model:

```bash
python -B examples/mem0_native_smoke.py --embedding-path /path/to/existing/bge-onnx --output local-runs/mem0-smoke
```

## Paid reader pilot: same experience, two storage paths

One authored two-version quality task, six sequential sessions per backend. Mem0 receives the true initial margins and all tool observations it acquires, through ordinary infer=True writing. The verbatim reference appends the same type of original text. Both readers use the same non-thinking DeepSeek configuration, system prompt, current identity and query tool. Each sees only the text actually retrieved by its backend. Diagnostic get_all contents are not secretly shown to the reader.

Mem0 native search runs in a fresh Python process at every session. Reader API calls are stateless fresh payloads orchestrated by the runner; the LLM client itself is not a separately isolated process. Tool results are real scans or source-bound cache hits. A wrong submitted value commits unchanged. Tool observations are ingested at session end for later use; native Mem0 chooses its own ADD/UPDATE/NONE behavior.

The pilot protocol did **not** offer a model-selectable local arithmetic/calculation action. The query tool supplies an exact gate along with the table. Consequently errors after retrieval cannot establish a memory-system deficit beyond ordinary calculator-assisted planning. A same-evidence arithmetic control is the next needed diagnostic, not a new author mechanism.

## Actual outcomes

| Backend | Correct / planned | Wrong | Query invocations | Actual source-content reads |
|---|---:|---:|---:|---:|
| Native Mem0 | 4/6 | 2 | 3 | 308 B |
| Verbatim complete notes | 3/6 | 3 | 2 | 308 B |

All12 sessions submitted; no abstention, truncation or interface retry. Each backend has two real cache misses; Mem0 has one additional cache hit. Common initial history formation reads154 B once in setup. This tiny file is an engineering environment; it is not an expensive industrial verification workload. Do not turn an extra cached query into extra physical-source cost.

25 actual model calls: 8 native-writer, 9 Mem0-reader, 8 verbatim-reader. Recorded totals are **24,129 input /1,601 output tokens**, peak estimate **USD0.005360538**, below48calls/USD0.10. Pricing estimates are not invoices. Mem0 writer USD0.002653578, Mem0 reader USD0.001869228, verbatim reader USD0.000837732; local embedding/storage/transport time and byte costs are not fully profiled. Native-writer and reader expense are not pooled into a misleading read-only comparison.

The two repeated99% false decisions were submitted as1 in both arms even though full correct source numbers were delivered. Native memories retained the original source alongside the new one. This is a useful diagnostic candidate about consuming saved evidence, but one fixed-order, single-seed development stream cannot distinguish stable threshold interpretation, output variation or a channel-specific memory cause. A complete-note reference also failed, so Mem0's compression/retrieval is not established as the cause.

## Limits and next work

This qualifies a reusable native adapter plus one real execution of framework inference and persistence on authored data. It is not production history, independent native-source confirmation, fair ranking against fully calculator-equipped agents, or proof of general memory failure. Natural-language support labels initially remain unassessed; any posthoc case check is separately labeled fresh-model-reviewer semantic calibration, with no independent human annotation. Existing exact-structured policies stay as strong controls.

The lifecycle pilot reuses the benchmark task backend and independent scorer in a separate frozen runner; it is not yet a native-backend option in every `trustmem_runtime.suite` task. The adapter, portable smoke and retained logs are real increments toward that interface. Source isolation, background/concurrent writes, deletion, graph/reranker options and broad version compatibility are not claimed.

[The retained artifact manifest](../reports/native-mem0-v1/manifest.json) includes the frozen runner, protocol, first-response API ledger, actual delivered text, submissions and both backend outcomes. Private native stores and embedding weights are excluded; exported inventory/readback records show what was stored and delivered.
