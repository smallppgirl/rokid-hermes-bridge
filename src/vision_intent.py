"""
视觉意图判断
============
判断一句话是不是要眼镜拍照（take_photo）。

只看关键词会误判：「看看美股」「分析一下财报」也含「看看」「分析」，
却是普通问题。所以：
- 明确说眼前/画面的（这是什么、前面是什么、上面写的、拍一下、识别…）→ 拍照
- 只有「看看 / 看一下」这类动词时，去掉它和这个、帮我、一下等虚词后，
  剩下的为空或只是要看的东西（牌子、字、菜单…）才拍照；
  剩下别的话题（美股、新闻…）就当普通问题
"""

import re

SCENE_PATTERNS = [
    "这是什么", "这是啥", "这个是什么", "这个是啥", "那是什么", "那是啥",
    "这是哪", "前面是什么", "前面是啥", "眼前", "上面写", "写的什么", "写的是什么",
    "什么牌子", "拍一下", "拍照", "拍张", "拍个照", "识别", "认一下", "帮我认",
]

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
    if any(p in t for p in SCENE_PATTERNS):
        return True
    if not LOOK.search(t):
        return False
    rest = FILLER.sub("", LOOK.sub("", t))
    return rest == "" or VISUAL_THINGS.fullmatch(rest) is not None
