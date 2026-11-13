# All-state parameter and delivery diagnosis

Posthoc fresh-model review calibration, **not independent human annotation**. Requested reviewer: gpt-6.1-sol/ultra; actual backend identity not independently attested. Same-family/provisional assurance. Original unassessed labels and all paid outputs remain unchanged.

The9 required-arm calculator calls are mathematically correct for their supplied inputs. All9 copy the current task threshold correctly;8 use the correct selected counts. `verbatim-s03` uses80/100 rather than80/80. Six correct calculator values are delivered; two correct and one wrong intermediate values are never submitted.

| State | Reference | Fresh control | Optional calculator | Required actions | Required outcome | Parameter/delivery review |
|---|---:|---|---|---|---|---|
| mem0-s00 | 1 | 1 (correct) | 1 (correct) | query → quality_check | unfinished | Initial margins already suffice via75/80 lower bound; redundant query, then final-slot calculator instead of submit; correct intermediate1 but no delivery. |
| mem0-s01 | 0 | 1 (wrong) | 0 (correct) | query → submit | 0 (correct) | Necessary query then correct submitted gate; no calculator execution. |
| mem0-s02 | 0 | 1 (wrong) | 1 (wrong) | quality_check → submit | 0 (correct) | Evidence-bound exact calculation then correct submitted gate. |
| mem0-s03 | 1 | 1 (correct) | 1 (correct) | query → submit | 1 (correct) | Necessary query then correct submitted gate; no calculator execution. |
| mem0-s04 | 1 | 1 (correct) | 1 (correct) | quality_check → submit | 1 (correct) | Evidence-bound exact calculation then correct submitted gate. |
| mem0-s05 | 0 | 1 (wrong) | 1 (wrong) | quality_check → submit | 0 (correct) | Evidence-bound exact calculation then correct submitted gate. |
| verbatim-s00 | 1 | 1 (correct) | 1 (correct) | query → quality_check | unfinished | Initial margins already suffice via75/80 lower bound; redundant query, then final-slot calculator instead of submit; correct intermediate1 but no delivery. |
| verbatim-s01 | 0 | 0 (correct) | 0 (correct) | query → submit | 0 (correct) | Necessary query then correct submitted gate; no calculator execution. |
| verbatim-s02 | 0 | 0 (correct) | 0 (correct) | quality_check → submit | 0 (correct) | Evidence-bound exact calculation then correct submitted gate. |
| verbatim-s03 | 1 | 1 (correct) | 1 (correct) | query → quality_check | unfinished | Necessary current-source query, then final-slot calculator instead of submit; wrong selected denominator80/100 produces wrong intermediate0; no committed wrong action. |
| verbatim-s04 | 1 | 1 (correct) | 1 (correct) | quality_check → submit | 1 (correct) | Evidence-bound exact calculation then correct submitted gate. |
| verbatim-s05 | 0 | 1 (wrong) | 1 (wrong) | quality_check → submit | 0 (correct) | Evidence-bound exact calculation then correct submitted gate. |

The initial90% states have current-source margins: total100, correct95, selected80. Their selected-correct count is in[75,80], so75/80=93.75% already proves gate1. The first query in those two states was redundant under the conditional instruction. The initial99% margin states need a query because[93.75%,100%] straddles99%; the changed-source99% states need current-source evidence. Full observations at the remaining states give76/80 or80/80 directly.

The reported12/12 first-tool metric verifies only the first action type. The complete two-action instruction is followed in9/12 cases. Three query→calculator sequences use the terminal slot for another tool. None was stopped by a monetary cap, API failure, malformed argument, or arithmetic exception. Increasing the budget after the fact would change the policy and cannot replace these outcomes.

This calibration supports an explicit denominator-binding defect in one intermediate calculation. It does not certify arbitrary natural-language support judgments, establish a causal mechanism for the optional arm, or convert unfinished cases into delivered tasks.
