"""Meaningful source/decision/persistence boundaries for rational release gates."""
from collections import defaultdict
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
import unittest
from trustmem_runtime.evidence import calculate
from trustmem_runtime.fixtures import build
from trustmem_runtime.run import read_case, run
from trustmem_runtime.reporting import write_report


def gate(cutoff=80, numerator=9, denominator=10):
    return dict(kind="quality", a="correct", cutoff=cutoff, numerator=numerator, denominator=denominator)


class QualityTests(unittest.TestCase):
    def test_nonzero_uncertainty_can_still_determine_a_gate(self):
        margins = dict(kind="margins", source_id="x", total=100,
                       left={"correct":95,"incorrect":5}, right={"90":80,"50":20})
        self.assertEqual(calculate([margins],gate(),"x"),1)
        self.assertIsNone(calculate([margins],gate(numerator=99,denominator=100),"x"))
        self.assertIsNone(calculate([margins],dict(kind="joint",a="correct",b="90"),"x"))
        self.assertIsNone(calculate([margins],gate(),"new-source"))

    def test_certificates_hold_in_all_enumerated_same_margin_worlds(self):
        worlds = defaultdict(list)
        for a,b,c,d in product(range(3),repeat=4):
            worlds[(a+b,c+d,a+c,b+d)].append((a,b,c,d))
        for (correct,incorrect,low,high), rows in worlds.items():
            receipt = dict(kind="margins",source_id="x",total=correct+incorrect,
                left={"correct":correct,"incorrect":incorrect},right={"50":low,"90":high})
            for cutoff in (0,80,100):
                for num,den in ((0,1),(1,2),(9,10),(1,1)):
                    value = calculate([receipt],gate(cutoff,num,den),"x")
                    if value is not None:
                        for a,b,c,d in rows:
                            n,h = ((a+b,a+b+c+d) if cutoff==0 else (b,b+d) if cutoff==80 else (0,0))
                            self.assertEqual(value,int(h>0 and n*den>=h*num))

    def test_group_requires_current_population_and_full_is_self_sufficient(self):
        group = dict(kind="group",source_id="x",scope_a="correct",table={"correct":{"90":76,"50":19}})
        margins = dict(kind="margins",source_id="x",total=100,
            left={"correct":95,"incorrect":5},right={"90":80,"50":20})
        task = gate(numerator=99,denominator=100)
        self.assertIsNone(calculate([group],task,"x"))
        self.assertEqual(calculate([margins,group],task,"x"),0)
        self.assertIsNone(calculate([{**margins,"source_id":"old"},group],task,"x"))
        full = dict(kind="full",source_id="x",table={"correct":{"90":80,"50":15},"incorrect":{"90":0,"50":5}})
        self.assertEqual(calculate([full],task,"x"),1)
        self.assertEqual(calculate([full],gate(cutoff=100),"x"),0)

    def test_all_ordinary_policies_preserve_source_changes_and_cached_return(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = next(p for p in build(root/"cases") if Path(p).name=="quality.case.json")
            for index,policy in enumerate(("always_verify","lazy_group","lazy_full","eager_full")):
                result = run(case,root/f"c{index:02}-{policy}",policy)
                self.assertEqual(result["supported_correct"],8)
                self.assertEqual([e["submitted_value"] for e in result["events"]],[1,0,0,1,1,1,0,0])
                if policy != "always_verify":
                    self.assertEqual(result["events"][0]["source_read_bytes"],0)
                    self.assertEqual(result["events"][2]["source_read_bytes"],0)
                    self.assertGreater(result["events"][4]["source_read_bytes"],0)
                    self.assertEqual(result["events"][5]["source_read_bytes"],0)
                    self.assertEqual(result["events"][7]["source_read_bytes"],0)
            write_report(root)
            import csv
            with (root/"tasks.csv").open(encoding="utf-8",newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),32)
            self.assertIn("engineering-quality",(root/"SUMMARY.md").read_text())
            with self.assertRaises(FileExistsError):
                write_report(root)

    def test_shared_tool_cache_keeps_quality_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = next(p for p in build(root/"cases") if Path(p).name=="quality.case.json")
            result = run(case,root/"run","always_verify",tool_cache=True)
            self.assertEqual(result["supported_correct"],8)
            self.assertEqual(result["tool_cache_misses"],2)
            self.assertEqual(result["tool_cache_hits"],6)
            payload=json.loads((root/"run/bootstrap.observation.json").read_text())
            self.assertIn("Quality gates return integer 1",payload["protocol"])

    def test_wrong_gate_is_committed_without_hidden_host_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            case=Path(next(p for p in build(root/"cases") if Path(p).name=="quality.case.json"))
            manifest=json.loads(case.read_text())
            manifest["tasks"]=manifest["tasks"][:1]
            case.write_text(json.dumps(manifest))
            script=root/"wrong.py"
            script.write_text('import json,sys\no=json.loads(sys.stdin.readline())\nprint(json.dumps({"action":"start"} if o["phase"]=="bootstrap" else {"action":"submit","value":0,"evidence":["history"]}))\n')
            result=run(case,root/"run",agent_command=[sys.executable,str(script)])
            self.assertEqual(result["incorrect_submissions"],1)
            self.assertEqual(result["contradictory_submissions"],1)
            self.assertEqual(json.loads((root/"run/s00.delivery.json").read_text())["value"],0)

    def test_invalid_rational_threshold_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            case=Path(next(p for p in build(root/"cases") if Path(p).name=="quality.case.json"))
            manifest=json.loads(case.read_text())
            manifest["tasks"][0]["request"]["denominator"]=0
            case.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                read_case(case)

    def test_native_decimal_reader_and_independent_sql_reference(self):
        from trustmem_runtime.data import digest, history, scan
        from trustmem_runtime.grading import reference
        from trustmem_runtime.prepare_confidence import prepare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"predictions.arff"
            lines=["@RELATION smoke"]
            lines += [f"@ATTRIBUTE {name} NUMERIC" for name in ("repeat","fold","sample","row_id")]
            lines += [f"@ATTRIBUTE confidence.{i} NUMERIC" for i in range(1,8)]
            lines += ["@ATTRIBUTE prediction {1,2,3,4,5,6,7}","@ATTRIBUTE correct {1,2,3,4,5,6,7}","@DATA"]
            for i,(peak,truth) in enumerate((("0.8",1),("0.8",2),("0.6",1),("0.6",1))):
                lines.append(",".join(["0","0",str(i),str(i),peak,"0.2" if peak=="0.8" else "0.4",*(["0"]*5),"1",str(truth)]))
            path.write_text("\n".join(lines)+"\n")
            identity=digest(path)
            source=dict(format="openml-arff-confidence",path=str(path),sha256=identity)
            table,cost=scan(source)
            self.assertEqual(cost["source_read_bytes"],path.stat().st_size)
            old=history(table,"quality",identity)
            tasks=[gate(numerator=1,denominator=2),gate()]
            case=dict(sources={identity:source},tasks=[dict(source_id=identity,request=q) for q in tasks])
            self.assertEqual(reference(case),{0:1,1:0})
            self.assertEqual(calculate([old],tasks[0],identity),1)
            self.assertIsNone(calculate([old],tasks[1],identity))
            self.assertEqual(calculate([dict(kind="full",source_id=identity,table=table)],tasks[1],identity),0)
            with self.assertRaises(ValueError):
                prepare(path,root/"not-admitted")


if __name__ == "__main__":
    unittest.main()
