"""Offline-only provider mocks. These are not model experiment outputs."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"examples"))
from metered_deepseek import DeepSeekClient, ModelBudgetExhausted


class MeteringTests(unittest.TestCase):
    def test_insufficient_cap_prevents_network_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{"DEEPSEEK_API_KEY":"unit-only-key"}):
            client = DeepSeekClient(Path(directory),{},max_usd=1e-12,max_tokens=384)
            with patch("urllib.request.urlopen") as network:
                with self.assertRaises(ModelBudgetExhausted):
                    client.complete("Return JSON.",{},"unit")
                network.assert_not_called()

    def test_usage_and_peak_estimate_are_saved(self):
        fake = {"model":"deepseek-flash","choices":[{"finish_reason":"stop","message":{"content":"{\"action\":\"start\"}"}}],
            "usage":{"prompt_tokens":100,"prompt_cache_hit_tokens":20,"prompt_cache_miss_tokens":80,"completion_tokens":8}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{"DEEPSEEK_API_KEY":"unit-only-key"}):
            client = DeepSeekClient(Path(directory),{},max_usd=.01,max_tokens=384)
            with patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(fake).encode())):
                self.assertEqual(client.complete("Return JSON.",{},"unit"),{"action":"start"})
            entry = json.loads((Path(directory)/"model_calls.jsonl").read_text())
            self.assertAlmostEqual(entry["estimated_peak_usd"],0.00003372)
            self.assertNotIn("unit-only-key",(Path(directory)/"model_calls.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
