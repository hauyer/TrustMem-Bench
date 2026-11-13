"""Read-only adapter for SAP1 logs, with explicit scorer/actor separation."""
import csv
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .metrics import Ratio,evaluate_opportunity


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def diagnose(original,continuation,output):
    original=Path(original);continuation=Path(continuation);output=Path(output)
    assert not output.exists(),'Preserve earlier diagnostics; use a new version directory'
    output.mkdir(parents=True)
    logs=[json.loads(s) for p in [original/'api/model_calls.jsonl',continuation/'api/model_calls.jsonl'] for s in p.read_text(encoding='utf-8').splitlines()]
    calls={r['call_id']:r for r in logs};rows=[];sessions=[]
    for stream in read(continuation/'results.json'):
        dbpath=(continuation/'streams'/stream['id']/'state.sqlite').resolve()
        with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)) as db:
            actual_invoices={r[0]:r[3] for r in db.execute('SELECT * FROM invoices') if r[0].startswith('order-')}
        truth={r['order_id']:r['reference_fee'] for r in stream['private_scoring']}
        for step in stream['rounds']:
            call_id=stream['id']+f"-s{step['round']}-decide"
            payload=json.loads(calls[call_id]['request']['messages'][1]['content'])
            before={tuple(e['context']):e for e in payload['history'] if e['kind']=='reference_quote' and e['source_version']==payload['source_version']}
            current=payload['new_reference_quote'];cache={**before}
            if current is not None:cache[tuple(current['context'])]=current
            planned=payload['planning_recommendation']
            candidates=[i for i,o in enumerate(payload['orders']) if tuple(o['context']) not in before and planned['fees'][i] is not None and not planned['verify'][i]]
            sessions.append({'stream':stream['id'],'round':step['round'],'new_query':current is not None,
                'query_repeated_exact_cached_context':current is not None and tuple(current['context']) in before,
                'planned_unquoted_commit_indices':candidates,
                'query_misses_all_planned_unquoted_commits':bool(candidates) and current is not None and all(payload['orders'][i]['context']!=current['context'] for i in candidates),
                'writeback_readback_matches':step['memory_readback_matches'],
                'procedural_note_delivered':bool(payload['procedural_memory'])})
            # Deferred orders still need independent post-submission truth. Reconstruct
            # the provider's registered authored rule here, never in the actor payload.
            for i,order in enumerate(payload['orders']):
                a,b,c,d,e=order['context'];reference=(10+3*a+2*b if stream['family']==0 else 8+2*a+4*b)
                if stream['exception']:reference+=(11 if c and d else 0) if stream['family']==0 else (9 if d and e else 0)
                if order['order_id'] in truth:assert truth[order['order_id']]==reference
                record={'stream':stream['id'],'family':stream['family'],'world':int(stream['exception']),'arm':stream['arm'],
                    'round':step['round'],'order_id':order['order_id'],'context':order['context'],
                    'source_version':payload['source_version'],'reference_fee':reference,
                    'issued_fee':actual_invoices.get(order['order_id']),'quote':cache.get(tuple(order['context'])),
                    'planned_fee':planned['fees'][i],'recommended_verify':planned['verify'][i],
                    'confidence':planned['confidence'][i],'declared_quote_context':None}
                rows.append({**record,**evaluate_opportunity(record)})
    n=len(rows);known=sum(r['exact_quote_present'] for r in rows);unknown=n-known
    metrics={
        'correct_completion':Ratio(sum(r['correct'] for r in rows),n,'planned_order').as_dict(),
        'wrong_submission':Ratio(sum(r['wrong'] for r in rows),n,'planned_order').as_dict(),
        'deferral':Ratio(sum(r['deferred'] for r in rows),n,'planned_order').as_dict(),
        'correct_given_exact_quote':Ratio(sum(r['correct'] and r['exact_quote_present'] for r in rows),known,'exact_quote_order').as_dict(),
        'wrong_given_no_exact_quote':Ratio(sum(r['unquoted_wrong'] for r in rows),unknown,'no_exact_quote_order').as_dict(),
        'correct_given_no_exact_quote':Ratio(sum(r['unquoted_correct'] for r in rows),unknown,'no_exact_quote_order').as_dict(),
        'deferred_given_no_exact_quote':Ratio(sum(r['unquoted_deferred'] for r in rows),unknown,'no_exact_quote_order').as_dict(),
        'fresh_read_after_write_matches':Ratio(sum(s['writeback_readback_matches'] for s in sessions),len(sessions),'session').as_dict(),
        'redundant_exact_quote':Ratio(sum(s['query_repeated_exact_cached_context'] for s in sessions),sum(s['new_query'] for s in sessions),'new_quote').as_dict(),
        'causal_memory_writeback_benefit':Ratio(None,None,'matched_intervention','unobservable_without_fixed_note_or_equal_feedback_control').as_dict(),
        'semantic_source_attribution':Ratio(None,None,'memory_object','unobservable_native_citations_not_recorded').as_dict(),
    }
    report={'kind':'READ_ONLY_PIPELINE_DIAGNOSTICS','metrics':metrics,'planned_orders':n,'sessions':len(sessions),
        'authored_families':2,'independent_orders':False,
        'query_allocation_candidate_sessions':sum(s['query_misses_all_planned_unquoted_commits'] for s in sessions),
        'incorrect_given_exact_quote':sum(r['incorrect_given_exact_quote'] for r in rows),
        'scope':'Exact context coverage is a measurement, not a universal proof requirement or causal source attribution.',
        'model_calls':0,'usd':0,'adapter':'sap_readonly_trace_v1'}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'opportunities.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'sessions.json').write_text(json.dumps(sessions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['stream','arm','round','order_id','exact_quote_present','planned_fee','recommended_verify','confidence','issued_fee','reference_fee','correct','wrong','deferred']
    with (output/'opportunities.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    return report
