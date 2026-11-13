# Invocation-level delivered support

`trustmem_diagnostics.support` is a conservative diagnostic for the current structured evidence contracts, not a new memory algorithm or a general natural-language entailment checker.

It separates evidence actually present in an agent input from tool results generated after that input. Initial history can already justify an answer. A tool result produced in the last action slot, without any later agent invocation, has not been delivered to that agent. A source-free calculator's correct arithmetic does not certify that the supplied numbers describe the requested population.

`assess` accepts structured receipts and explicitly task/source-bound host certificates. The caller must authenticate certificate provenance; arbitrary agent-created dictionaries are not trusted certificates. The support decision does not take the reference answer as an input. Grading independently checks the resulting value against raw-source truth.

Statuses are `sufficient`, `not_certified`, `unknown`, and `conflicting`. `not_certified` is not a completeness or impossibility claim. Unassessed prose remains unknown. Stale-source presence is a separate flag and can coexist with sufficient current evidence. Current conflict detection compares collected computed values; it is not a complete consistency check across arbitrary receipts. The current retrospective inputs were independently checked against their raw sources. Host integrity and observation consistency are prerequisites for this limited contract.

Offline development replay of 240 existing related tasks included all192 ordinary scripted tasks and48 model branches. The192 scripted tasks all completed correctly. Of the48 model branches,35 had certified support before their final action (27 correct,5 wrong,3 unfinished), while13 remained unknown (6 correct,7 wrong). The48 branches all share one already exposed authored history, so this is neither a system ranking nor an independent confirmation estimate.

The earlier heuristic that any tool value matching gold implies sufficient delivery missed11 certified inputs;3 other matching-value branches remained unknown. These are distinct findings, not14 proved classification errors. Three unfinished branches generated a final tool result without a later input receiving it. Extra source queries under already sufficient current-task evidence are reported without assuming they have no future memory value.

Twelve deterministic sensitivity controls passed. The full local suite passed54 checks. The replay made zero new model/API calls. A fresh same-family provisional review verified the raw counts and retained the conflict-checking limitation above. This instrument supports controlled diagnosis; causal attribution and any method advantage need separate evidence.

[Byte-preserved results](../reports/delivery-support-v1/results.json), [controls](../reports/delivery-support-v1/calibration.json), [protocol](../reports/delivery-support-v1/PROTOCOL.md), and [review](../reports/delivery-support-v1/INTEGRITY_REVIEW.md) are included. The original workspace freeze references the full research archive; retrospective replay is not yet a standalone installed CLI. The reusable support module and its unit checks run without that archive.
