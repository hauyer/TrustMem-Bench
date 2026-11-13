"""Ordinary source-bound observation caching, separate from agent memory."""
from contextlib import closing
import hashlib
import json
import sqlite3
from .data import canonical


class ToolCache:
    def __init__(self, path):
        self.path = path
        self.read_payload_bytes = 0
        self.written_payload_bytes = 0
        self.hits = 0
        self.misses = 0
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE cache(id TEXT PRIMARY KEY, source TEXT, kind TEXT, scope_a TEXT, body TEXT)")
            db.execute("CREATE INDEX scope_lookup ON cache(source,kind,scope_a)")
            db.commit()

    def get(self, source_id, scope, a):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT body FROM cache WHERE source=? AND (kind='full' OR (kind='group' AND ?='group' AND scope_a=?)) ORDER BY CASE kind WHEN 'full' THEN 0 ELSE 1 END LIMIT 1",(source_id,scope,a)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        self.read_payload_bytes += len(row[0].encode("utf-8"))
        return json.loads(row[0])

    def put(self, receipt):
        body = canonical(receipt)
        key = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.path)) as db:
            inserted = db.execute("INSERT OR IGNORE INTO cache VALUES (?,?,?,?,?)",(key,receipt["source_id"],receipt["kind"],receipt.get("scope_a"),body)).rowcount
            db.commit()
        if inserted:
            self.written_payload_bytes += len(body.encode("utf-8"))
