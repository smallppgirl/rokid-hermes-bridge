import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vision_intent import is_vision_request  # noqa: E402


class VisionIntentTest(unittest.TestCase):
    def test_scene_questions_take_a_photo(self):
        for q in ["看看", "看一下", "帮我看看", "帮我看一下这个", "看看前面", "看一眼这个吧",
                  "这是什么", "前面是什么？", "上面写的什么", "拍一下", "帮我识别一下",
                  "看看这个牌子", "帮我看看这个是什么", "这是什么牌子的车", "看下菜单",
                  "看看前面有什么", "看看前面那辆车", "看看前面的路", "看看前面的人在干嘛",
                  "帮我看看前面的牌子写的什么", "看一下周围有什么", "看看旁边那个人", "看一眼对面那栋楼",
                  "前面有什么", "旁边是什么", "看看这是什么花"]:
            self.assertTrue(is_vision_request(q), q)

    def test_topic_questions_go_to_hermes(self):
        for q in ["美股看看美股", "看看美股", "美股看一下", "帮我看看今天美股", "看一下今天的新闻",
                  "分析一下美股", "帮我分析这份财报", "这个牌子的手机好吗", "美股怎么样",
                  "查一下美股", "今天有哪些国际新闻。", "看下明天天气", "",
                  "看看前面说的", "看一下前面的消息", "帮我看看前面你回答的对不对",
                  "前面我们聊的是什么", "前面你说的是什么意思"]:
            self.assertFalse(is_vision_request(q), q)


if __name__ == "__main__":
    unittest.main()
