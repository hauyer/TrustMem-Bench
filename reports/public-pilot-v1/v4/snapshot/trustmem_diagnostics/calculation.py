"""Describe selection, returned arithmetic and actual delivery as separate events."""


def diagnose(events, references, *, planned):
    if planned < len(events):
        raise ValueError("Executed states exceed the planned denominator")
    rows=[]
    for event in events:
        expected=references[str(event["index"])] if str(event["index"]) in references else references[event["index"]]
        numeric=[step for step in event.get("trace",[]) if type(step.get("result",{}).get("value")) is int]
        calculator=[step for step in numeric if step["action"]["action"]=="quality_check"]
        last=numeric[-1] if numeric else None
        submitted=event["status"]=="submitted"
        rows.append(dict(state=event["state"],backend=event.get("backend"),index=event["index"],
            status=event["status"],submitted=submitted,
            correct=submitted and event.get("value")==expected,
            wrong=submitted and event.get("value")!=expected,
            calculator_calls=event.get("calculator_calls",0),
            returned_numeric_calculator_results=len(calculator),
            calculator_returns_matching_reference=sum(step["result"]["value"]==expected for step in calculator),
            submission_agrees_with_last_calculator=(event.get("value")==calculator[-1]["result"]["value"]) if submitted and calculator else None,
            last_tool_value_matches_reference_without_submit=bool(not submitted and last and last["result"]["value"]==expected),
            last_numeric_tool_action=last["action"]["action"] if last else None,
            semantic_input_binding="unassessed; numeric agreement alone does not validate selected facts or bounds"))
    return dict(planned=planned,executed=len(events),not_run=planned-len(events),
        correct=sum(row["correct"] for row in rows),wrong=sum(row["wrong"] for row in rows),
        abstained=sum(row["status"]=="abstained" for row in rows),
        unfinished=sum(row["status"] not in ("submitted","abstained") for row in rows),
        states_selecting_calculator=sum(row["calculator_calls"]>0 for row in rows),
        calculator_calls=sum(row["calculator_calls"] for row in rows),
        returned_numeric_calculator_results=sum(row["returned_numeric_calculator_results"] for row in rows),
        calculator_returns_matching_reference=sum(row["calculator_returns_matching_reference"] for row in rows),
        submitted_agreeing_with_last_calculator=sum(row["submission_agrees_with_last_calculator"] is True for row in rows),
        correct_last_tool_value_without_submit=sum(row["last_tool_value_matches_reference_without_submit"] for row in rows),
        unit="fixed-state branch; source, policy and repeated-state grouping must be reported separately",rows=rows)
