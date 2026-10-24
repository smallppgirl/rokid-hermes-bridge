"""
视觉意图判断
============
判断一句话是不是要眼镜拍照（take_photo）。

只看关键词会误判：「看看美股」「分析一下财报」也含「看看」「分析」，
却是普通问题。所以：
- 明确说眼前/画面的（这是什么、前面是什么、上面写的、拍一下、识别…）→ 拍照
- 「看看 / 看一下」加上眼前的位置（前面、周围、旁边…）→ 拍照，
  如「看看前面那辆车」「看一下周围有什么」；但「前面」指刚才的对话时
  （看看前面说的、前面的消息）不算
- 只有「看看 / 看一下」这类动词时，去掉它和这个、帮我、一下等虚词后，
  剩下的为空或只是要看的东西（牌子、字、菜单…）才拍照；
  剩下别的话题（美股、新闻…）就当普通问题
"""

import re

SCENE_PATTERNS = [
    "这是什么", "这是啥", "这个是什么", "这个是啥", "那是什么", "那是啥",
    "这是哪", "前面是什么", "前面是啥", "眼前", "上面写", "写的什么", "写的是什么",
    "什么牌子", "拍一下", "拍照", "拍张", "拍个照", "识别", "认一下", "帮我认",
    "前面有什么", "周围有什么", "周围是什么", "旁边有什么", "旁边是什么",
]

# 眼前的位置：和「看看」一起出现就是看现场
PLACE = re.compile(r"前面|前方|眼前|周围|四周|旁边|左边|右边|对面|这边|那边")

# 「前面」指刚才的对话，不是眼前
EARLIER = re.compile(r"前面(你|我|我们)?(说|讲|聊|提|问|回答|写)|前面的(消息|对话|内容|回答|问题|记录|聊天)")

LOOK = re.compile(r"看看|看一下|看一眼|看下|瞧瞧|瞅瞅")

FILLER = re.compile(
    r"[\s，。！？、,.!?~…]|帮我|帮忙|请|你|给我|这个|那个|这里|那里|这儿|那儿|这边|那边|"
    r"前面|这|那|一下|吧|呢|啊|呀|嘛|了|的"
)

# 只剩这些也算看眼前的东西
VISUAL_THINGS = re.compile(r"(东西|牌子|招牌|路牌|标签|字|菜单|商品|植物|花|图|画面)+")


def is_vision_request(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if EARLIER.search(t):
        return False
    if any(p in t for p in SCENE_PATTERNS):
        return True
    if not LOOK.search(t):
        return False
    if PLACE.search(t):
        return True
    rest = FILLER.sub("", LOOK.sub("", t))
    return rest == "" or VISUAL_THINGS.fullmatch(rest) is not None
