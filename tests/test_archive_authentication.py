from pathlib import Path
import tempfile
import unittest
from trustmem_runtime.archive import ObservationArchive
from trustmem_runtime.data import history
from trustmem_diagnostics.authentication import assess_authenticated


class ArchiveAuthenticationTests(unittest.TestCase):
    def test_future_absent_and_integrity_checked(self):
        with tempfile.TemporaryDirectory() as d:
            archive=ObservationArchive(Path(d)/"archive")
            self.assertEqual(archive.catalog(),[])
            receipt=dict(kind="full",source_id="A",table={"red":{"n":2}})
            ident=archive.put(receipt)
            restored,size=archive.get(ident)
            self.assertEqual(restored,receipt);self.assertGreater(size,0)
            with self.assertRaises(ValueError):archive.get("0"*64)
            (archive.path/(ident+".json")).write_bytes(b"bad")
            with self.assertRaises(ValueError):archive.get(ident)

    def test_valid_and_invalid_content_coexist_without_false_authentication(self):
        table={"correct":{"90":76,"50":19},"incorrect":{"90":4,"50":1}}
        full=dict(kind="full",source_id="A",table=table)
        wrong=dict(kind="full",source_id="A",table={"correct":{"90":80}})
        task=dict(kind="quality",a="correct",cutoff=80,numerator=99,denominator=100)
        result=assess_authenticated(receipts=[wrong,full],tables={"A":table},task=task,source_id="A")
        self.assertEqual(result["invalid_content"],1)
        self.assertEqual(result["conflicting_same_observation"],1)
        self.assertEqual(result["support"]["supported_value"],0)
        invalid=assess_authenticated(receipts=[wrong],tables={"A":table},task=task,source_id="A")
        self.assertEqual(invalid["support"]["status"],"not_certified")

    def test_source_id_and_lucky_value_do_not_authenticate(self):
        table={"red":{"n":2,"s":3}}
        margin=history(table,"cross","A");margin["left"]["red"]=999
        result=assess_authenticated(receipts=[margin],tables={"A":table},task=dict(kind="marginal",a="red"),source_id="A")
        self.assertEqual(result["invalid_content"],1)
        self.assertIsNone(result["support"]["supported_value"])

    def test_boolean_weights_are_not_integer_observations(self):
        receipt=dict(kind="full",source_id="A",table={"red":{"n":True}})
        result=assess_authenticated(receipts=[receipt],tables={"A":{"red":{"n":1}}},task=dict(kind="marginal",a="red"),source_id="A")
        self.assertEqual(result["invalid_content"],1)


if __name__=="__main__":unittest.main()
