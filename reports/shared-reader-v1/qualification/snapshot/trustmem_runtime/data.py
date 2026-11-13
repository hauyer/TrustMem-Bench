"""Native readers. Reference scoring deliberately uses a separate SQL path."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Meter:
    def __init__(self, stream):
        self.stream, self.bytes = stream, 0

    def read(self, n=-1):
        data = self.stream.read(n)
        self.bytes += len(data)
        return data


def scan(source, group=None, *, groups=None):
    """Actually scan a bound source, without a hidden reference answer."""
    if groups is not None and (group is not None or not groups):
        raise ValueError("Supply a single group or a nonempty group set")
    selected = frozenset(groups) if groups is not None else None if group is None else frozenset((group,))
    started = perf_counter()
    table = defaultdict(lambda: defaultdict(int))
    path = Path(source["path"])
    with path.open("rb") as raw:
        meter = Meter(raw)
        if source["format"] == "weighted-jsonl":
            for line in iter(lambda: meter.stream.readline(), b""):
                meter.bytes += len(line)
                row = json.loads(line)
                a, b, weight = row["a"], str(row["b"]), row["weight"]
                if type(weight) is not int or (source.get("nonnegative") and weight < 0):
                    raise ValueError("Weights must be integers")
                if selected is None or a in selected:
                    table[a][b] += weight
        elif source["format"] == "openml-arff-confidence":
            import csv
            from decimal import Decimal
            started_data = False
            for line in iter(lambda: meter.stream.readline(), b""):
                meter.bytes += len(line)
                if not started_data:
                    started_data = line.strip().lower() == b"@data"
                    continue
                if not line.strip() or line.lstrip().startswith(b"%"):
                    continue
                row = next(csv.reader([line.decode("utf-8")]))
                if len(row) != 13:
                    raise ValueError("Expected pinned seven-class OpenML prediction schema")
                probabilities = [Decimal(x) for x in row[4:11]]
                prediction, truth = int(row[11]), int(row[12])
                score = max(probabilities) * 100
                if (not all(Decimal(0) <= x <= Decimal(1) for x in probabilities)
                    or abs(sum(probabilities) - 1) > Decimal("1e-12")
                    or not 1 <= prediction <= 7 or not 1 <= truth <= 7
                    or probabilities[prediction - 1] != max(probabilities) or score != int(score)):
                    raise ValueError("Unsupported prediction probabilities or labels")
                a, b = "correct" if prediction == truth else "incorrect", str(int(score))
                if selected is None or a in selected:
                    table[a][b] += 1
            if not started_data:
                raise ValueError("Missing ARFF data section")
        else:
            seen = set()
            with gzip.GzipFile(fileobj=meter, mode="rb") as data:
                for line in data:
                    if source["format"] == "gharchive":
                        event = json.loads(line)
                        a = event["type"]
                        owner, sep, name = event["repo"]["name"].partition("/")
                        if not (owner and owner.isascii() and sep and name):
                            raise ValueError("Unsupported repository identity")
                        b, weight = owner.lower(), 1
                    elif source["format"] == "wikimedia":
                        domain, title, views, _ = line.rstrip(b"\r\n").split(b" ")
                        a, b, weight = domain.decode("ascii"), "colon" if b":" in title else "no-colon", int(views)
                    else:
                        raise ValueError("Unknown native format")
                    if selected is not None and source.get("group_contiguous") and seen == selected and a not in selected:
                        break
                    if selected is None or a in selected:
                        table[a][b] += weight
                        if selected is not None:
                            seen.add(a)
    return {a: dict(values) for a, values in table.items()}, {"source_read_bytes": meter.bytes, "scan_seconds": perf_counter() - started}


def history(table, mechanism, source_id):
    if mechanism == "range":
        if any(int(b) not in (1,2,3,4) for cells in table.values() for b in cells):
            raise ValueError("Range development contract has domain 1..4")
        observations = []
        for a, cells in table.items():
            for lo, hi in ((1, 3), (3, 3)):
                observations.append({"a": a, "lo": lo, "hi": hi,
                    "value": sum(v for b, v in cells.items() if lo <= int(b) <= hi)})
        return {"source_id": source_id, "kind": "range-history", "domain": [1, 2, 3, 4], "observations": observations}
    left, right = defaultdict(int), defaultdict(int)
    for a, cells in table.items():
        for b, value in cells.items():
            if value < 0:
                raise ValueError("Count mechanisms require nonnegative weights")
            left[a] += value
            right[b] += value
    return {"source_id": source_id, "kind": "margins", "left": dict(left), "right": dict(right), "total": sum(left.values())}
