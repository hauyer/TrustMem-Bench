# One public-stream pilot with qualified claims

The adaptive Wikimedia pilot used frozen `native-reader-2` and actual local/native
stores. A separate continuation ran only unexecuted positions, preserving the
original first seven positions and their first failure. It is development evidence,
not independent confirmation or a system ranking.

All48 eligible positions ran:35 correct commits,2 wrong commits and11 interface
failures. Another48 GH positions were excluded as one whole history by a
before-model input-size rule. Eight generated quality histories remained controls:
an always-zero answer got62/64 correct, so they were not expanded into a claimed
challenging test.

| Condition | Correct | Wrong | Interface failures | Source bytes |
|---|---:|---:|---:|---:|
| Coverage / free | 6 | 1 | 1 | 89,646,823 |
| Coverage / tool-first | 8 | 0 | 0 | 89,646,823 |
| Mem0 / free | 2 | 0 | 6 | 45,359,446 |
| Mem0 / tool-first | 4 | 0 | 4 | 45,359,446 |
| Verbatim / free | 7 | 1 | 0 | 89,646,823 |
| Verbatim / tool-first | 8 | 0 | 0 | 89,646,823 |

Two free branches committed7,324,894 at zero-based task4 after the source changed;
the new-source truth was6,337,276. The submitted number equals the old-source
result; that equality alone does not establish the model's internal causal path.
Both tool-first branches were correct there. Separately, two8/8 tool-first streams
read45,359,446 avoidable old-source bytes beyond the ordinary exact/archive
baseline, which needed only44,287,377 new-source bytes. Ordinary recovery already
provides a solution; this is not an author-method gain or a general speedup.

Important limits preclude interpreting this table as framework quality. Reader-2
did not explicitly prescribe the required `action` key; all11 shape failures used
`type=query` and executed no query. Mem0's actual extraction returned `facts:[]`,
leaving initial retrieval empty. All branches made zero saves. All bootstrap choices
were start, so coverage and verbatim did not exercise compaction differences.

There were94 API requests:93 model responses with usage, plus1 rejected startup
request with unknown usage. Peak estimatesUSD0.406370964 plus conservative reserve
USD0.0184866 totalUSD0.424857564, not an invoice. Resource screening, startup-format
recovery and a task-local-error continuation make this an adaptive pilot.

The production `native-reader-3` now supplies an explicit action schema and examples,
without alias repair or auto-submission. It passed65 engineering checks but has no
new model effect result. Natural native-writer intake needs a positive control
before a meaningful memory-system comparison. The raw pilot results are unchanged.

[Analysis](../reports/public-pilot-v1/v4/analysis.json),
[raw-trace and compressed-ledger manifest](../reports/public-pilot-v1/manifest.json),
and [integrity review](../reports/public-pilot-v1/v4/INTEGRITY_REVIEW.md) are included.
Compressed ledgers decompress to their byte-identical originals. Raw archives,
large ordinary-preflight traces and native databases are excluded; this is not a
standalone portable CLI for the whole research workspace.
