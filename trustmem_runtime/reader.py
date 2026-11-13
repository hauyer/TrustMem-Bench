"""Shared native-note reader contract; no model dependency and no hidden gold."""
import json
from pathlib import Path
from .calculator import quality_check
from .data import canonical, scan
from .evidence import calculate


CONTRACT_VERSION = "native-reader-3"
ACTION_SCHEMA = {"type":"object","required":["action"],"properties":{
    "action":{"type":"string","enum":["query","recover","calculate","quality_check","save","submit","abstain"]},
    "scope":{"enum":["group","full"]},"archive_id":{"type":"string"},
    "evidence":{"type":"array","items":{"type":"string"}},"receipt_id":{"type":"string"},
    "value":{"type":"integer"},"citations":{"type":"array","items":{"type":"string"}}}}
SYSTEM = """Continue a multi-session workflow using only the supplied notes and tools.
Current source identity and the current request are authoritative. Old-source notes
may be valid history, but do not support this source. Each source is a weighted
table over a,b. marginal sums group a; joint selects a,b; threshold selects a and
b<=limit; range selects a and lo<=b<=hi. quality returns 1 iff the selected rows
with b>=cutoff are nonempty and their share belonging to a>=numerator/denominator.
For nonnegative counts, marginal totals bound a joint count by
max(0,a_total+b_total-total)..min(a_total,b_total). A bound may decide a gate.
Return exactly one JSON object with the required string key "action" and the
appropriate argument fields at the top level. For example a source query is
{"action":"query","scope":"full"}; a calculator request is
{"action":"calculate","evidence":["an-available-ID"]}. The key "action" is
required for every operation. Use the action_schema supplied in the input.
Tools consume actions, including failed tools:
query(scope:group|full) obtains a current-source observation, using the common
persistent cache if covered; it returns a task-bound value when justified.
recover(archive_id:ID) reads an already available authorized historical observation
from archive_catalog without scanning its original source. Only cataloged past
observations are available. Archive transport/storage costs are counted separately.
calculate(evidence:[IDs]) uses complete JSON receipt literals in specified notes
and acquired observations; it returns null if this format/contract does not certify
the request. Null is not proof that the prose is uninformative. The tool does not
translate paraphrased prose. quality_check(selected_correct,selected_total,
threshold_numerator,threshold_denominator) performs exact arithmetic on supplied
integers; it does not validate their source, population or threshold binding.
save(receipt_id:ID) stores an acquired observation through the same memory backend
for later sessions. submit(value:integer,citations:[IDs]) commits unchanged;
abstain ends without a deliverable. No gold feedback, automatic repair or automatic
commit is provided. Enough current evidence permits direct submission. Query only
if needed for the declared task or an explicit future-retention decision.
remaining_actions includes your present action. When it equals 1, only submit or
abstain can end with a completed decision. A final tool result without a later
reader invocation is generated but has not been delivered to you. Allowed actions
are not masked by the host. The task stream after the current request is hidden.
"""
TOOL_FIRST = """\nOrdinary tool-first comparison policy: use calculate/quality_check when
current notes justify the result; otherwise query. Submit after a sufficient result.
With one action remaining, submit or abstain. This is an instruction, not host enforcement.
"""


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def note_receipts(text):
    """Decode complete JSON receipt literals only, without a semantic extractor."""
    result = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value,dict) and value.get("kind") in ("full","group","margins","range-history") and "source_id" in value:
            result.append(value)
    return result


class CaseTools:
    """Actual current-source scans/cache; grader is deliberately absent."""
    def __init__(self, sources, cache=None, archive=None):
        self.sources, self.cache, self.archive = sources, cache, archive

    def query(self, source_id, task, scope):
        if scope not in ("group", "full"):
            raise ValueError("scope must be group or full")
        receipt = self.cache.get(source_id,scope,task["a"]) if self.cache else None
        hit = receipt is not None
        cost = dict(source_read_bytes=0,scan_seconds=0.0)
        if receipt is None:
            table,cost = scan(self.sources[source_id],task["a"] if scope=="group" else None)
            receipt = dict(kind=scope,source_id=source_id,table=table)
            if scope=="group":
                receipt["scope_a"]=task["a"]
            if self.cache:
                self.cache.put(receipt)
        if self.archive:
            self.archive.put(receipt)
        return receipt,dict(**cost,backend_cache_hit=hit)


