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


def scan(source, group=None):
    """Actually scan a bound source, without a hidden reference answer."""
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
                if group is None or a == group:
                    table[a][b] += weight
        else:
            seen_target = False
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
                    if group is not None and source.get("group_contiguous") and seen_target and a != group:
                        break
                    if group is None or a == group:
                        table[a][b] += weight
                        seen_target = True
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
