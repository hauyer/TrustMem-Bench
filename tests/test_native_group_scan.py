import gzip
from pathlib import Path
import tempfile
import unittest

from trustmem_runtime.data import scan


class NativeGroupScanTests(unittest.TestCase):
    def test_contiguous_scan_finishes_all_requested_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pageviews.gz"
            with gzip.open(path, "wb") as archive:
                archive.write(b"a One 3 0\na Two 5 0\nb One 7 0\nc Help:One 11 0\nc Two 13 0\nd One 17 0\n")
            source = {"path": path, "format": "wikimedia", "group_contiguous": True}
            requested, _ = scan(source, groups=("a", "c"))
            self.assertEqual(requested, {"a": {"no-colon": 8}, "c": {"colon": 11, "no-colon": 13}})
            missing, _ = scan(source, groups=("c", "missing"))
            self.assertEqual(missing, {"c": {"colon": 11, "no-colon": 13}})
            single, _ = scan(source, "b")
            self.assertEqual(single, {"b": {"no-colon": 7}})


if __name__ == "__main__":
    unittest.main()
