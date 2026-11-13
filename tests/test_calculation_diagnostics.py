import unittest
from trustmem_diagnostics.calculation import diagnose


class CalculationDiagnosticsTests(unittest.TestCase):
    def test_correct_tool_does_not_count_as_delivered_task(self):
        result=diagnose([dict(state="x",index=0,status="unfinished",calculator_calls=1,
            trace=[dict(action=dict(action="quality_check"),result=dict(value=0))])],{"0":0},planned=2)
        self.assertEqual(result["correct"],0)
        self.assertEqual(result["unfinished"],1)
        self.assertEqual(result["not_run"],1)
        self.assertEqual(result["correct_last_tool_value_without_submit"],1)

    def test_availability_nonuse_and_contradicted_calculator_stay_distinct(self):
        rows=[dict(state="a",index=0,status="submitted",value=1,calculator_calls=0,trace=[]),
              dict(state="b",index=0,status="submitted",value=1,calculator_calls=1,
                   trace=[dict(action=dict(action="quality_check"),result=dict(value=0))])]
        report=diagnose(rows,{0:0},planned=2)
        self.assertEqual(report["wrong"],2)
        self.assertEqual(report["states_selecting_calculator"],1)
        self.assertFalse(report["rows"][1]["submission_agrees_with_last_calculator"])
        self.assertIn("unassessed",report["rows"][1]["semantic_input_binding"])
