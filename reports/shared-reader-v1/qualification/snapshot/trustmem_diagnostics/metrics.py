"""Metric primitives that keep opportunity, outcome and observability separate."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Ratio:
    numerator: int | None
    denominator: int | None
    unit: str
    status: str = 'measured'

    def as_dict(self):
        if self.status != 'measured':
            return {'numerator':self.numerator,'denominator':self.denominator,'value':None,
                    'unit':self.unit,'status':self.status}
        assert self.numerator is not None and self.denominator is not None
        assert 0<=self.numerator<=self.denominator
        return {'numerator':self.numerator,'denominator':self.denominator,
                'value':self.numerator/self.denominator if self.denominator else None,
                'unit':self.unit,'status':'measured' if self.denominator else 'no_eligible_opportunity'}


def evaluate_opportunity(row):
    """Ground truth belongs to a post-submission scorer, never the actor input."""
    status=row.get('execution_status','executed')
    if status!='executed':
        return {'execution_status':status,'correct':None,'wrong':None,'deferred':None,
                'exact_quote_present':None,'incorrect_given_exact_quote':None,
                'deferred_given_exact_quote':None,'not_evaluated_as_business_failure':True}
    issued=row['issued_fee'] is not None
    quote=row.get('quote')
    exact=bool(quote is not None and quote['context']==row['context'] and quote['source_version']==row['source_version'])
    return {
        'execution_status':status,'correct':issued and row['issued_fee']==row['reference_fee'],
        'wrong':issued and row['issued_fee']!=row['reference_fee'],'deferred':not issued,
        'exact_quote_present':exact,'incorrect_given_exact_quote':exact and issued and row['issued_fee']!=row['reference_fee'],
        'deferred_given_exact_quote':exact and not issued,
        # An unquoted correct prediction is not automatically an error or violation.
        'unquoted_correct':not exact and issued and row['issued_fee']==row['reference_fee'],
        'unquoted_wrong':not exact and issued and row['issued_fee']!=row['reference_fee'],
        'unquoted_deferred':not exact and not issued,
        'stale_quote_present':quote is not None and quote['source_version']!=row['source_version'],
        'explicit_binding_mismatch':None if row.get('declared_quote_context') is None else row['declared_quote_context']!=row['context'],
        'memory_revision_mismatch':None if row.get('expected_memory_revision') is None or row.get('observed_memory_revision') is None else row['expected_memory_revision']!=row['observed_memory_revision'],
        'causal_memory_effect':None,
    }


def dominates(left,right,cost_dimensions=('queries','logical_calls')):
    """Sample-level Pareto comparison under explicitly selected operating costs."""
    same_regime=all(left[k]<=right[k] for k in cost_dimensions)
    no_worse=left['correct']>=right['correct'] and left['wrong']<=right['wrong'] and left['deferred']<=right['deferred']
    strict=left['correct']>right['correct'] or left['wrong']<right['wrong'] or left['deferred']<right['deferred'] or any(left[k]<right[k] for k in cost_dimensions)
    return same_regime and no_worse and strict
