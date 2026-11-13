import json
from pathlib import Path
import tempfile
import unittest

from trustmem_diagnostics.adapters import DelegatedMemory, MarkdownMemory, SQLiteMemory, UnsupportedOperation
from trustmem_diagnostics.calibration import run_calibration
from trustmem_diagnostics.metrics import Ratio, dominates, evaluate_opportunity


class DiagnosticTests(unittest.TestCase):
    def test_sensitivity_controls(self):
        report=run_calibration()
        self.assertEqual(report['passed'], report['total'])
        self.assertEqual(report['total'], 13)

    def test_zero_and_unobservable_have_no_numeric_score(self):
        self.assertIsNone(Ratio(0,0,'request').as_dict()['value'])
        self.assertIsNone(Ratio(None,None,'request','unobservable').as_dict()['value'])
        self.assertEqual(Ratio(2,5,'request').as_dict()['value'], .4)

    def test_unquoted_correct_does_not_become_business_error(self):
        row=evaluate_opportunity(dict(context=[0], source_version='v1', quote=None, issued_fee=2, reference_fee=2))
        self.assertTrue(row['correct'])
        self.assertFalse(row['wrong'])
        self.assertTrue(row['unquoted_correct'])
        self.assertIsNone(row['explicit_binding_mismatch'])

    def test_quote_requires_scope_and_version(self):
        base=dict(context=[0], source_version='v2', issued_fee=2, reference_fee=2)
        for quote in [dict(context=[1],source_version='v2'),dict(context=[0],source_version='v1')]:
            self.assertFalse(evaluate_opportunity(dict(base,quote=quote))['exact_quote_present'])

    def test_pareto_requires_whole_batch_and_declared_costs(self):
        left=dict(correct=6,wrong=0,deferred=2,queries=1,logical_calls=1,usd=2)
        right=dict(correct=5,wrong=1,deferred=2,queries=1,logical_calls=1,usd=1)
        self.assertTrue(dominates(left,right))
        self.assertFalse(dominates(left,right,('queries','logical_calls','usd')))
        self.assertFalse(dominates(dict(left,correct=4,deferred=4),right))

    def test_verbatim_persistence_and_replacement_across_fresh_instances(self):
        text='范围: A\r\nB 的报价不可迁移。\nUnicode β and literal `code`.'
        for cls, name in [(SQLiteMemory,'state.sqlite'),(MarkdownMemory,'notes')]:
            with self.subTest(adapter=cls.__name__), tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/name
                first=cls(target).add(text)
                self.assertEqual(cls(target).get(first.id).text,text)
                self.assertEqual(cls(target).search('Unicode')[0].id,first.id)
                revised=cls(target).replace(first.id,'corrected scope',expected_revision=1)
                self.assertEqual((revised.revision,cls(target).get(first.id).text),(2,'corrected scope'))
                with self.assertRaises(ValueError):cls(target).replace(first.id,'stale writer',expected_revision=1)
                cls(target).delete(first.id)
                self.assertIsNone(cls(target).get(first.id))

    def test_markdown_detects_external_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MarkdownMemory(tmp);obj=store.add('original')
            (Path(tmp)/(obj.id+'.md')).write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):store.get(obj.id)

    def test_no_emulated_native_update(self):
        submitted=[]
        native=DelegatedMemory('test-fixture','version-pinned',{'add':lambda **kw:submitted.append(kw)})
        with self.assertRaises(UnsupportedOperation):native.invoke('replace',memory_id='id',text='revision')
        self.assertEqual(submitted,[])
        native.invoke('add',text='literal')
        self.assertEqual(submitted,[dict(text='literal')])


if __name__=='__main__':unittest.main()
