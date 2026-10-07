"""消息更新、切换会话和后台起草结果的版本隔离。"""
import os
import queue
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import main


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        main.chats.clear()
        main.state.update(area=None, hwnd=None, chat='甲')
        main.results = queue.Queue()
        main.draft_results = queue.Queue()
        main.update_result = queue.Queue()
        main.q = queue.Queue()
        self.overlay = Mock()
        self.overlay.current_chat.return_value = '甲'
        self.ui = patch.object(main, 'ov', self.overlay, create=True)
        self.ui.start()
        self.addCleanup(self.ui.stop)

    def test_analysis_starts_without_draft_key(self):
        with patch.object(main.settings, 'has_jev_key', return_value=True), \
                patch.object(main.settings, 'has_llm_key', side_effect=AssertionError('不应查询起草密钥')), \
                patch.object(main.threading, 'Thread') as thread:
            main.start_analyze('甲', [('her', '你好')])
        thread.return_value.start.assert_called_once()

    def test_new_messages_discard_inflight_draft(self):
        chat = main.chat_of('甲')
        chat.update(result={'answers': {'intent_thanks': {'score': 4}}, 'candidates': ['旧回复']}, draft_rev=0)
        main.invalidate_chat('甲')
        main.draft_results.put(('ok', {'candidates': ['过期结果']}, '甲', 0))
        main.tick()
        self.assertEqual(chat['result']['candidates'], [])
        self.assertTrue(chat['result']['stale'])
        self.overlay.show.assert_not_called()

    def test_other_chat_draft_is_cached_without_overwriting_screen(self):
        chat = main.chat_of('乙')
        chat.update(result={'answers': {}}, draft_rev=0)
        main.draft_results.put(('ok', {'answers': {}, 'candidates': ['乙的回复']}, '乙', 0))
        main.tick()
        self.assertEqual(chat['result']['candidates'], ['乙的回复'])
        self.overlay.show.assert_not_called()

    def test_draft_error_preserves_judgment(self):
        chat = main.chat_of('甲')
        chat.update(result={'answers': {'intent_thanks': {'score': 4}}}, draft_rev=0)
        main.draft_results.put(('err', '起草离线', '甲', 0))
        main.tick()
        self.assertEqual(chat['result']['answers']['intent_thanks']['score'], 4)
        self.assertEqual(chat['result']['draft_error'], '起草离线')
        self.overlay.set_status.assert_not_called()

    def test_target_change_invalidates_old_results(self):
        chat = main.chat_of('甲')
        chat['history'].append(('her', '你好', '小李'))
        chat['analysis_busy'] = True
        main.on_target_change('甲', '小李')
        self.assertEqual(chat['rev'], 1)
        main.results.put(('ok', {'answers': {'old': True}}, '甲', 0))
        with patch.object(main, 'start_analyze') as start:
            main.tick()
        start.assert_called_once()
        self.assertIsNone(chat['result'])

    def test_each_chat_keeps_its_own_pending_analysis(self):
        for title in ('甲', '乙'):
            chat = main.chat_of(title)
            chat.update(analysis_busy=True, pending=[('her', title)], rev=1)
            main.results.put(('ok', {'answers': {}}, title, 0))
        with patch.object(main, 'start_analyze') as start:
            main.tick()
        self.assertEqual([call.args[0] for call in start.call_args_list], ['甲', '乙'])

    def test_missing_draft_key_only_affects_draft_region(self):
        main.chat_of('甲')['result'] = {'answers': {'intent_thanks': {'score': 4}}}
        with patch.object(main.settings, 'has_llm_key', return_value=False), \
                patch.object(main.threading, 'Thread') as thread:
            main.on_generate('甲')
        thread.assert_not_called()
        self.overlay.set_draft_busy.assert_called_once()
        self.overlay.set_status.assert_not_called()

    def test_own_reply_stops_showing_obsolete_analysis_as_loading(self):
        chat = main.chat_of('甲')
        chat.update(analysis_busy=True, analysis_rev=0)
        self.assertTrue(main.result_for('甲')['analysis_busy'])
        main.invalidate_chat('甲')
        self.assertIsNone(main.result_for('甲'))

    def test_repeated_click_does_not_start_duplicate_draft(self):
        main.chat_of('甲')['result'] = {'answers': {}}
        with patch.object(main.settings, 'has_llm_key', return_value=True), \
                patch.object(main.threading, 'Thread') as thread:
            main.on_generate('甲')
            main.on_generate('甲')
        thread.return_value.start.assert_called_once()
