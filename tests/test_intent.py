"""程度展示、分析/起草隔离和部分拒答的回归测试。"""
import unittest
from unittest.mock import patch

from core import engine
from core.intent import INTENT_QUESTIONS, percentage, ratings
from core.jev_client import JevError
from core.openai_decisions import normalize_response


class IntentTests(unittest.TestCase):
    def test_fractional_scores_and_invalid_values(self):
        for score, expected in ((0, 0), (1, 25), (2, 50), (3, 75), (4, 100),
                                (3.42, 86), (0.02, 1), (1.98, 50)):
            self.assertEqual(percentage(score), expected)
        for value in (None, True, '3', -0.1, 4.01, float('nan'), float('inf')):
            self.assertIsNone(percentage(value))

    def test_multiple_labels_stay_independent_and_missing_is_unknown(self):
        answers = {'intent_reminder': {'score': 3.8}, 'intent_thanks': {'score': 3.4},
                   'intent_refusal': {'score': 0}}
        values = ratings(answers, 'intent')
        self.assertEqual(values[:3], [('提醒', 95), ('感谢', 85), ('拒绝', 0)])
        self.assertGreater(sum(v for _, v in values if v is not None), 100)
        self.assertIsNone(values[-1][1])

    def test_analysis_never_invokes_drafting(self):
        with patch.object(engine, 'ask', return_value={'answers': {}}) as ask, \
                patch.object(engine, 'draft_candidates') as draft:
            result = engine.analyze([('her', '你好')], 'friends')
        ask.assert_called_once()
        draft.assert_not_called()
        self.assertNotIn('candidates', result)
        self.assertTrue(all(q['type'] == 'score' for q in ask.call_args.args[1].values()))

    def test_analysis_failure_does_not_generate_blind_replies(self):
        with patch.object(engine, 'ask', side_effect=JevError('离线')), \
                patch.object(engine, 'draft_candidates') as draft, self.assertRaises(JevError):
            engine.analyze([('her', '你好')], 'friends')
        draft.assert_not_called()

    def test_partial_refusal_is_visible_as_unknown(self):
        questions = {name: INTENT_QUESTIONS[name] for name in ('intent_thanks', 'tone_calm')}
        response = {'answers': [{'name': 'intent_thanks', 'type': 'score', 'score': 3.5,
                                 'confidence': 0.8, 'probabilities': []},
                                {'name': 'tone_calm', 'type': 'refusal'}]}
        result = normalize_response(response, questions)
        self.assertEqual(ratings(result['answers'], 'intent')[0], ('感谢', 88))
        self.assertTrue(all(value is None for _, value in ratings(result['answers'], 'tone')))

    def test_draft_failure_preserves_analysis(self):
        analysis = {'answers': {'intent_greeting': {'score': 4}}, 'reply_to': None}
        with patch.object(engine, 'draft_candidates', side_effect=JevError('起草离线')), \
                self.assertRaises(JevError):
            engine.generate_replies([('her', '你好')], 'friends', analysis)
        self.assertEqual(analysis['answers']['intent_greeting']['score'], 4)

    def test_group_quote_matches_selected_target(self):
        with patch.object(engine, 'ask', return_value={'answers': {}}):
            result = engine.analyze([('her', '请明天提交', '小李'), ('her', '你好', '小王')],
                                    'colleagues', reply_to='小李')
        self.assertEqual(result['analyzed_text'], '请明天提交')
        self.assertEqual(result['analyzed_sender'], '小李')

    def test_target_outside_context_fails_before_request(self):
        with patch.object(engine, 'ask') as ask, self.assertRaises(JevError):
            engine.analyze([('her', '请明天提交', '小李'), ('her', '你好', '小王')],
                           'colleagues', reply_to='小李', context=1)
        ask.assert_not_called()
