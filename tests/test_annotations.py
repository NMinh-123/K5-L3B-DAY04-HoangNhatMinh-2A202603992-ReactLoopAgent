"""Bài 4: tool result được chú thích (_agent_notes) để giảm khái quát quá mức, thiếu nguồn và bỏ sót injection."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import _annotate, _find_injections, run_agent
from scenarios import ScenarioTools
from status_tools import StatusTools
from test_lab import FakeProvider, final, tool_call


class AnnotationTests(unittest.TestCase):
    def test_partial_list_and_loose_matches_are_flagged(self):
        args = {'provider': 'github', 'component': 'Actions'}
        notes = ' '.join(_annotate('get_status', args, StatusTools().execute('get_status', args)))
        self.assertIn('5/23', notes)
        self.assertIn('smtdswd1h2w4', notes)
        self.assertIn('https://www.githubstatus.com', notes)

    def test_injection_detected_in_status_and_incident(self):
        status = ScenarioTools('status_injection').execute('get_status', {'provider': 'github', 'component': 'Actions'})
        self.assertIn('external_notice', _find_injections(status))
        incident = ScenarioTools('injection').execute('get_incident_details', {'provider': 'github', 'incident_id': 'xr3myzj7ms51'})
        self.assertTrue(any(p.startswith('updates[') for p in _find_injections(incident)))

    def test_no_false_injection_on_real_snapshot(self):
        tools = StatusTools()
        for provider in ('github', 'cloudflare'):
            self.assertEqual(_find_injections(tools.execute('get_status', {'provider': provider})), [])

    def test_updated_at_and_overall_scope_notes(self):
        tools = StatusTools()
        github = ' '.join(_annotate('get_status', {'provider': 'github'}, tools.execute('get_status', {'provider': 'github'})))
        self.assertIn('updated_at', github)
        self.assertNotIn('Trạng thái tổng quan', github)  # GitHub overall = none
        cloudflare = ' '.join(_annotate('get_status', {'provider': 'cloudflare'}, tools.execute('get_status', {'provider': 'cloudflare'})))
        self.assertIn('Trạng thái tổng quan', cloudflare)  # Cloudflare overall = major

    def test_errors_get_no_notes(self):
        self.assertEqual(_annotate('get_status', {}, {'ok': False, 'error': 'TimeoutError'}), [])

    def test_notes_sent_to_model_and_trace_keeps_original_result(self):
        fake = FakeProvider([tool_call('c1', 'get_status', '{"provider":"github","component":"Actions"}'), final()])
        result = run_agent('x', fake, StatusTools())
        sent = json.loads(fake.histories[1][-1]['content'])
        self.assertTrue(sent['_agent_notes'])
        event = next(t for t in result['trace'] if t['event'] == 'tool')
        self.assertNotIn('_agent_notes', event['result'])
        self.assertEqual(event['notes'], sent['_agent_notes'])


if __name__ == '__main__':
    unittest.main()
