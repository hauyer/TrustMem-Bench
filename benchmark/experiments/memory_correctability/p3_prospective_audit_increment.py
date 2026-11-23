"""Stage-gated offline audit of scoped historical receipts."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns
from unittest.mock import patch

import p3_prospective_workflows as domain
from p3_prospective_diagnosis import predict, from_sets

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = ROOT / "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1"
MODES = ("ordered", "low_cost")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, sort_keys=True, ensure_ascii=False, indent=2)
        f.write("\n")


def driver_for(name, sources):
    binding = read(sources / "rescopebench/cases" / name / "formal-binding.json")
    module, cls = binding["driver_factory"].split(":")
    return getattr(importlib.import_module(module), cls)()


def close(world):
    if hasattr(world, "close"):
        world.close()


class StopWork(Exception):
    pass


class Episode:
    def __init__(self, driver, world, name, memory, focal=None, prior=None, adjustment=None):
        self.driver, self.world = driver, world
        self.name, self.memory = name, memory
        self.focal, self.prior = focal, prior
        self.adjustment = adjustment
        self.log, self.gates = [], []
        self.witnesses = {}
        self.profiles = {}
        self.target = None
        self.checked = set()
        self.same_value = None
        self.focal_different = False
        self.rejected_focal = False
        self.balance = self.initial = world._remaining if name == "backup_recovery" else world.remaining

    @staticmethod
    def content(reply):
        return reply.get("content", reply)

    @classmethod
    def nonaccounting(cls, reply):
        return {k:v for k,v in cls.content(reply).items() if k not in {"budget","receipt_index"}}

    @classmethod
    def success(cls, reply):
        return cls.content(reply).get("status") == "success"

    @classmethod
    def data(cls, reply):
        return cls.content(reply)["data"]

    @classmethod
    def error(cls, reply):
        body = cls.content(reply)
        return body.get("error_code") or body.get("code") or body.get("message", "rejected")

    def require(self, amount, label):
        if self.balance < amount:
            self.gates.append(dict(needed=amount, remaining=self.balance, call_index=len(self.log)+1,
                                   label=label, after_reject=any(
                                       not row["success"] for row in self.log if row["target"] == self.target)))
            raise StopWork("unfunded_" + label)

    def tool(self, name, args, receipt_key=None):
        call_idx = len(self.log) + 1
        before = self.balance
        credit = 0
        if self.adjustment and self.adjustment["index"] == call_idx:
            assert self.adjustment["tool"] == name and self.adjustment["arguments"] == args
            credit = self.adjustment["amount"]
            if self.name=="railway_ticketing":
                old_finish=self.world._finish
                def finish(tool, arguments, actor, result, price, before_hash):
                    return old_finish(tool, arguments, actor, result, price-credit, before_hash)
                with patch.object(self.world,"_finish",side_effect=finish):
                    return self.record(self.driver.call(self.world,name,args),name,args,receipt_key,
                                       call_idx,before,credit)
            old_cost = self.world._cost
            def cost(*pos, **kwargs):
                price = old_cost(*pos, **kwargs)
                if pos and pos[0] == name and isinstance(price, int) and price >= credit:
                    return price - credit
                return price
            with patch.object(self.world, "_cost", side_effect=cost):
                reply = self.driver.call(self.world, name, args)
        else:
            reply = self.driver.call(self.world, name, args)
        return self.record(reply,name,args,receipt_key,call_idx,before,credit)

    def record(self, reply, name, args, receipt_key, call_idx, before, credit):
        accounting = reply.get("budget", self.content(reply).get("budget"))
        if accounting is None:
            new = self.world._remaining if self.name == "backup_recovery" else self.world.remaining
            charged = before-new
        else:
            charged, new = accounting["charged"], accounting["remaining"]
        assert before - charged == new, (self.name, name, before, charged, new)
        self.balance = new
        row = dict(index=call_idx, target=self.target, tool=name, arguments=args, result=reply,
                   charged=charged, balance_before=before, remaining=new, success=self.success(reply),
                   receipt_key=receipt_key, applied_credit=credit)
        self.log.append(row)
        return reply

    def read(self, name, args, receipt_key=None):
        reply = self.tool(name, args, receipt_key)
        if not self.success(reply):
            error = self.error(reply)
            if ("BUDGET" in error.upper() or "ALLOWANCE" in error.upper() or "QUOTA" in error.upper()):
                self.gates.append(dict(needed=self.balance+1, remaining=self.balance, call_index=len(self.log),
                                       label=name, after_reject=any(not r["success"] for r in self.log[:-1]
                                                                    if r["target"] == self.target),
                                       lower_bound_only=True))
                raise StopWork("unfunded_" + name)
            raise StopWork(error)
        return self.data(reply)

    def remember(self, tool, key, args, projection):
        aux = self.memory["aux"]
        if key not in aux:
            aux[key] = projection(self.read(tool, args))
        return aux[key]

    def receipt(self, key, args, projection):
        saved = self.memory["receipts"]
        if key not in saved:
            if key in self.checked:
                raise StopWork("already_refreshed")
            self.checked.add(key)
            payload = projection(self.read(domain.DOMAINS[self.name][3], args, key))
            saved[key] = payload
            self.witnesses[key] = self.log[-1]["index"]
            if key == self.focal and self.same_value is None and self.prior is not None:
                if payload == self.prior and self.log[-1]["charged"] > 0:
                    self.same_value = self.log[-1]["index"]
                elif payload != self.prior:
                    self.focal_different = True
        return saved[key]

    def reject(self, key):
        if key == self.focal:
            self.rejected_focal = True
        self.memory["receipts"].pop(key, None)


def run_episode(driver, world, name, task, memory, mode, focal=None, prior=None, adjustment=None,
                order=None, grade=True):
    targets = domain.goals(name, task)
    id_key, grade_key, grade_id, _ = domain.DOMAINS[name]
    start = driver.begin(world, task)
    run = Episode(driver, world, name, memory, focal, prior, adjustment)
    dispatch = []
    pending = list(enumerate(targets))
    by_order = {t:i for i,t in enumerate(order or ())}
    focal_order = [t[id_key] for t in targets if domain.known_key(name,t,memory) == focal and focal is not None]
    while pending:
        queue = []
        for pos, t in pending:
            key = domain.known_key(name,t,memory)
            normal = domain.floor(name,t,memory)
            if key == focal and prior is not None and key not in memory["receipts"]:
                memory["receipts"][key] = prior
                with_receipt = domain.floor(name,t,memory)
                del memory["receipts"][key]
            else:
                with_receipt = normal
            queue.append(dict(position=pos,target=t[id_key],floor=normal,with_receipt_floor=with_receipt,
                              receipt_covered=key == focal and focal is not None))
        chosen = min(queue, key=lambda q: (
            by_order[q["target"]] if order is not None else q["floor"] if mode=="low_cost" else q["position"],
            q["position"]))
        pair = next(p for p in pending if p[0] == chosen["position"])
        pending.remove(pair)
        _, t = pair
        run.target = chosen["target"]
        run.gates = []
        begin, balance = len(run.log)+1, run.balance
        if chosen["floor"] > balance:
            stop = "unfunded_entry"
        else:
            try:
                stop = domain.execute(name,t,run)
            except StopWork as e:
                stop = str(e)
        dispatch.append(dict(queue=queue, target=run.target, floor=chosen["floor"], start=begin,
                             balance=balance, remaining=run.balance, stop=stop, gates=run.gates))
    if not grade:
        return run
    native = driver.grade(world, task)
    artifacts = native[grade_key]
    ids = {t[id_key] for t in targets}
    assert {row[grade_id] for row in artifacts} == ids, (name, [(a.get(grade_id), a.get("complete")) for a in artifacts], sorted(ids))
    complete = sorted(row[grade_id] for row in artifacts if row["complete"])
    count = native.get("completed_artifacts", native.get("complete_artifacts"))
    assert count is None or len(complete) == count, (name, complete, count)
    c = run.same_value
    return dict(workflow=name, day=task["position"], mode=mode, start=start, targets=sorted(ids),
                scope=sorted(focal_order), focal_key=focal, initial_budget=run.initial, remaining=run.balance,
                public_task=task["query"], public_pricing=task["business_budget"],
                calls=run.log, dispatch=dispatch, completed=complete, native_grade=native,
                published=None, post_publish_confirmed=None, blocked_optional_post_publish_price=None,
                same_value_read=c, same_value_cost=run.log[c-1]["charged"] if c else 0,
                focal_reread_different=run.focal_different, focal_prior_rejected=run.rejected_focal,
                focal_receipt_used_in_loss=c is not None or run.focal_different)


def cold(name, sources):
    d = driver_for(name, sources)
    world = d.create_world()
    memory = {"receipts":{}, "aux":{}, "keys":{}}
    window = min(e["before_task"] for e in d.lifecycle_schedule["events"])
    try:
        for task in d.tasks:
            if task["position"] >= window:
                break
            run_episode(d,world,name,task,memory,"ordered",grade=False)
    finally:
        close(world)
    before_window = set(memory["receipts"])
    relevant = sum(any(domain.known_key(name,t,memory) in before_window for t in domain.goals(name,task))
                   for task in d.tasks if task["position"] >= window)
    return dict(workflow=name, first_batch=window, history_length=len(d.tasks),
                cold_receipt_count=len(before_window), later_public_scope_match_batches=relevant)


def common_files(sources):
    return {p.relative_to(sources).as_posix(): sha(p) for p in sorted(sources.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def frozen(sources, out):
    admission = read(out / "ADMISSION_AUDIT.json")
    return dict(paid_model_calls=0, api_usd=0, modes=list(MODES),
                selected=admission["selected"], admission_sha256=sha(out/"ADMISSION_AUDIT.json"),
                code={p.name:sha(p) for p in sorted(HERE.glob("p3_prospective*.py"))},
                protocol=sha(HERE/"P3_PROSPECTIVE_AUDIT_INCREMENT_PROTOCOL.md"),
                sources=common_files(sources))


def replay(driver, name, task, snapshot, memory, mode, *args, **kw):
    begin = perf_counter_ns()
    world = driver.create_world()
    try:
        world.restore(deepcopy(snapshot))
        result = run_episode(driver,world,name,task,deepcopy(memory),mode,*args,**kw)
    finally:
        close(world)
    return result, (perf_counter_ns()-begin)/1_000_000


def make_openings(out, sources, item):
    sys.path.insert(0,str(sources.resolve()))
    snapshots = out/"CHECKPOINTS"
    snapshots.mkdir(exist_ok=True)
    openings = []
    name=item["workflow"]
    driver = driver_for(name,sources)
    world = driver.create_world()
    mem = {"receipts":{}, "aux":{}, "keys":{}}
    try:
        for task in driver.tasks:
            day = task["position"]
            if day >= item["first_batch"]:
                targets = domain.goals(name,task)
                keys = [domain.known_key(name,t,mem) for t in targets]
                focal = next((k for k in keys if k in mem["receipts"]),None)
                sham = next((k for k in sorted(mem["receipts"]) if k not in keys),None)
                opening = dict(workflow=name,day=day,focal=focal,sham=sham)
                if focal is not None:
                    checkpoint = snapshots/f"{name}-T{day:02}.json"
                    write(checkpoint,dict(state=world.snapshot(),memory=mem))
                    opening["checkpoint_sha256"] = sha(checkpoint)
                openings.append(opening)
            # The unscored continuation supplies the next day's opening.
            if day < len(driver.tasks):
                run_episode(driver,world,name,task,mem,"ordered",grade=False)
    finally:
        close(world)
    print("Wrote openings", name, flush=True)
    return openings


def observe_block(out, sources, openings):
    sys.path.insert(0,str(sources.resolve()))
    results=[]
    name=openings[0]["workflow"]
    driver=driver_for(name,sources)
    for opening in openings:
        day,focal=opening["day"],opening["focal"]
        if focal is None:
            results.extend({**opening, "mode":mode, "status":"ineligible_batch"} for mode in MODES)
            continue
        path=out/"CHECKPOINTS"/f"{name}-T{day:02}.json"
        assert sha(path)==opening["checkpoint_sha256"]
        initial=read(path)
        absent=initial["memory"]
        prior=absent["receipts"].pop(focal)
        for mode in MODES:
            log, _=replay(driver,name,driver.tasks[day-1],initial["state"],absent,mode,focal,prior)
            assert log["scope"],(name,day,focal)
            results.append({**opening,"status":"eligible",**log})
    return results


def blocks(items, size=3):
    return [items[i:i+size] for i in range(0,len(items),size)]


def blind(out):
    rows = []
    for row in read(out/"OBSERVE_LOSS.json"):
        if row["status"] != "eligible":
            continue
        answers = {"total": predict(row,"total")}
        if row["same_value_read"] is not None:
            answers["fee"] = predict(row,"fee")
        rows.append(dict(workflow=row["workflow"],day=row["day"],mode=row["mode"],answers=answers))
    write(out/"DIAGNOSIS_BEFORE_TRUTH.json",rows)


def same_world_outcome(first, second):
    return first["completed"] == second["completed"] and first["published"] == second["published"] and (
        first["post_publish_confirmed"] == second["post_publish_confirmed"])


def terminal(loss, other):
    return from_sets(loss["completed"], other["completed"], "native_outcomes",
                     loss["post_publish_confirmed"] != other["post_publish_confirmed"])


def compare(out,sources,observations):
    sys.path.insert(0,str(sources.resolve()))
    truth = []
    durations = []
    full = out/"REPLAY"
    full.mkdir(exist_ok=True)
    workflow=observations[0]["workflow"]
    driver = driver_for(workflow,sources)
    for observation in observations:
        item = {k:observation[k] for k in ("workflow","day","mode","status")}
        truth.append(item)
        if observation["status"] != "eligible":
            continue
        name,day,mode = item["workflow"],item["day"],item["mode"]
        checkpoint = out/"CHECKPOINTS"/f"{name}-T{day:02}.json"
        assert sha(checkpoint)==observation["checkpoint_sha256"]
        context = read(checkpoint)
        memory, snap = context["memory"], context["state"]
        task = driver.tasks[day-1]
        focal, sham = observation["focal_key"], observation["sham"]
        absent = deepcopy(memory)
        prior = absent["receipts"].pop(focal)
        storage = {}
        costs = {}
        elapsed = {}
        branch_valid = {}
        stem = f"{name}-T{day:02}-{mode}"

        def branch(label,mem,adjustment=None,order=None):
            outcome, ms = replay(driver,name,task,snap,mem,mode,focal,prior,adjustment,order)
            if adjustment:
                index=adjustment["index"]
                a,b=outcome["calls"],observation["calls"]
                valid=(len(a)>=index and a[:index-1]==b[:index-1] and
                       Episode.nonaccounting(a[index-1]["result"])==Episode.nonaccounting(b[index-1]["result"]) and
                       a[index-1]["charged"]==b[index-1]["charged"]-adjustment["amount"])
                branch_valid[label]=valid
            storage[label]=outcome
            elapsed[label]=ms
            costs[label]=dict(calls=len(outcome["calls"]), restorations=1)
            return outcome

        keep = branch("keep", memory)
        archive_mem = deepcopy(absent)
        archive_mem["receipts"][focal] = deepcopy(prior)
        archive = branch("archive",archive_mem)
        if sham is not None:
            unrelated=deepcopy(memory)
            del unrelated["receipts"][sham]
            sham_run=branch("sham",unrelated)
        else:
            sham_run=None
        observed_order=[x["target"] for x in observation["dispatch"]]
        retained_order=[x["target"] for x in archive["dispatch"]]
        total=terminal(observation, archive)
        interaction=None
        if mode=="low_cost" and observed_order!=retained_order and total["predicted_class"]!="no_terminal_change":
            a=branch("loss_order_keep_receipt",memory,order=observed_order)
            b=branch("keep_order_loss_receipt",absent,order=retained_order)
            def delta(first,second):
                x=set(first["completed"])
                y=set(second["completed"])
                return sorted(y-x),sorted(x-y)
            interaction=delta(observation,a)!=delta(b,archive)
        named=observation["same_value_read"]
        fee=None
        alternatives=[]
        if named is not None:
            c=observation["same_value_cost"]
            named_row=observation["calls"][named-1]
            def adjust(row):
                return dict(index=row["index"],tool=row["tool"],arguments=row["arguments"],amount=c)
            fee_run=branch("fee_only",absent,adjust(named_row))
            if branch_valid["fee_only"]:
                fee=terminal(observation,fee_run)
                if fee["predicted_class"]!="no_terminal_change":
                    for row in observation["calls"]:
                        if row["index"]==named or not row["success"] or row["charged"]<c:
                            continue
                        label=f"equal_charge_{row['index']}"
                        candidate=branch(label,absent,adjust(row))
                        if branch_valid[label] and same_world_outcome(candidate, fee_run):
                            alternatives.append(dict(index=row["index"], target=row["target"],
                                                     outside_scope=row["target"] not in observation["scope"]))
        first_difference=next((i for i,(a,b) in enumerate(zip(observed_order,retained_order)) if a!=b),None)
        identical_before_dispatch=False
        if first_difference is not None:
            pre_loss=observation["dispatch"][first_difference]["start"]-1
            pre_keep=archive["dispatch"][first_difference]["start"]-1
            loss_prefix=observation["calls"][:pre_loss]
            keep_prefix=archive["calls"][:pre_keep]
            comparable=lambda entries:[(r["target"],r["tool"],r["arguments"],
                                         Episode.nonaccounting(r["result"]),r["charged"]) for r in entries]
            identical_before_dispatch=(comparable(loss_prefix)==comparable(keep_prefix) and
                                       (named is None or pre_loss<named))
        item.update(scope=observation["scope"], total=total, fee=fee, costs=costs,
                    same_value_read=named, receipt_order_interaction=interaction,
                    equal_charge_alternatives=alternatives, dose_validated=branch_valid,
                    first_dispatch_difference=first_difference,
                    same_prefix_before_dispatch_and_prior_to_designated_charge=identical_before_dispatch,
                    loss_order=observed_order, archive_order=retained_order,
                    keep_archive_identical=keep==archive,
                    sham_trace_identical=sham_run==keep if sham_run else None,
                    sham_terminal_identical=same_world_outcome(sham_run,keep) if sham_run else None,
                    declined_confirmation_separately=observation["post_publish_confirmed"] is not None)
        durations.append(dict(workflow=name,day=day,mode=mode,arms_ms=elapsed))
        write(full/(stem+".json"), storage)
    print("Replayed",workflow,observations[0]["day"],observations[-1]["day"],flush=True)
    return truth,durations


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("cold","freeze","observe","blind","compare"))
    parser.add_argument("--out",type=Path,default=RUN)
    parser.add_argument("--sources",type=Path,default=RUN/"sources")
    parser.add_argument("--workflow",choices=tuple(domain.DOMAINS))
    args=parser.parse_args()
    sys.path.insert(0,str(args.sources.resolve()))
    if args.stage=="cold":
        print(json.dumps(cold(args.workflow,args.sources),ensure_ascii=False))
        return
    if args.stage=="freeze":
        write(args.out/"COHORT_FREEZE.json",frozen(args.sources,args.out))
        return
    spec=read(args.out/"COHORT_FREEZE.json")
    if args.stage=="blind":
        blind(args.out)
        return
    assert spec==frozen(args.sources,args.out), "Cohort, source or code changed after freeze"
    if args.stage=="compare":
        from p3_prospective_verify import lock
        lock(args.out,verify_only=True)
    with ProcessPoolExecutor(max_workers=8) as pool:
        if args.stage=="observe":
            start=[pool.submit(make_openings,args.out,args.sources,item) for item in spec["selected"]]
            # Begin loss observations as soon as each independent opening spine is ready.
            by_position={}
            from concurrent.futures import as_completed
            for future in as_completed(start):
                by_position[start.index(future)] = [
                    pool.submit(observe_block,args.out,args.sources,part)
                    for part in blocks(future.result())
                ]
            results=[f.result() for i in range(len(start)) for f in by_position[i]]
            write(args.out/"OBSERVE_LOSS.json",[row for subset in results for row in subset])
        else:
            observations=read(args.out/"OBSERVE_LOSS.json")
            chunks=[block for item in spec["selected"] for block in blocks(
                [row for row in observations if row["workflow"]==item["workflow"]],4)]
            runs=[pool.submit(compare,args.out,args.sources,chunk) for chunk in chunks]
            results=[f.result() for f in runs]
            write(args.out/"RESULT.json",dict(rows=[row for subset,_ in results for row in subset],
                                          paid_model_calls=0,api_usd=0))
            write(args.out/"REPLAY_TIMINGS.json",[row for _,subset in results for row in subset])


if __name__=="__main__":
    main()

