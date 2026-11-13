"""Fresh-process inspection of the exact common-backend cache; no source access."""
import json
import sqlite3
import sys

with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True) as db:
    receipts=[json.loads(row[0]) for row in db.execute("SELECT body FROM cache ORDER BY source")]
print(json.dumps(dict(receipts=receipts,source_reads=0)))
