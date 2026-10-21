import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vision_intent import is_vision_request  # noqa: E402


class VisionIntentTest(unittest.TestCase):
    def test_scene_questions_take_a_photo(self):
        for q in ["看看", "看一下", "帮我看看", "帮我看一下这个", "看看前面", "看一眼这个吧",
                  "这是什么", "前面是什么？", "上面写的什么", "拍一下", "帮我识别一下",
                  "看看这个牌子", "帮我看看这个是什么", "这是什么牌子的车", "看下菜单"]:
            self.assertTrue(is_vision_request(q), q)

    def test_topic_questions_go_to_hermes(self):
        for q in ["美股看看美股", "看看美股", "美股看一下", "帮我看看今天美股", "看一下今天的新闻",
                  "分析一下美股", "帮我分析这份财报", "这个牌子的手机好吗", "美股怎么样",
                  "查一下美股", "今天有哪些国际新闻。", "看下明天天气", ""]:
            self.assertFalse(is_vision_request(q), q)


if __name__ == "__main__":
    unittest.main()
