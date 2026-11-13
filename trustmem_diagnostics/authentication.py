"""Offline raw-content checks; these never provide feedback to an acting reader."""
from collections import defaultdict
from trustmem_runtime.data import canonical, history
from .support import assess


def authenticate(receipts, tables):
    rows=[];claims=defaultdict(set)
    valid=[]
    for receipt in receipts:
        source=receipt.get("source_id");kind=receipt.get("kind")
        signature=(source,kind,receipt.get("scope_a"))
        claims[signature].add(canonical(receipt))
        if source not in tables:
            rows.append(dict(status="unknown_source",source_id=source,kind=kind));continue
        table=tables[source]
        expected=None
        keys=[]
        if kind=="full":
            expected=dict(kind=kind,source_id=source,table=table);keys=list(expected)
        elif kind=="group":
            a=receipt.get("scope_a")
            expected=dict(kind=kind,source_id=source,scope_a=a,table={a:table[a]} if a in table else {});keys=list(expected)
        elif kind=="margins":
            expected=history(table,"cross",source);keys=list(expected)
        elif kind=="range-history":
            expected=history(table,"range",source);keys=list(expected)
        if expected is None:
            rows.append(dict(status="unsupported_kind",source_id=source,kind=kind));continue
        match=canonical({k:receipt.get(k) for k in keys})==canonical(expected)
        rows.append(dict(status="authentic" if match else "invalid_content",source_id=source,kind=kind))
        if match:valid.append(receipt)
    return dict(checks=rows,valid_receipts=valid,
        invalid_content=sum(r["status"]=="invalid_content" for r in rows),
        unknown_sources=sum(r["status"]=="unknown_source" for r in rows),
        conflicting_same_observation=sum(len(values)>1 for values in claims.values()),
        scope="fixed-source canonical full/group/margins/range-history contracts, not arbitrary prose consistency")


def assess_authenticated(*,receipts,tables,task,source_id,unassessed_text=False):
    checked=authenticate(receipts,tables)
    support=assess(task=task,source_id=source_id,receipts=checked["valid_receipts"],unassessed_text=unassessed_text)
    return dict(support=support,invalid_content=checked["invalid_content"],
        unknown_sources=checked["unknown_sources"],conflicting_same_observation=checked["conflicting_same_observation"],
        checks=checked["checks"])
