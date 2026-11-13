"""Public exact arithmetic for explicitly documented evidence contracts.

This is an ordinary calculator shared by all policies, not a proposed method.
"""
from fractions import Fraction


def quality_value(receipts, task):
    """A nonempty selected population must satisfy the rational quality gate."""
    selected = None
    numerator = None
    bounds = None
    for receipt in receipts:
        if receipt["kind"] == "full":
            selected = sum(w for cells in receipt["table"].values() for b, w in cells.items() if int(b) >= task["cutoff"])
            numerator = sum(w for b, w in receipt["table"].get(task["a"], {}).items() if int(b) >= task["cutoff"])
        elif receipt["kind"] == "group" and receipt["scope_a"] == task["a"]:
            numerator = sum(w for b, w in receipt["table"].get(task["a"], {}).items() if int(b) >= task["cutoff"])
        elif receipt["kind"] == "margins":
            selected = sum(w for b, w in receipt["right"].items() if int(b) >= task["cutoff"])
            correct = receipt["left"].get(task["a"], 0)
            bounds = max(0, correct + selected - receipt["total"]), min(correct, selected)
    if selected is None:
        return None
    if selected == 0:
        return 0
    low, high = (numerator, numerator) if numerator is not None else bounds or (None, None)
    if low is None:
        return None
    if low * task["denominator"] >= selected * task["numerator"]:
        return 1
    if high * task["denominator"] < selected * task["numerator"]:
        return 0
    return None


def target(cells, task):
    if task["kind"] == "marginal":
        return sum(cells.values())
    if task["kind"] == "joint":
        return cells.get(str(task["b"]), 0)
    if task["kind"] == "threshold":
        return sum(v for b, v in cells.items() if int(b) <= task["limit"])
    if task["kind"] == "range":
        return sum(v for b, v in cells.items() if task["lo"] <= int(b) <= task["hi"])
    raise ValueError("Unknown task")


def range_value(records, task, domain):
    """Find a rational linear combination of retained interval observations."""
    rows, basis = [], {}
    for record in records:
        if record["a"] != task["a"]:
            continue
        vector = [Fraction(int(record["lo"] <= b <= record["hi"])) for b in domain]
        value = Fraction(record["value"])
        for pivot, (old, old_value) in sorted(basis.items()):
            factor = vector[pivot]
            vector = [x - factor*y for x, y in zip(vector, old)]
            value -= factor * old_value
        pivot = next((i for i, v in enumerate(vector) if v), None)
        if pivot is not None:
            factor = vector[pivot]
            basis[pivot] = ([x/factor for x in vector], value/factor)
    query = [Fraction(int(task["lo"] <= b <= task["hi"])) for b in domain]
    result = Fraction(0)
    for pivot, (vector, value) in sorted(basis.items()):
        factor = query[pivot]
        query = [x-factor*y for x, y in zip(query, vector)]
        result += factor*value
    return int(result) if not any(query) and result.denominator == 1 else None


def calculate(receipts, task, source_id):
    """Return a value only when cited, source-matching observations justify it."""
    if task["kind"] == "quality":
        return quality_value([r for r in receipts if r["source_id"] == source_id], task)
    for receipt in receipts:
        if receipt["source_id"] != source_id:
            continue
        if receipt["kind"] in ("full", "group"):
            if receipt["kind"] == "full" or receipt["scope_a"] == task["a"]:
                return target(receipt["table"].get(task["a"], {}), task)
        if receipt["kind"] == "range-history" and task["kind"] == "range":
            value = range_value(receipt["observations"], task, receipt["domain"])
            if value is not None:
                return value
        if receipt["kind"] == "margins":
            a_total = receipt["left"].get(task["a"], 0)
            if task["kind"] == "marginal":
                return a_total
            if task["kind"] == "joint":
                b_total = receipt["right"].get(str(task["b"]), 0)
            elif task["kind"] == "threshold":
                b_total = sum(v for b,v in receipt["right"].items() if int(b) <= task["limit"])
            else:
                continue
            lower = max(0, a_total + b_total - receipt["total"])
            upper = min(a_total, b_total)
            if lower == upper:
                return lower
    return None
