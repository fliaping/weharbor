import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

path = Path(__file__).resolve().parents[1] / 'root/scripts/workspace/visual_send.py'
spec = importlib.util.spec_from_file_location('visual_send', path)
visual_send = importlib.util.module_from_spec(spec)
sys.modules['visual_send'] = visual_send
spec.loader.exec_module(visual_send)


class SendCaptionTests(unittest.TestCase):
    def tsv(self, words):
        header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
        return header + ''.join('5\t1\t1\t1\t1\t%d\t0\t0\t10\t10\t%s\t%s\n' % (i, conf, word)
                                for i, (word, conf) in enumerate(words, 1))

    def test_exact_chinese_split_caption_and_english(self):
        self.assertTrue(visual_send.send_label(self.tsv([('发', 93.3), ('送', 93.2)])))
        self.assertTrue(visual_send.send_label(self.tsv([('Send', 96)])))

    def test_low_confidence_and_other_send_actions_are_rejected(self):
        for words in [[('发', 4.6), ('送', 81)], [('发送', 99), ('文件', 99)],
                      [('发送收藏', 99)], [('Send', 99), ('File', 99)], [('发送', 99), ('发送', 99)]]:
            with self.subTest(words=words):
                self.assertFalse(visual_send.send_label(self.tsv(words)))
        self.assertFalse(visual_send.send_label('invalid'))

    def test_moved_window_prevents_all_mouse_events(self):
        connection = Mock()
        xtest = SimpleNamespace(fake_input=Mock())
        modules = {'Xlib': SimpleNamespace(X=SimpleNamespace(), display=SimpleNamespace(Display=lambda: connection)),
                   'Xlib.ext': SimpleNamespace(xtest=xtest)}
        target = visual_send.VisualSend(100, 200, 50, 30, 42, (0, 0, 1200, 800))
        with patch.dict(sys.modules, modules), patch.object(visual_send, 'active_window', return_value=(42, (50, 0, 1200, 800))):
            with self.assertRaisesRegex(ValueError, 'moved or changed'):
                visual_send.click_send(target)
        xtest.fake_input.assert_not_called()
        connection.close.assert_called_once()
