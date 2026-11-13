"""Ordinary arithmetic only: no source, note, cache or reference access."""
from fractions import Fraction


def quality_check(*, selected_correct, selected_total, threshold_numerator, threshold_denominator):
    values = (selected_correct, selected_total, threshold_numerator, threshold_denominator)
    if any(type(value) is not int for value in values):
        raise ValueError("Calculator inputs must be integers, not booleans or strings")
    if not 0 <= selected_correct <= selected_total:
        raise ValueError("Expected 0 <= selected_correct <= selected_total")
    if threshold_denominator <= 0 or not 0 <= threshold_numerator <= threshold_denominator:
        raise ValueError("Expected a rational threshold in [0,1] with positive denominator")
    return dict(value=int(selected_total > 0 and selected_correct * threshold_denominator >= selected_total * threshold_numerator),
        ratio=str(Fraction(selected_correct, selected_total)) if selected_total else None,
        threshold=str(Fraction(threshold_numerator, threshold_denominator)),
        source_access=False, input_binding="unverified_model_supplied_numbers")
