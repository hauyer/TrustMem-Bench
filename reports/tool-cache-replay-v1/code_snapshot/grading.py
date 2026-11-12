"""Controller-only independent numeric reference using SQLite and own parsers."""
import gzip
import json
import sqlite3
from pathlib import Path


def reference(case):
    answers = {}
    for source_id, source in case["sources"].items():
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE observations(a TEXT,b TEXT,w INTEGER)")
        def records():
            path = Path(source["path"])
            if source["format"] == "weighted-jsonl":
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        item = json.loads(line)
                        yield item["a"], str(item["b"]), item["weight"]
            elif source["format"] == "gharchive":
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    for line in handle:
                        item = json.loads(line)
                        yield item["type"], item["repo"]["name"].split("/", 1)[0].lower(), 1
            elif source["format"] == "wikimedia":
                with gzip.open(path, "rb") as handle:
                    for line in handle:
                        values = line.split()
                        yield values[0].decode("ascii"), ("colon" if b":" in values[1] else "no-colon"), int(values[2])
            else:
                raise ValueError("Unknown source format")
        connection.executemany("INSERT INTO observations VALUES (?,?,?)", records())
        for index, entry in enumerate(case["tasks"]):
            if entry["source_id"] != source_id:
                continue
            task = entry["request"]
            sql, params = "SELECT COALESCE(SUM(w),0) FROM observations WHERE a=?", [task["a"]]
            if task["kind"] == "joint":
                sql += " AND b=?"
                params.append(str(task["b"]))
            elif task["kind"] == "threshold":
                sql += " AND CAST(b AS INTEGER)<=?"
                params.append(task["limit"])
            elif task["kind"] == "range":
                sql += " AND CAST(b AS INTEGER) BETWEEN ? AND ?"
                params.extend([task["lo"], task["hi"]])
            answers[index] = connection.execute(sql, params).fetchone()[0]
        connection.close()
    return answers
