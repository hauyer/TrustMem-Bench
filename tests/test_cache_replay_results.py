"""Check the published fixed-action replay, not an autonomous model effect."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/"reports/tool-cache-replay-v1"


class CacheReplayResultTests(unittest.TestCase):
    def test_actions_costs_and_declared_scope_match_the_frozen_plan(self):
        plan = json.loads((REPORT/"plan.json").read_text(encoding="utf-8"))
        summary = json.loads((REPORT/"summary.json").read_text(encoding="utf-8"))
        original = json.loads((ROOT/"reports/model-native-v1/result.json").read_text(encoding="utf-8"))
        arms = {}
        for arm in ("off","on"):
            result = json.loads((REPORT/arm/"result.json").read_text(encoding="utf-8"))
            arms[arm] = result
            self.assertEqual(json.loads((REPORT/arm/"bootstrap.stdout").read_text()),plan["bootstrap"])
            self.assertEqual([[step["action"] for step in e["trace"]] for e in result["events"]],plan["tasks"])
            self.assertEqual([e["submitted_value"] for e in result["events"]],[e["submitted_value"] for e in original["events"]])
            self.assertEqual(result["supported_correct"],8)
            self.assertEqual(result["tool_errors"],9)
            self.assertEqual(result["source_read_bytes_after_history"],sum(e["source_read_bytes"] for e in result["events"]))
            self.assertEqual(result["memory_written_payload_bytes"],0)
            freeze = json.loads((REPORT/arm/"freeze.json").read_text(encoding="utf-8"))
            for name,expected in freeze["code"].items():
                self.assertEqual(hashlib.sha256((REPORT/"code_snapshot"/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(arms["off"]["source_read_bytes_after_history"],original["source_read_bytes_after_history"])
        self.assertEqual(arms["on"]["tool_cache_hits"],4)
        self.assertEqual(arms["on"]["tool_cache_misses"],2)
        self.assertGreater(arms["on"]["events"][4]["source_read_bytes"],0)
        self.assertEqual(arms["on"]["events"][7]["source_read_bytes"],0)
        objects = json.loads((REPORT/"cache-objects.json").read_text())
        self.assertEqual(len(objects),2)
        self.assertEqual(sum(o["payload_bytes"] for o in objects),arms["on"]["tool_cache_written_payload_bytes"])
        self.assertEqual(summary["new_model_api_calls"],0)
        self.assertEqual(summary["source_read_bytes_saved_after_history"],arms["off"]["source_read_bytes_after_history"]-arms["on"]["source_read_bytes_after_history"])


if __name__ == "__main__":
    unittest.main()
