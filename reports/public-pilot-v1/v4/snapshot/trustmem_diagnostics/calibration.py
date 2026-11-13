"""Authored sensitivity controls; these measure the instrument, not LLM prevalence."""
from .metrics import Ratio, evaluate_opportunity


def run_calibration():
    base = dict(context=[1, 0], source_version='v2', issued_fee=13, reference_fee=13)
    exact = dict(context=[1, 0], source_version='v2', unit_fee=13)
    cases = [
        ('clean_exact_reuse', dict(quote=exact), 'correct', True),
        ('wrong_despite_exact_evidence', dict(quote=exact, issued_fee=15), 'incorrect_given_exact_quote', True),
        ('defer_despite_exact_evidence', dict(quote=exact, issued_fee=None), 'deferred_given_exact_quote', True),
        ('correct_unquoted_is_not_an_error', dict(quote=None), 'wrong', False),
        ('wrong_unquoted', dict(quote=None, issued_fee=15), 'unquoted_wrong', True),
        ('scope_mismatch', dict(quote={**exact, 'context':[0, 1]}), 'exact_quote_present', False),
        ('stale_version', dict(quote={**exact, 'source_version':'v1'}), 'stale_quote_present', True),
        ('declared_wrong_binding', dict(quote=exact, declared_quote_context=[0, 1]), 'explicit_binding_mismatch', True),
        ('unknown_binding_is_not_inferred', dict(quote=exact), 'explicit_binding_mismatch', None),
        ('readback_old_revision', dict(expected_memory_revision=2, observed_memory_revision=1), 'memory_revision_mismatch', True),
        ('retrieval_is_not_causal_use', dict(quote=exact), 'causal_memory_effect', None),
        ('unsupported_is_not_business_failure', dict(execution_status='unsupported'), 'wrong', None),
    ]
    rows=[]
    for name, change, key, expected in cases:
        observed=evaluate_opportunity({**base, **change})[key]
        rows.append(dict(control=name, metric=key, expected=expected, observed=observed, passed=observed==expected))
    zero=Ratio(0,0,'eligible_opportunity').as_dict()
    rows.append(dict(control='zero_denominator', metric='value', expected=None, observed=zero['value'], passed=zero['value'] is None and zero['status']=='no_eligible_opportunity'))
    return dict(kind='ENGINEERING_SENSITIVITY_CONTROLS_NOT_MODEL_FINDINGS', controls=rows,
                passed=sum(r['passed'] for r in rows), total=len(rows), model_calls=0)


if __name__=='__main__':
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Choose a new calibration output; previous records are preserved.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result=run_calibration()
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],total=result['total'],kind=result['kind'])))
