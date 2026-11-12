import copy
import json
import unittest
import trustmem

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(trustmem.CATALOG.read_text(encoding="utf-8"))

    def test_catalog_counts_and_scope(self):
        result = trustmem.validate(self.data)
        self.assertEqual((result["records"], result["source_families"], result["archive_groups"]), (31, 5, 8))
        self.assertIsNone(result["independent_trajectory_count"])

    def test_rejects_nested_scoring_fields(self):
        data = copy.deepcopy(self.data)
        data["tasks"][0]["request"]["leak"] = {"expected": 1}
        with self.assertRaises(ValueError):
            trustmem.validate(data)

    def test_rejects_duplicate_id(self):
        data = copy.deepcopy(self.data)
        data["tasks"].append(copy.deepcopy(data["tasks"][0]))
        with self.assertRaises(ValueError):
            trustmem.validate(data)

if __name__ == "__main__":
    unittest.main()
