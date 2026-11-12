"""Bonus: retry có giới hạn, Retry-After, pagination, lọc nhiễu và injection với BonusTools (không gọi LLM API)."""
import email.utils
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
from agent import run_agent
from bonus.tools import BonusTools


def call(call_id, name, args):
    raw = json.dumps(args)
    return {'message': {'role': 'assistant', 'content': None,
                        'tool_calls': [{'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': raw}}]},
            'calls': [{'id': call_id, 'name': name, 'arguments': raw}], 'finish': 'tool_calls', 'usage': {}}


def final(text='Đã kiểm tra'):
    return {'message': {'role': 'assistant', 'content': text}, 'calls': [], 'finish': 'stop', 'usage': {}}


class Scripted:
    def __init__(self, responses):
        self.responses, self.histories = iter(responses), []

    def complete(self, messages, schemas):
        self.histories.append(list(messages))
        return next(self.responses)


def sent(provider, i):
    return json.loads(provider.histories[i][-1]['content'])


class FixedRetryTools(BonusTools):
    """Vercel luôn trả 429 với Retry-After cho trước (giả lập header thật)."""
    def __init__(self, retry_after):
        super().__init__()
        self.retry_after, self.executed = retry_after, 0

    def execute(self, name, args):
        self.executed += 1
        return {'ok': False, 'error': 'RATE_LIMITED', 'http_status': 429, 'retry_after': self.retry_after, 'retriable': True}


class BonusAgentTests(unittest.TestCase):
    def test_prompt_keeps_bonus_prompt_and_adds_rules(self):
        p = Scripted([final()])
        run_agent('x', p, BonusTools())
        system = p.histories[0][0]['content']
        self.assertTrue(system.startswith(BonusTools.system_prompt))
        self.assertIn('RATE_LIMITED', system)
        self.assertIn('next_offset', system)

    def test_persistent_429_stops_after_three_executions(self):
        tools = BonusTools(scenario='rate_limit_always')
        p = Scripted([call(str(i), 'get_vercel_status', {}) for i in range(4)] + [final()])
        result = run_agent('x', p, tools, max_steps=8)
        executed = [t for t in result['trace'] if t['event'] == 'tool']
        blocked = [t for t in result['trace'] if t['event'] == 'tool_blocked']
        self.assertEqual(len(executed), 3)
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 3)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(sent(p, 4)['error'], 'RETRY_BUDGET_EXCEEDED')
        self.assertIn('Đã hết lượt thử', ' '.join(sent(p, 3)['_agent_notes']))
        self.assertEqual(result['status'], 'completed')

    def test_429_once_then_success_resets_budget(self):
        tools = BonusTools(scenario='rate_limit_once')
        p = Scripted([call('a', 'get_vercel_status', {}), call('b', 'get_vercel_status', {}), final()])
        result = run_agent('x', p, tools, max_steps=5)
        self.assertIn('không phải outage', ' '.join(sent(p, 1)['_agent_notes']))
        self.assertEqual(sent(p, 2)['provider'], 'vercel')
        self.assertEqual(result['status'], 'completed')

    def test_retry_after_is_waited_within_budget(self):
        waits = []
        with patch.object(agent, '_sleep', waits.append):
            tools = FixedRetryTools(retry_after='2')
            p = Scripted([call('a', 'get_vercel_status', {}), call('b', 'get_vercel_status', {}), final()])
            run_agent('x', p, tools, max_steps=5)
        self.assertEqual(len(waits), 1)
        self.assertAlmostEqual(waits[0], 2, delta=0.5)
        self.assertEqual(tools.executed, 2)

    def test_retry_after_too_long_is_not_called(self):
        future = email.utils.formatdate(time.time() + 120, usegmt=True)  # Retry-After dạng HTTP date
        with patch.object(agent, '_sleep', lambda s: self.fail('không được chờ quá budget')):
            tools = FixedRetryTools(retry_after=future)
            p = Scripted([call('a', 'get_vercel_status', {}), call('b', 'get_vercel_status', {}), final()])
            result = run_agent('x', p, tools, max_steps=5)
        self.assertEqual(tools.executed, 1)
        self.assertEqual(sent(p, 2)['error'], 'RETRY_AFTER_TOO_LONG')
        self.assertEqual(result['trace'][-3]['event'], 'tool_blocked')

    def test_format_error_gets_fix_hint(self):
        tools = BonusTools(scenario='format_once')
        args = {'provider': 'npm', 'incident_id': 'cc0t2r4403sy', 'offset': 0}
        p = Scripted([call('a', 'get_incident_details', args), call('b', 'get_incident_details', args), final('x')])
        run_agent('x', p, tools, max_steps=5)
        self.assertIn('integer', ' '.join(sent(p, 1)['_agent_notes']))
        self.assertTrue(sent(p, 2)['ok'])

    def test_pagination_note_points_to_next_offset(self):
        tools = BonusTools()
        args = {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'offset': 0, 'limit': 2}
        out = tools.execute('get_incident_details', args)
        self.assertIsNotNone(out['next_offset'])
        notes = ' '.join(agent._annotate('get_incident_details', args, out))
        self.assertIn(f'offset={out["next_offset"]}', notes)

    def test_noise_is_compacted_for_model_but_kept_in_trace(self):
        tools = BonusTools(scenario='noisy')
        p = Scripted([call('a', 'get_vercel_status', {'component': 'Builds'}), final()])
        result = run_agent('x', p, tools)
        payload = sent(p, 1)
        self.assertEqual(payload['distractors']['_omitted_by_agent'], 160)
        self.assertTrue(payload['incidents'])  # bằng chứng vẫn giữ nguyên
        self.assertEqual(len(next(t for t in result['trace'] if t['event'] == 'tool')['result']['distractors']), 160)

    def test_injection_in_bonus_status_is_flagged(self):
        tools = BonusTools(scenario='injection')
        p = Scripted([call('a', 'get_npm_status', {}), final()])
        run_agent('x', p, tools)
        self.assertIn('external_notice', ' '.join(sent(p, 1)['_agent_notes']))

    def test_bonus_status_partial_list_and_source(self):
        out = BonusTools().execute('get_github_status', {})
        notes = ' '.join(agent._annotate('get_github_status', {}, out))
        self.assertIn('https://www.githubstatus.com', notes)
        if out['match_count'] > out['returned']:
            self.assertIn(f'{out["returned"]}/{out["match_count"]}', notes)


if __name__ == '__main__':
    unittest.main()
