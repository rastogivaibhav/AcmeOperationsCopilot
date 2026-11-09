"""W13 evaluator regression tests: never claim semantic or live certainty from fixtures."""
import json
from pathlib import Path

import pytest

from evals.w13_scoring import ordered_subsequence, score_agent_case, summarise, validate_cases
from evals.run_w13 import _report_markdown

ROOT = Path(__file__).resolve().parents[1]


def cases():
    return json.loads((ROOT / 'evals/w13_cases.json').read_text())['cases']


def base_result(**overrides):
    value = {'status': 'complete', 'answer': 'Acme Retail is an active account',
             'tool_events': [{'name': 'find_customer', 'status': 'ok'}],
             'evidence_refs': ['customers:ac000000-0000-4000-8000-000000000001'],
             'proposed_actions': []}
    value.update(overrides)
    return value


def test_exactly_ten_unique_realistic_cases():
    cs = cases()
    validate_cases(cs)
    assert {c['role'] for c in cs} == {'admin', 'sales_user', 'support_user'}
    assert {'rbac', 'grounding', 'skill', 'tool-minimality'} <= set(
        term for c in cs for term in c['category'].split(','))


def test_wrong_number_and_duplicate_ids_rejected():
    cs = cases()
    with pytest.raises(ValueError):
        validate_cases(cs[:9])
    cs[1]['id'] = cs[0]['id']
    with pytest.raises(ValueError):
        validate_cases(cs)


def test_ordered_subsequence_must_preserve_order():
    assert ordered_subsequence(['find_customer', 'list_open_issues'],
                               ['find_customer', 'get_issue_history', 'list_open_issues'])
    assert not ordered_subsequence(['find_customer', 'list_open_issues'],
                                   ['list_open_issues', 'find_customer'])


def test_profile_provenance_structural_pass():
    result = score_agent_case(cases()[0], base_result())
    assert result['passed'] is True
    assert result['checks']['evidence_links']


def test_missing_required_evidence_fails_even_if_response_fluent():
    result = score_agent_case(cases()[0], base_result(evidence_refs=[]))
    assert result['passed'] is False
    assert not result['checks']['evidence_links']


def test_hallucinated_uuid_fails():
    outcome = score_agent_case(cases()[0], base_result(
        answer='Acme Retail belongs to customer aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'))
    assert not outcome['checks']['evidence_links']


def test_tool_not_run_cannot_pass():
    outcome = score_agent_case(cases()[0], base_result(tool_events=[]))
    assert not outcome['checks']['tool_routing']


def test_sales_write_tool_always_rejected():
    outcome = score_agent_case(cases()[8], base_result(tool_events=[
        {'name': 'create_next_action', 'status': 'ok'}]))
    assert not outcome['checks']['forbidden_tools_absent']


def test_admin_requires_a_proposal_not_a_claim():
    admin_case = cases()[7]
    missing = score_agent_case(admin_case, base_result())
    assert not missing['checks']['proposal_boundary']
    actual = base_result(tool_events=[{'name': 'get_issue_history', 'status': 'ok'},
                                     {'name': 'request_next_action', 'status': 'approval_required'}],
                         evidence_refs=['issues:ab000000-0000-4000-8000-000000000001'],
                         proposed_actions=[{'kind': 'next_action'}],
                         answer='I propose contacting the customer; no action saved.')
    checked = score_agent_case(admin_case, actual)
    assert checked['checks']['proposal_boundary']
    assert checked['checks']['no_database_commit_claim']
    actual['answer'] = 'I have created the next action already.'
    assert not score_agent_case(admin_case, actual)['checks']['no_database_commit_claim']


def test_no_tool_case_rejects_extra_lookup():
    outcome = score_agent_case(cases()[9], base_result())
    assert not outcome['checks']['tool_minimality']
    outcome = score_agent_case(cases()[9], base_result(tool_events=[], evidence_refs=[]))
    assert outcome['passed']


def test_denied_customer_cannot_be_claimed_visible():
    scoped = cases()[4]
    denied = base_result(tool_events=[{'name': 'find_customer', 'status': 'not_found'}],
                         evidence_refs=[], answer='Cannot access the account.')
    assert score_agent_case(scoped, denied)['passed']
    denied['answer'] = 'Morgan Admin owns it.'
    assert not score_agent_case(scoped, denied)['checks']['answer_terms']


def test_runtime_report_never_auto_marks_not_run_as_pass():
    report = {'timestamp_utc': '2026-11-09T00:00:00Z', 'model': 'unavailable',
              'live_runtime_verified': False, 'cases': [], 'summary': {'passed': 0, 'case_count': 10},
              'blockers': ['ModuleNotFoundError']}
    content = _report_markdown(report)
    assert 'Live runtime verified:** False' in content
    assert '0 / 10' in content
    assert 'ModuleNotFoundError' in content


def test_summary_counts_failed_cases_without_missing_status_assumption():
    summary = summarise([{'passed': True, 'checks': {'tool_routing': True}},
                         {'passed': False, 'checks': {'tool_routing': False}}])
    assert summary['passed'] == 1 and summary['failed'] == 1
    assert summary['check_rates']['tool_routing'] == {'passed': 1, 'total': 2}
