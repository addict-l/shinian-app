"""Explicit whole-question opt-outs; no inference from narrated refusals."""
import re

_SKIP = re.compile(
    r'(?:跳过(?:这(?:个问题|题))?|暂时跳过|先跳过|略过|这题不适用|'
    r'(?:那|这)(?:个问题|道题|一题|题|段)(?:我)?(?:暂时|现在|先)?不想(?:回答|回忆|讲|说|聊)(?:了)?|'
    r'(?:我)?(?:暂时|现在|先)?不想(?:回答|讲|说|聊)(?:这(?:个问题|道题|一题|题|段))?(?:了)?|'
    r'(?:我)?(?:不愿意|不愿|不方便)(?:回答|讲|说)(?:这(?:个问题|题))?|'
    r'(?:这个问题|这题)(?:先)?(?:算了|不答了)|(?:我们)?(?:换|聊)(?:个|下一个)(?:话题|问题))'
    r'[。！!，,\s]*')


def skips_question(text):
    return bool(_SKIP.fullmatch(text.strip()))


SKIP_ACK = '那我们聊聊下一个话题吧。'
