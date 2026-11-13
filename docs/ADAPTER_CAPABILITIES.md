# Adapter capabilities and measurement limits

2026-11-13. `implemented-local`, `trace-only`, `bridge-only`, and `docs-reviewed-not-run` are different integration states.

| Adapter | Status | Actual operations | Important limitation |
|---|---|---|---|
| SQLite reference store | implemented-local, offline tests | Verbatim add/get/literal search/revision-checked replace/delete | Own simple baseline; no semantic extraction or published-system claim |
| Markdown reference store | implemented-local, offline tests | Verbatim body plus hash/revision sidecar; same five operations | Sequential writes; no cross-process transaction guarantee; detects sidecar/body mismatch |
| SAP | trace-only, real saved logs/SQL read | Read decisions, delivered memories, quotes, invoices and readback | No live external retriever; semantic citations and causal memory use unobserved |
| Delegated native API | bridge-only, contract tested with a test fixture | Calls only explicitly supplied operations and declares version | User must supply native SDK integration; missing operations raise `UnsupportedOperation` |
| Mem0 | docs-reviewed-not-run | Add/update documented; no native SDK run in this increment | No performance result or installed-version compatibility certified |
| Letta | docs-reviewed-not-run | Stateful agent/memory documentation reviewed | No integration, background consistency or performance result |
| LangMem | docs-reviewed-not-run | Hot-path and background memory primitives documented | No integration or performance result |

Mem0's current documentation distinguishes [additive add](https://docs.mem0.ai/core-concepts/memory-operations/add) from [explicit update](https://docs.mem0.ai/core-concepts/memory-operations/update). Wrappers must distinguish these operations and verify the installed/platform version. This is not a retrospective change to E1's old interface result. [Letta](https://docs.letta.com/v1-sdk/concepts/stateful-agents) and [LangMem](https://langchain-ai.github.io/langmem/) are integration references, not evaluated baselines here.

Every real system run needs a capability declaration: system and SDK/commit version, writer and reader models, operation mapping, retrieval mode, visibility of internal calls and candidates, fork/replay support, concurrent-write semantics, namespaces, export restrictions and cost visibility. The adapter must not normalize all returned content into a hand-written ideal coverage graph. Preserve raw native responses before any lossless transport conversion.

If an internal metric is unavailable, publish `unobservable`. If an operation does not exist, publish `unsupported`, including the system version. Do not score either as a successful zero or a business failure. Evaluate actual available actions and end-to-end results, with unsupported capability coverage shown alongside them.

Use `DelegatedMemory(name, version, operations)` only as an extension point. Supplying an `add` callable does not authorize `replace` emulation. These adapters expose no hidden scoring labels to the model. Source/version checks for a memory's evidence belong to the declared task contract, not to the memory store's universal definition of truth.
