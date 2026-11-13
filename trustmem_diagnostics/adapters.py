"""Native-content baseline stores and capability-declared external call wrappers."""
from dataclasses import dataclass,asdict
from contextlib import closing,contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


class UnsupportedOperation(RuntimeError):pass


@contextmanager
def connection(path):
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


@dataclass(frozen=True)
class MemoryObject:
    id:str
    text:str
    revision:int

    @property
    def text_sha256(self):return hashlib.sha256(self.text.encode('utf-8')).hexdigest()


def validate_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',value):raise ValueError('Invalid local memory identity')


class SQLiteMemory:
    """Plain reference store, not a published memory-system reproduction."""
    capabilities=frozenset({'add','get','search','replace','delete'})

    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with connection(self.path) as db:db.execute('CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY,text TEXT NOT NULL,revision INTEGER NOT NULL)')

    def add(self,text):
        oid=uuid.uuid4().hex
        with connection(self.path) as db:db.execute('INSERT INTO memory VALUES (?,?,1)',(oid,text))
        return self.get(oid)

    def get(self,oid):
        with connection(self.path) as db:row=db.execute('SELECT * FROM memory WHERE id=?',(oid,)).fetchone()
        return None if row is None else MemoryObject(*row)

    def search(self,query):
        # Deliberately transparent literal baseline; not a replacement for a native retriever.
        with connection(self.path) as db:rows=db.execute('SELECT * FROM memory ORDER BY id').fetchall()
        return [MemoryObject(*r) for r in rows if query.casefold() in r[1].casefold()]

    def replace(self,oid,text,expected_revision):
        with connection(self.path) as db:
            result=db.execute('UPDATE memory SET text=?,revision=revision+1 WHERE id=? AND revision=?',(text,oid,expected_revision))
            if result.rowcount!=1:raise ValueError('Revision conflict or absent object')
        return self.get(oid)

    def delete(self,oid):
        with connection(self.path) as db:db.execute('DELETE FROM memory WHERE id=?',(oid,))


class MarkdownMemory:
    """Verbatim Markdown content; sidecar metadata does not alter model-facing text."""
    capabilities=frozenset({'add','get','search','replace','delete'})

    def __init__(self,path):self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)

    def _paths(self,oid):
        validate_id(oid)
        return self.path/(oid+'.md'),self.path/(oid+'.json')

    def _write(self,obj):
        body,meta=self._paths(obj.id)
        body.write_bytes(obj.text.encode('utf-8'))
        meta.write_text(json.dumps({'id':obj.id,'revision':obj.revision,'text_sha256':obj.text_sha256}),encoding='utf-8')
        return obj

    def add(self,text):return self._write(MemoryObject(uuid.uuid4().hex,text,1))

    def get(self,oid):
        body,meta=self._paths(oid)
        if not body.exists() and not meta.exists():return None
        metadata=json.loads(meta.read_text(encoding='utf-8'));obj=MemoryObject(oid,body.read_bytes().decode('utf-8'),metadata['revision'])
        if obj.text_sha256!=metadata['text_sha256']:raise ValueError('Content and metadata mismatch')
        return obj

    def search(self,query):
        rows=[self.get(p.stem) for p in sorted(self.path.glob('*.json'))]
        return [r for r in rows if query.casefold() in r.text.casefold()]

    def replace(self,oid,text,expected_revision):
        old=self.get(oid)
        if old is None or old.revision!=expected_revision:raise ValueError('Revision conflict or absent object')
        # This simple file baseline is sequential, not a cross-process transactional store.
        return self._write(MemoryObject(oid,text,old.revision+1))

    def delete(self,oid):
        for p in self._paths(oid):p.unlink(missing_ok=True)


class DelegatedMemory:
    """Invoke explicitly supplied native functions; never silently emulate an absent API."""
    def __init__(self,name,version,operations):
        if not name or not version or any(not callable(v) for v in operations.values()):raise ValueError('Declare version and callable native operations')
        self.name=name;self.version=version;self.operations=operations;self.capabilities=frozenset(operations)

    def invoke(self,operation,**kwargs):
        if operation not in self.operations:raise UnsupportedOperation(operation)
        return self.operations[operation](**kwargs)
