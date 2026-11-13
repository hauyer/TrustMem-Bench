import unittest
from trustmem_diagnostics.support import assess, generated_not_delivered, host_certificate


TASK = dict(kind="quality", a="correct", cutoff=80, numerator=9, denominator=10)
HISTORY = dict(kind="margins", source_id="A", left={"correct":95,"incorrect":5},
               right={"50":20,"90":80}, total=100)


class SupportTests(unittest.TestCase):
    def test_initial_sufficiency_without_tools(self):
        self.assertEqual(assess(task=TASK,source_id="A",receipts=[HISTORY])["supported_value"],1)

    def test_wrong_source_equal_numeric_not_support(self):
        result=assess(task=TASK,source_id="B",receipts=[HISTORY])
        self.assertEqual(result["status"],"not_certified")
        self.assertEqual(result["stale_receipts_present"],1)

    def test_sufficient_and_stale_coexist(self):
        result=assess(task=TASK,source_id="A",receipts=[HISTORY,dict(HISTORY,source_id="B")])
        self.assertEqual(result["status"],"sufficient")
        self.assertEqual(result["stale_receipts_present"],1)

    def test_unbound_arithmetic_not_a_certificate(self):
        self.assertEqual(assess(task=TASK,source_id="A",certificates=[dict(value=1)])["status"],"not_certified")

    def test_task_binding_required(self):
        cert=host_certificate(dict(value=1),dict(TASK,numerator=99,denominator=100),"A")
        self.assertEqual(assess(task=TASK,source_id="A",certificates=[cert])["status"],"not_certified")

    def test_last_result_not_delivered(self):
        steps=[dict(action=dict(action="calculate"),result=dict(value=1))]
        self.assertEqual(generated_not_delivered(steps,[[]]),steps)
        self.assertEqual(generated_not_delivered(steps,[[],steps]),[])

    def test_text_unknown_and_conflicting_certificates(self):
        self.assertEqual(assess(task=TASK,source_id="A",unassessed_text=True)["status"],"unknown")
        certs=[host_certificate(dict(value=v),TASK,"A") for v in (0,1)]
        self.assertEqual(assess(task=TASK,source_id="A",certificates=certs)["status"],"conflicting")

    def test_bad_trace_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            generated_not_delivered([dict(result=1)],[[dict(result=2)]])


if __name__ == "__main__":
    unittest.main()
