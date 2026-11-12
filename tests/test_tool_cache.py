import tempfile
from pathlib import Path
import unittest
from trustmem_runtime.tool_cache import ToolCache
from trustmem_runtime.fixtures import build
from trustmem_runtime.run import run


class ToolCacheTests(unittest.TestCase):
    def test_cached_queries_keep_correctness_without_agent_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = build(root/"cases")[0]
            result = run(case,root/"run",policy="always_verify",tool_cache=True)
            self.assertEqual(result["supported_correct"],8)
            self.assertEqual(result["memory_written_payload_bytes"],0)
            self.assertGreater(result["tool_cache_written_payload_bytes"],0)
            self.assertEqual(result["tool_cache_hits"],6)
            self.assertEqual(result["tool_cache_misses"],2)
            self.assertGreater(result["events"][4]["source_read_bytes"],0)
            self.assertEqual(result["events"][7]["source_read_bytes"],0)

    def test_scope_and_source_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ToolCache(Path(directory)/"cache.sqlite")
            group = {"kind":"group","scope_a":"red","source_id":"old","table":{"red":{"x":2}}}
            cache.put(group)
            self.assertEqual(cache.get("old","group","red"),group)
            self.assertIsNone(cache.get("old","full","red"))
            self.assertIsNone(cache.get("old","group","blue"))
            self.assertIsNone(cache.get("new","group","red"))
            complete = {"kind":"full","source_id":"new","table":{"red":{"x":5},"blue":{"x":3}}}
            cache.put(complete)
            self.assertEqual(cache.get("new","group","blue"),complete)
            self.assertEqual(cache.get("new","full","red"),complete)
            self.assertEqual(cache.get("old","group","red"),group)


if __name__ == "__main__":
    unittest.main()
