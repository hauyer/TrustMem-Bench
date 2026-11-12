import json
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import product
from collections import defaultdict

from trustmem_runtime.evidence import calculate, range_value
from trustmem_runtime.fixtures import build
from trustmem_runtime.run import run


class RuntimeTests(unittest.TestCase):
    def test_small_table_enumeration_and_threshold_boundaries(self):
        worlds = defaultdict(list)
        for cells in product(range(3),repeat=4):
            signature = (cells[0]+cells[1],cells[2]+cells[3],cells[0]+cells[2],cells[1]+cells[3])
            worlds[signature].append(cells)
        for signature, group in worlds.items():
            a,b,c,d = signature
            receipt = {"kind":"margins","source_id":"x","left":{"r":a,"s":b},"right":{"10":c,"20":d},"total":a+b}
            for limit in (9,10,19,20):
                task = {"kind":"threshold","a":"r","limit":limit}
                value = calculate([receipt],task,"x")
                if value is not None:
                    for cells in group:
                        independent = cells[0]*int(10<=limit)+cells[1]*int(20<=limit)
                        self.assertEqual(value,independent)

    def test_signed_interval_enumeration(self):
        worlds = defaultdict(list)
        for vector in product((-1,0,1),repeat=4):
            worlds[(sum(vector[:3]),vector[2])].append(vector)
        for (prefix,tail), group in worlds.items():
            records = [{"a":"r","lo":1,"hi":3,"value":prefix},{"a":"r","lo":3,"hi":3,"value":tail}]
            for lo in range(1,5):
                for hi in range(lo,5):
                    value = range_value(records,{"a":"r","lo":lo,"hi":hi},[1,2,3,4])
                    if value is not None:
                        self.assertTrue(all(sum(v[lo-1:hi])==value for v in group))
    def test_same_marginals_do_not_certify_joint(self):
        receipt = {"kind":"margins","source_id":"x","left":{"a":5},"right":{"b":4},"total":10}
        query = {"kind":"joint","a":"a","b":"b"}
        self.assertIsNone(calculate([receipt],query,"x"))
        self.assertEqual(calculate([receipt],{**query,"b":"missing"},"x"),0)
        self.assertIsNone(calculate([receipt],{**query,"b":"missing"},"changed-source"))

    def test_interval_subtraction_and_unobserved_expansion(self):
        records = [{"a":"a","lo":1,"hi":3,"value":12},{"a":"a","lo":3,"hi":3,"value":5}]
        self.assertEqual(range_value(records,{"a":"a","lo":1,"hi":2},[1,2,3,4]),7)
        self.assertIsNone(range_value(records,{"a":"a","lo":1,"hi":4},[1,2,3,4]))

    def test_persisted_observation_survives_new_session_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = build(root/"cases")[0]
            result = run(case,root/"run")
            self.assertEqual(result["supported_correct"],8)
            self.assertEqual(result["events"][3]["source_read_bytes"],0)
            self.assertTrue(result["events"][3]["cited_saved_evidence"])
            self.assertGreater(result["events"][4]["source_read_bytes"],0)
            self.assertEqual(result["events"][5]["source_read_bytes"],0)
            self.assertEqual(result["events"][7]["source_read_bytes"],0)

    def test_lucky_numeric_answer_is_still_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = Path(build(root/"cases")[0])
            case = json.loads(case_path.read_text())
            case["tasks"] = [case["tasks"][2]]
            case_path.write_text(json.dumps(case))
            agent = root/"agent.py"
            agent.write_text('import json,sys\no=json.loads(sys.stdin.readline())\nprint(json.dumps({"action":"start"} if o["phase"]=="bootstrap" else {"action":"submit","value":3,"evidence":["history"]}))\n')
            result = run(case_path,root/"run",agent_command=[sys.executable,str(agent)])
            self.assertEqual(result["correct"],1)
            self.assertEqual(result["supported_correct"],0)
            self.assertEqual(result["unsupported_submissions"],1)
            for obs in (root/"run").glob("*.observation.json"):
                payload = json.loads(obs.read_text())
                self.assertNotIn("answers",payload)
                self.assertNotIn("scoring",payload)

    def test_missing_executable_keeps_entire_planned_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = build(root/"cases")[0]
            result = run(case,root/"run",agent_command=[str(root/"not-an-executable")])
            self.assertEqual(result["status"],"BOOTSTRAP_FAILURE")
            self.assertEqual(result["sessions"],8)
            self.assertEqual(len(result["events"]),8)
            self.assertEqual(result["agent_failures"],8)

    def test_invalid_actions_reach_step_limit_without_disappearing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = build(root/"cases")[0]
            agent = root/"agent.py"
            agent.write_text('import json,sys\no=json.loads(sys.stdin.readline())\nprint(json.dumps({"action":"start"} if o["phase"]=="bootstrap" else {"action":"unknown"}))\n')
            result = run(case,root/"run",agent_command=[sys.executable,str(agent)],steps=2)
            self.assertEqual(result["step_limits"],8)
            self.assertEqual(result["submitted"],0)

    def test_wrong_value_is_committed_and_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = Path(build(root/"cases")[0])
            case = json.loads(case_path.read_text())
            case["tasks"] = [case["tasks"][0]]
            case_path.write_text(json.dumps(case))
            agent = root/"agent.py"
            agent.write_text('import json,sys\no=json.loads(sys.stdin.readline())\nprint(json.dumps({"action":"start"} if o["phase"]=="bootstrap" else {"action":"submit","value":99,"evidence":["history"]}))\n')
            result = run(case_path,root/"run",agent_command=[sys.executable,str(agent)])
            self.assertEqual(result["submitted"],1)
            self.assertEqual(result["incorrect_submissions"],1)
            delivered = json.loads((root/"run/s00.delivery.json").read_text())
            self.assertEqual(delivered["value"],99)


if __name__ == "__main__":
    unittest.main()
