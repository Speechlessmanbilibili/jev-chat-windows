"""验证采集、OCR、输入回填及异常响应的实际故障边界。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch

import numpy as np

from app import capture, fill, ocr, ocr_windows, settings
from core.draft import _parse_candidates
from core.jev_client import JevError
from core.llm import chat
from core.openai_decisions import normalize_response


class ReliabilityTests(unittest.TestCase):
    def test_capture_detects_title_change_when_messages_are_identical(self):
        area = (0, 60, 200, 140, np.array([255, 255, 255]), 0)
        with patch('windows_capture.WindowsCapture'), patch.object(capture, 'chat_area', return_value=area):
            stream = capture.Capture(1, settle=0)
            frame = np.full((200, 200, 4), 255, dtype=np.uint8)
            stream.on_frame_arrived(SimpleNamespace(frame_buffer=frame), None)
            self.assertIsNotNone(stream.settled())
            frame[20, 20, :3] = 0
            stream.on_frame_arrived(SimpleNamespace(frame_buffer=frame), None)
            self.assertIsNotNone(stream.settled())
            self.assertIsNone(stream.settled())
        self.assertIsNone(capture.chat_area(np.zeros((0, 0, 3), dtype=np.uint8)))

    def test_message_alignment_preserves_repetitions_and_sender_changes(self):
        reader = ocr.Reader.__new__(ocr.Reader)
        reader.seen = []
        first = [('her', '甲', '明天上午开会', 10), ('her', '甲', '收到', 30)]
        self.assertEqual(len(reader.new_lines(first)), 2)
        self.assertEqual(reader.new_lines(first + [('her', '甲', '收到', 50)]), [('her', '甲', '收到')])
        current = first + [('her', '甲', '收到', 50), ('her', '乙', '收到', 70),
                           ('her', '甲', '明天下午开会', 90)]
        self.assertEqual(reader.new_lines(current), [('her', '乙', '收到'), ('her', '甲', '明天下午开会')])
        self.assertEqual(reader.new_lines(current), [])
        self.assertEqual(reader.new_lines(first), [])
        self.assertEqual(reader.new_lines([('her', '甲', '新的话题', 10)]), [('her', '甲', '新的话题')])

    def test_ocr_ignores_outside_boxes_and_restores_trimmed_coordinates(self):
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        box = [[50, 50], [60, 50], [60, 60], [50, 60]]
        self.assertEqual(ocr.who_said(image, box), (None, None, 0))
        reader = ocr.Reader.__new__(ocr.Reader)
        reader.app = SimpleNamespace(trim_top=lambda img: 10, join='')
        reader.ocr = Mock(return_value=([([[1, 1], [20, 1], [20, 20], [1, 20]], '消息', 1)], None))
        reader.lh = None
        with patch.object(ocr, 'who_said', return_value=('her', np.array([0, 0, 0]), 15)):
            reader.read(image, np.array([255, 255, 255]))
        self.assertEqual(reader.last_boxes[0][:4], (1, 11, 20, 30))

    def test_windows_ocr_respects_size_limit_and_closes_bitmap(self):
        bitmap = Mock()
        factory = Mock(return_value=bitmap)
        reader = ocr_windows.WindowsOcr.__new__(ocr_windows.WindowsOcr)
        reader._engine = Mock()
        def recognize(coroutine):
            coroutine.close()
            return SimpleNamespace(lines=[])
        reader._loop = Mock(run_until_complete=recognize)
        with patch.object(ocr_windows, 'OcrEngine', SimpleNamespace(max_image_dimension=100)), \
                patch.object(ocr_windows, 'SoftwareBitmap', SimpleNamespace(create_copy_from_buffer=factory)), \
                patch.object(ocr_windows, 'CryptographicBuffer', SimpleNamespace(create_from_byte_array=lambda b: b)):
            self.assertEqual(reader(np.zeros((30, 80, 3), dtype=np.uint8)), ([], None))
        self.assertEqual(factory.call_args.args[2:4], (100, 37))
        bitmap.close.assert_called_once()

    def test_fill_stops_before_input_when_foreground_activation_fails(self):
        user32 = Mock()
        user32.IsWindow.return_value = True
        user32.GetForegroundWindow.return_value = 2
        user32.GetWindowThreadProcessId.return_value = 3
        with patch.object(fill, 'u32', user32), patch.object(fill, 'set_clipboard') as clipboard, \
                patch.object(capture, 'unminimize'), patch.object(fill.time, 'sleep'), \
                self.assertRaises(RuntimeError):
            fill.fill(1, (0, 0, 100, 100), '测试')
        clipboard.assert_not_called()
        user32.mouse_event.assert_not_called()
        user32.keybd_event.assert_not_called()

    def test_fill_uses_swapped_primary_mouse_button(self):
        user32 = Mock()
        user32.IsWindow.return_value = True
        user32.GetForegroundWindow.return_value = 1
        user32.GetSystemMetrics.return_value = 1
        def rectangle(hwnd, attribute, pointer, size):
            pointer._obj.left, pointer._obj.top = 0, 0
            pointer._obj.right, pointer._obj.bottom = 500, 600
            return 0
        with patch.object(fill, 'u32', user32), patch.object(fill, 'set_clipboard'), \
                patch.object(capture, 'unminimize'), patch.object(fill.time, 'sleep'), \
                patch.object(fill.ctypes.windll.dwmapi, 'DwmGetWindowAttribute', side_effect=rectangle):
            fill.fill(1, (0, 0, 400, 400), '测试')
        self.assertEqual([call.args[0] for call in user32.mouse_event.call_args_list], [0x8, 0x10])
        self.assertNotIn(0x0D, [call.args[0] for call in user32.keybd_event.call_args_list])

    def test_failed_settings_replace_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            original = json.dumps({'relationship': 'friends', 'style': '原文'}, ensure_ascii=False)
            config.write_text(original, encoding='utf-8')
            with patch.object(settings, '_CONFIG', str(config)), \
                    patch.object(settings, '_read_env', return_value=''), \
                    patch.object(settings.os, 'replace', side_effect=PermissionError), \
                    self.assertRaises(PermissionError):
                settings.save(style_text='新文案')
            self.assertEqual(config.read_text(encoding='utf-8'), original)
            self.assertEqual(list(Path(directory).iterdir()), [config])
        with patch('builtins.open', mock_open(read_data='{"thinking":"false","context":Infinity,"jev_model":{}}')):
            self.assertFalse(settings.thinking())
            self.assertEqual(settings.context(), 10)
            self.assertEqual(settings.jev_model(), 'gpt-6-luna')

    def test_invalid_candidates_and_truncated_output_are_rejected(self):
        for value in ('[null, 1, {}]', '{"reply":"内容"}', '["未完成', None):
            with self.subTest(value=value), self.assertRaises(JevError):
                _parse_candidates(value)
        self.assertEqual(_parse_candidates('[null, "有效回复", 12]'), ['有效回复'])
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='length', message=SimpleNamespace(content='["未完成', refusal=None))])
        with patch('openai.OpenAI', return_value=client), self.assertRaises(JevError):
            chat('openai', 'https://api.openai.com/v1', 'synthetic-key', 'gpt-6-luna', '测试', ['你好'])
        client.close.assert_called_once()

    def test_invalid_decisions_shapes_raise_readable_errors(self):
        questions = {'score': {'type': 'score', 'criteria': ['低', '高']}}
        for response in ([], {'answers': [{'name': []}]},
                         {'answers': [{'name': 'score', 'type': 'score', 'probabilities': [None]}]}):
            with self.subTest(response=response), self.assertRaises(JevError):
                normalize_response(response, questions)
