# Third-party sources and scope

The MIT license covers the original TrustMem-Bench code listed in `OWN_CODE.txt`. Upstream inputs and model weights follow their respective authors' terms. Manuscript figures and statistical summaries are identified separately in `RELEASE_LOCK.json`.

| Source | Frozen version and access | Content in this archive |
|---|---|---|
| ReScopeBench data | [Data card and Apache-2.0 label](https://huggingface.co/datasets/JoeYing/ReScopeBench/tree/f726fd6939a77440992dc433872acf2d2d03d158) | Hashes, source routes, and aggregated measurements |
| ReScopeBench runtime | [Pinned GitHub commit](https://github.com/JoeYing1019/ReScopeBench/tree/4780ba60e61b8dd41e86a370560ca72de3e9ed61) | Hashes and retrieval routes. The upstream Hermes component has its own MIT notice. |
| SkillHorizon | [Pinned notices](https://github.com/HKUST-KnowComp/SkillHorizon/blob/1749e7439fdafb75426d7bfecbd4b657509ebe1c/THIRD_PARTY_NOTICES.md) | Metric summaries, revision and result hashes, and original reproduction code. The pinned release specifies no project license. The Git checkout is retrieved from the authors' host for local evaluation. |
| P4 & P4b open-weight model providers | Frozen protocols in `modules/p4/` and `modules/p4b/` list checkpoints (`Qwen/Qwen3-32B`, `LLM-Research/Llama-3.3-70B-Instruct`, `mistralai/Mistral-Small-24B-Instruct-2501`, `Qwen/Qwen2.5-7B-Instruct`, `LLM-Research/Meta-Llama-3.1-8B-Instruct`) | Model names, derived opening-level outcomes, aggregate tables, and original runners |

## Public package boundary vs. separately requested recordings

This package omits upstream runtime bytes, upstream case payloads, frozen environment snapshots, SkillHorizon task-level traces, and raw P4/P4b model decision tapes. Using only this archive, readers can verify all packaged hashes and tables, rebuild P3 and SkillHorizon locally from pinned upstreams, run the P3 external diagnosis interface with custom predictors, and stage fresh P4/P4b runtimes for new inference.

Replaying the original recorded P4 (`p4_all_results.tar.gz`, SHA-256 `d86e8da54d101a1b8a88721285496fe7bb7bb45a4b34f4fe3df36c8de5f7ada6`) and P4b (`p4b_all_results.tar.gz`, SHA-256 `f2347193cffaec118a6d68f5f3942ac75f097c4bfe088e82f07fb924b25015fd`) model decisions or recounting individual tool traces requires the original decision recordings. Requests for those recordings and associated scoring reports may be addressed to the corresponding author at the email on the manuscript title page, specifying the run and intended use, subject to applicable upstream licensing terms.
