"""Arithmetic boundaries, empty selection and arbitrary-size integer support."""
from decimal import Decimal, localcontext
import unittest
from trustmem_runtime.calculator import quality_check


class CalculatorTests(unittest.TestCase):
    def test_against_independent_decimal_exhaustion(self):
        checks=0
        for total in range(13):
            for correct in range(total+1):
                for denominator in range(1,13):
                    for numerator in range(denominator+1):
                        with localcontext() as context:
                            context.prec=80
                            expected=int(total>0 and Decimal(correct)*denominator>=Decimal(total)*numerator)
                        result=quality_check(selected_correct=correct,selected_total=total,
                            threshold_numerator=numerator,threshold_denominator=denominator)
                        self.assertEqual(result["value"],expected)
                        self.assertFalse(result["source_access"])
                        checks+=1
        self.assertEqual(checks,8190)

    def test_current_threshold_and_bound_examples(self):
        def value(n,h,t,d):
            return quality_check(selected_correct=n,selected_total=h,threshold_numerator=t,threshold_denominator=d)["value"]
        self.assertEqual(value(76,80,99,100),0)
        self.assertEqual(value(80,80,99,100),1)
        self.assertEqual(value(75,80,9,10),1)
        self.assertEqual(value(0,0,0,1),0)
        self.assertEqual(value(0,5,0,1),1)
        self.assertEqual(value(99*10**100,100*10**100,99,100),1)
        self.assertEqual(value(99*10**100-1,100*10**100,99,100),0)

    def test_invalid_inputs_remain_tool_errors(self):
        base=dict(selected_correct=76,selected_total=80,threshold_numerator=99,threshold_denominator=100)
        for change in (dict(selected_correct=True),dict(selected_total="80"),dict(selected_total=-1),
                       dict(selected_correct=81),dict(threshold_denominator=0),dict(threshold_numerator=101)):
            with self.assertRaises(ValueError):
                quality_check(**{**base,**change})


if __name__ == "__main__":
    unittest.main()
