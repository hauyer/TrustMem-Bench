"""An explicit authorized observation archive; future sources never appear early."""
import hashlib
import json
from pathlib import Path
from .data import canonical


class ObservationArchive:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.read_payload_bytes=0;self.written_payload_bytes=0

    def put(self,receipt):
        body=canonical(receipt).encode()
        ident=hashlib.sha256(body).hexdigest()
        path=self.path/(ident+".json")
        if not path.exists():
            path.write_bytes(body);self.written_payload_bytes+=len(body)
        return ident

    def catalog(self):
        rows=[]
        for path in sorted(self.path.glob("*.json")):
            obj=json.loads(path.read_bytes())
            rows.append(dict(id=path.stem,source_id=obj["source_id"],kind=obj["kind"],scope_a=obj.get("scope_a")))
        return rows

    def get(self,ident):
        if not isinstance(ident,str) or len(ident)!=64 or any(c not in "0123456789abcdef" for c in ident):
            raise ValueError("Invalid archive identity")
        path=self.path/(ident+".json")
        if not path.exists():raise ValueError("Observation not yet available in authorized archive")
        body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=ident:raise ValueError("Archive content identity mismatch")
        self.read_payload_bytes+=len(body)
        return json.loads(body),len(body)
