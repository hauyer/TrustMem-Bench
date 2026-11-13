"""Reconcile published development summaries against retained full results."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublishedResultTests(unittest.TestCase):
    def test_native_mem0_pilot_preserves_first_responses_and_costs(self):
        root=ROOT/"reports/native-mem0-v1"
        manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
        for name,info in manifest["files"].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),info["sha256"])
        ledger=[json.loads(line) for line in (root/"models/api/model_calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(ledger),25)
        self.assertEqual(len({row["call_id"] for row in ledger}),25)
        self.assertTrue(all(row["status"]=="received" for row in ledger))
        usage=json.loads((root/"models/metrics.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(sum(row["estimated_peak_usd"] for row in ledger),usage["external_model_cost"])
        results=json.loads((root/"models/results.json").read_text(encoding="utf-8"))
        self.assertEqual([(r["arm"],r["correct"],r["wrong"]) for r in results],[("mem0",4,2),("verbatim",3,3)])
        for result in results:
            self.assertEqual(len(result["events"]),6)
            self.assertEqual(sum(e["correct"] for e in result["events"]),result["correct"])
            self.assertEqual(sum(e["source_read_bytes"] for e in result["events"]),308)

    def test_v03_exports_preserve_complete_streams_and_original_bytes(self):
        folder=ROOT/"reports/development-v0.3"
        manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        for name,info in manifest["files"].items():
            self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),info["sha256"])
        published=json.loads((ROOT/"reports/development-v0.3.json").read_text(encoding="utf-8"))
        self.assertEqual(published["new_external_model_calls"],0)
        for mode,summary in published["conditions"].items():
            runs=[]
            for path in (folder/mode).glob("c*/result.json"):
                result=json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(sum(event["correct"] for event in result["events"]),result["correct"])
                self.assertEqual(sum(event["source_read_bytes"] for event in result["events"]),result["source_read_bytes_after_history"])
                runs.append(result)
            self.assertEqual(len(runs),summary["run_count"])
            self.assertEqual(sum(r["sessions"] for r in runs),summary["planned_deliveries"])
            self.assertEqual(sum(r["supported_correct"] for r in runs),summary["supported_correct"])
            freeze=json.loads((folder/mode/"freeze.json").read_text(encoding="utf-8"))
            for name,identity in freeze["code"].items():
                self.assertEqual(hashlib.sha256((folder/mode/"code_snapshot"/name).read_bytes()).hexdigest(),identity)
            for name,identity in freeze["cases"].items():
                prefix,filename=name.split(":",1)
                self.assertEqual(hashlib.sha256((folder/mode/"case_snapshot"/f"{prefix}-{filename}").read_bytes()).hexdigest(),identity)

    def test_all_ordinary_results_match_their_original_bytes(self):
        report = json.loads((ROOT/"reports/development-v0.2.json").read_text(encoding="utf-8"))
        for section,folder in (("engineering_runs","engineering-v1"),("native_runs","native-v2")):
            actual = {json.loads(path.read_text(encoding="utf-8"))["case_id"]+"/"+json.loads(path.read_text(encoding="utf-8"))["policy"]:path for path in (ROOT/"reports"/folder).glob("c*/result.json")}
            for summary in report[section]:
                path = actual[summary["case_id"]+"/"+summary["policy"]]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),summary["result_sha256"])
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(sum(e["correct"] for e in raw["events"]),summary["correct"])
                self.assertEqual(sum(e["source_read_bytes"] for e in raw["events"]),summary["source_read_bytes_after_history"])
            freeze = json.loads((ROOT/"reports"/folder/"freeze.json").read_text(encoding="utf-8"))
            for name,expected in freeze["code"].items():
                self.assertEqual(hashlib.sha256((ROOT/"reports"/folder/"code_snapshot"/name).read_bytes()).hexdigest(),expected)

    def test_model_counts_and_costs_come_from_actual_ledgers(self):
        report = json.loads((ROOT/"reports/development-v0.2.json").read_text(encoding="utf-8"))
        calls, cost = 0,0
        for folder in ("model-pilot-v1","model-pilot-v2","model-native-v1"):
            path = ROOT/"reports"/folder
            summary = json.loads((path/"summary.json").read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in (path/"model_calls.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows),summary["attempted_model_calls"])
            subtotal = sum(row.get("estimated_peak_usd",row["reserve_usd"]) for row in rows)
            self.assertAlmostEqual(subtotal,summary["estimated_peak_usd"])
            raw = json.loads((path/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(sum(e["correct"] for e in raw["events"]),summary["correct"])
            self.assertEqual(len(raw["events"]),8)
            for row in rows:
                self.assertEqual(row["request"]["thinking"],{"type":"disabled"})
                self.assertEqual(row["response"]["choices"][0]["finish_reason"],"stop")
            calls += len(rows)
            cost += subtotal
        self.assertEqual(calls,report["external_api_calls"])
        self.assertAlmostEqual(cost,report["estimated_peak_usd"])


if __name__ == "__main__":
    unittest.main()
