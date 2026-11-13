"""Conservative, invocation-level evidence support; never infer use from citations."""
from trustmem_runtime.evidence import calculate


def assess(*, task, source_id, receipts=(), certificates=(), unassessed_text=False):
    """Certificates must come from an adapter for an authenticated host tool.

    No reference answer is accepted here: numeric agreement cannot create support.
    `not_certified` is not a proof of logical insufficiency.
    """
    values = []
    errors = []
    matching = [r for r in receipts if r.get("source_id") == source_id]
    stale = sum(r.get("source_id") != source_id for r in receipts)
    if matching:
        try:
            value = calculate(matching, task, source_id)
            if type(value) is int:
                values.append(value)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(type(exc).__name__)
    for cert in certificates:
        if (cert.get("source_id") == source_id and cert.get("task") == task
                and cert.get("kind") == "host_task_bound" and type(cert.get("value")) is int):
            values.append(cert["value"])
    unique = set(values)
    if len(unique) > 1:
        status, value = "conflicting", None
    elif unique:
        status, value = "sufficient", next(iter(unique))
    else:
        status, value = ("unknown" if unassessed_text or errors else "not_certified"), None
    return dict(status=status, supported_value=value, stale_receipts_present=stale,
                unassessed_text=unassessed_text, parser_errors=errors)


def host_certificate(result, task, source_id):
    """Only call for the runtime's task-bound query/calculate, never quality_check."""
    if type(result.get("value")) is int:
        return dict(kind="host_task_bound", value=result["value"], task=task, source_id=source_id)
    return None


def generated_not_delivered(generated_steps, visible_traces):
    """Use actual next-input trace prefixes, not tool execution as delivery proof."""
    for trace in visible_traces:
        if trace != generated_steps[:len(trace)]:
            raise ValueError("Saved input is not a prefix of the actual generated trace")
    seen = max((len(t) for t in visible_traces), default=0)
    return generated_steps[seen:]