def run_session(*, task, source_id, notes, respond, tools, output, save=None,
                max_actions=4, mode="free", session_id="s00"):
    """`respond(system,payload)` returns one action; native writer injected by save.

    The caller retrieves notes before this call and preserves them verbatim. No
    reference is accepted. Evaluation takes place after the stream in a caller.
    """
    if type(max_actions) is not int or max_actions<1 or mode not in ("free","tool_first"):
        raise ValueError("Invalid frozen reader configuration")
    if len({n["id"] for n in notes})!=len(notes) or any(not isinstance(n.get("memory"),str) for n in notes):
        raise ValueError("Notes require distinct IDs and original memory text")
    if any(n["id"].startswith("observation:") for n in notes):
        raise ValueError("Native IDs cannot use the transient observation namespace")
    out=Path(output)
    out.mkdir(parents=True,exist_ok=False)
    dump(out/"contract.json",dict(version=CONTRACT_VERSION,mode=mode,max_actions=max_actions,
        task=task,current_source_id=source_id,note_ids=[n["id"] for n in notes],
        host_masks_actions=False,host_repairs=False,model_calls_by_runtime=0))
    system=SYSTEM+(TOOL_FIRST if mode=="tool_first" else "")
    (out/"system.txt").write_text(system,encoding="utf-8")
    pool={n["id"]:note_receipts(n["memory"]) for n in notes}
    acquired={}
    trace=[]
    event=dict(session_id=session_id,contract_version=CONTRACT_VERSION,status="unfinished",
        value=None,source_read_bytes=0,source_scan_seconds=0.0,query_calls=0,calculate_calls=0,
        quality_check_calls=0,recover_calls=0,archive_read_payload_bytes=0,save_calls=0,tool_errors=0,actual_invocations=0,
        observation_payload_bytes=0,trace=trace)
    for turn in range(max_actions):
        payload=dict(contract_version=CONTRACT_VERSION,current_source_id=source_id,task=task,
            retrieved_notes=notes,tool_trace=trace,remaining_actions=max_actions-turn,
            terminal_action_required=True,terminal_actions=["submit","abstain"],
            action_schema=ACTION_SCHEMA,
            archive_catalog=tools.archive.catalog() if tools.archive else [],
            allowed_actions=["query","recover","calculate","quality_check","save","submit","abstain"])
        dump(out/f"t{turn}-input.json",payload)
        event["actual_invocations"]+=1
        event["observation_payload_bytes"]+=len(canonical(payload).encode())
        try:
            # A client cannot mutate already logged inputs or the runtime's trace.
            action=respond(system,json.loads(json.dumps(payload)))
            dump(out/f"t{turn}-response.json",action)
            if not isinstance(action,dict) or not isinstance(action.get("action"),str):
                raise ValueError("Expected a JSON action object")
        except Exception as error:
            event.update(status="interface_failure",error_type=type(error).__name__)
            break
        name=action["action"]
        try:
            if name=="submit":
                value=action.get("value")
                if type(value) is not int:
                    raise ValueError("Submission must be an integer")
                event.update(status="submitted",value=value,citations=action.get("citations",[]))
                dump(out/"delivery.json",action)
                break
            if name=="abstain":
                event["status"]="abstained"
                break
            if name in ("query","recover"):
                if name=="query":
                    event["query_calls"]+=1
                    receipt,cost=tools.query(source_id,task,action.get("scope","full"))
                else:
                    event["recover_calls"]+=1
                    if tools.archive is None:raise ValueError("No archive configured")
                    receipt,size=tools.archive.get(action.get("archive_id"))
                    cost=dict(source_read_bytes=0,scan_seconds=0.0,archive_read_payload_bytes=size,backend_cache_hit=False)
                    event["archive_read_payload_bytes"]+=size
                ident=f"observation:{session_id}:{turn}"
                acquired[ident]=receipt
                pool[ident]=[receipt]
                all_receipts=[r for collection in pool.values() for r in collection]
                # An acquired full observation must not be overridden by a corrupt note.
                value=calculate([receipt],task,source_id)
                if value is None:value=calculate(all_receipts,task,source_id)
                result=dict(receipt_id=ident,receipt=receipt,value=value,
                    evidence=list(pool),task_binding="host_current_task",**cost)
                event["source_read_bytes"]+=cost["source_read_bytes"]
                event["source_scan_seconds"]+=cost["scan_seconds"]
            elif name=="calculate":
                event["calculate_calls"]+=1
                ids=action.get("evidence",[])
                if not isinstance(ids,list) or any(not isinstance(i,str) or i not in pool for i in ids):
                    raise ValueError("Unknown evidence IDs")
                result=dict(value=calculate([r for i in ids for r in pool[i]],task,source_id),
                    evidence=ids,task_binding="host_current_task",source_access=False,
                    parser_scope="complete JSON receipt literals only")
            elif name=="quality_check":
                event["quality_check_calls"]+=1
                if task["kind"]!="quality":
                    raise ValueError("quality_check applies only to quality requests")
                result=quality_check(**{k:action[k] for k in ("selected_correct","selected_total","threshold_numerator","threshold_denominator")})
            elif name=="save":
                event["save_calls"]+=1
                ident=action.get("receipt_id")
                if ident not in acquired or save is None:
                    raise ValueError("Save requires an acquired receipt and declared writer")
                result=dict(saved=save(acquired[ident]),receipt_id=ident)
            else:
                raise ValueError("Unknown action")
        except (ValueError,TypeError,KeyError) as error:
            result=dict(error=str(error),error_type=type(error).__name__)
            event["tool_errors"]+=1
        except Exception as error:
            event.update(status="tool_failure",error_type=type(error).__name__)
            break
        step=dict(action=action,result=result)
        trace.append(step)
        # Explicit generated record, including last-slot outputs with no next input.
        dump(out/f"t{turn}-generated.json",step)
    seen=[]
    for turn in range(event["actual_invocations"]):
        p=json.loads((out/f"t{turn}-input.json").read_bytes())
        seen.append(len(p["tool_trace"]))
    delivered=max(seen,default=0)
    event["generated_results"]=len(trace)
    event["generated_not_delivered"]=len(trace)-delivered
    dump(out/"event.json",event)
    return event
