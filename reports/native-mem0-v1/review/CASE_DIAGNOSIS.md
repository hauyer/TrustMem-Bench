# Posthoc case diagnosis

All 12 retained cases in one authored two-version engineering workload. Posthoc semantic calibration by this fresh reviewer; not an independent human-labeled benchmark, not a new automated support metric and not a causal mechanism study.

A is the initial source, B its revised version. The frozen results retain `native_text_support=unassessed`.

The initial margins bound the selected correct count to [75,80] of 80: [93.75%,100%]. They fix the 90% gate to 1 but do not fix the 99% gate. Source A's complete table gives 76/80=95%; B gives 80/80=100%.

| Arm/session | Source/threshold | Truth → submitted | Query/source bytes | Posthoc diagnosis |
|---|---|---|---|---|
| mem0/s00 | A/90% | 1 → 1 | 1/154 | Correct after an avoidable query. Delivered accurate current-source margins imply a lower selected-correct count of 75 out of 80, so the 90% gate is already 1. This diagnoses information sufficiency, not whether the reader actually used the bound. |
| mem0/s01 | A/99% | 0 → 0 | 1/0 | Correct after cache-hit query. The prior s00 extraction contained all joint cells, but its update response retained the old marginal text; retained s00 inventory and s01 delivery lack those cells. Margins allow both 0 and 1 at 99%, so query is justified by what was delivered. This is an observed consolidation omission, not retrieval nondelivery; no counterfactual error reduction is established. |
| mem0/s02 | A/99% | 0 → 1 | 0/0 | Current-source full cells 76 correct and 4 incorrect at confidence 90 are actually delivered and cited. The selected share is 76/80=95%, below 99%; submission 1 is wrong. Missing facts, retrieval nondelivery and stale-source substitution do not explain this retained trace. Arithmetic versus task/threshold interpretation versus other reader failure cannot be separated without additional evidence. |
| mem0/s03 | B/99% | 1 → 1 | 1/154 | Only old source-A notes are delivered before querying new source B. Query returns the B table and gate 1, then the reader submits 1. Its old-A note citation alone does not support the current gate; current tool evidence does. No causal use of the citation is established. |
| mem0/s04 | B/90% | 1 → 1 | 0/0 | Accurate source-B cells are delivered and cited: 80 correct and 0 incorrect selected, share 100%, so the 90% gate is 1. Old source-A notes coexist as historical facts. This is compatible with successful reuse, not proof of causal note use. |
| mem0/s05 | A/99% | 0 → 1 | 0/0 | On return to source A, its accurate full cells are actually delivered and cited even while source-B history remains. The current share is 76/80=95%, so the 99% gate is 0, but submission is 1. The trace does not establish stale-source use; the cited source matches. Exact reader failure mechanism is undetermined. |
| verbatim/s00 | A/90% | 1 → 0 | 0/0 | The complete unchanged initial margins are delivered and cited. The selected-correct count is at least 95+80-100=75 of 80, so its share is at least 93.75% and the 90% gate is 1. Submission 0 is wrong despite sufficient notes; exact arithmetic versus interpretation failure is undetermined. |
| verbatim/s01 | A/99% | 0 → 0 | 1/154 | Initial margins permit selected-correct counts from 75 to 80, spanning the 99% threshold, so they do not fix this gate. Query scans source A, returns its complete table and exact gate 0, and submission is correctly 0. No prior joint observation had been acquired by this arm. |
| verbatim/s02 | A/99% | 0 → 1 | 0/0 | The newly appended source-A full observation is delivered and cited as note-1. Its selected counts 76 and 4 imply 95%, below 99%, hence gate 0. Submission 1 is wrong despite intact fully delivered memory; exact reader failure mechanism is undetermined. |
| verbatim/s03 | B/99% | 1 → 1 | 1/154 | Only source-A notes exist before the new source-B request. The reader queries B and correctly submits gate 1 from current tool evidence. It declares no citations. This is an expected source transition, not a demonstrated stale-source error. |
| verbatim/s04 | B/90% | 1 → 1 | 0/0 | Source-B full note-2 is delivered and cited. Selected counts 80 correct and 0 incorrect imply gate 1 at 90%. This is compatible with note reuse but does not establish causal adoption. |
| verbatim/s05 | A/99% | 0 → 1 | 0/0 | Source-A full note-1 remains intact, is delivered and is cited after returning from B. The selected share is 95%, so the 99% gate is 0, but submission is 1. Neither data omission nor source-mismatched citation explains the observed failure; exact reader mechanism is undetermined. |

All five errors occur despite semantically sufficient current-source information being delivered. These traces do not distinguish calculation error, threshold interpretation, instruction following or another reader failure. The calculator was not available as a model-selectable action in this pilot.

One separate native writer omission is directly visible: after mem0/s00 the extraction contains the full source-A table, but the update retains the old margins (API log lines 5–6; `models/mem0/s00/write-result.json:5`; `models/mem0/mem0-s00-inventory.json:16`). The next task queries a source-bound cache and the subsequent writer installs the full table. This omission does not explain the later wrong outputs, which already received those full values.

Per-case evidence is listed in CASE_DIAGNOSIS.json. No frozen results, inputs, native store or retained API output were changed.
