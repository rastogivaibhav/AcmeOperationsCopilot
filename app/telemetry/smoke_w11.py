"""Live W11 observability validation against real Keycloak, FastAPI, PostgreSQL.

Writes disposable telemetry only; it does not send requests to a model or mutate
business records. Must be run inside a healthy local Docker Compose stack.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx2

from app.smoke import acquire

REPORT = Path('/code/evals/results/w11-live.json')
API = 'http://web:8000'


async def main():
    report = {'verified': False, 'checks': []}
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    def check(name, passed):
        report['checks'].append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise AssertionError(name)

    try:
        sales = acquire('sales-demo', 'SalesLocal2026!')
        support = acquire('support-demo', 'SupportLocal2026!')
        with_headers = lambda t: {'Authorization': 'Bearer ' + t}
        async with httpx2.AsyncClient(timeout=30) as client:
            result = await client.post(API+'/api/conversations', headers=with_headers(sales),
                                       json={'title': 'W11 telemetry verification'})
            check('sales_conversation_created', result.status_code == 201)
            conversation = uuid.UUID(result.json()['id'])
            identity = (await client.get(API+'/api/me', headers=with_headers(sales))).json()
            from app.telemetry import store
            receipt = store.create_run(conversation_id=conversation, owner_sub=identity['sub'],
                                       role='sales_user', blueprint_version='1.0',
                                       model_name='validation-only')
            run = uuid.UUID(receipt['run_id'])
            store.finish_run(run_id=run, owner_sub=identity['sub'], status='complete',
                             duration_ms=123, tool_events=[{'name': 'find_customer',
                             'status': 'ok', 'duration_ms': 42,
                             'evidence_refs': ['customer:acme-retail']}],
                             evidence_refs=['customer:acme-retail'])
            own = await client.get(API+'/api/activity/runs/'+str(run), headers=with_headers(sales))
            check('owner_can_read_own_trace', own.status_code == 200)
            check('tool_event_stored', own.json()['tool_events'][0]['tool_name'] == 'find_customer')
            foreign = await client.get(API+'/api/activity/runs/'+str(run), headers=with_headers(support))
            check('other_user_trace_hidden', foreign.status_code == 404)
            all_runs = await client.get(API+'/api/activity/runs', headers=with_headers(sales))
            check('owner_run_list', all_runs.status_code == 200 and
                  any(str(x['id']) == str(run) for x in all_runs.json()['items']))
            aggregate = await client.get(API+'/api/activity/summary', headers=with_headers(sales))
            check('owner_summary', aggregate.status_code == 200 and
                  aggregate.json()['total_runs'] >= 1)
        report['verified'] = True
    except Exception as exc:
        report['error_class'] = type(exc).__name__
        raise
    finally:
        REPORT.write_text(json.dumps(report, indent=2))
    print('W11_OBSERVABILITY_LIVE_PASS')


if __name__ == '__main__':
    asyncio.run(main())
