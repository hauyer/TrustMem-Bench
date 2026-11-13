import gzip
import json
from pathlib import Path
import tempfile
import unittest
from trustmem_runtime.data import digest
from trustmem_runtime.prepare_public import prepare
from trustmem_runtime.run import read_case
from trustmem_runtime.grading import reference


class PublicSelectionTests(unittest.TestCase):
    def test_explicit_selection_keeps_actual_source_and_split(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec={}
            for label,groups in (("new-one",["PushEvent","PushEvent","IssuesEvent"]),("new-two",["IssuesEvent","PushEvent","IssuesEvent"])):
                p=root/f"{label}.gz"
                with gzip.open(p,"wt",encoding="utf-8") as stream:
                    for i,kind in enumerate(groups):
                        stream.write(json.dumps(dict(type=kind,repo=dict(name=("alice" if i%2 else "bob")+"/repo")))+"\n")
                spec[label]=("gharchive",digest(p),"https://example.invalid/"+label)
            prepare(root,root/"cases",source_spec=spec,history_pairs={"sample":("new-one","new-two")},split="selection-test")
            case=read_case(root/"cases/sample.case.json")
            self.assertEqual(case["split"],"selection-test")
            self.assertEqual({s["url"] for s in case["sources"].values()},{s[2] for s in spec.values()})
            self.assertEqual(len(reference(case)),8)
            self.assertEqual(case["sources"][case["initial_source"]]["sha256"],spec["new-one"][1])


if __name__=="__main__":unittest.main()
