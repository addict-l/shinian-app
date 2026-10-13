"""Conservative span suggestions; no model calls, writes, or global replacements.

Only whole temporal expressions matching the previous time are replaceable.
Multiple dates, relative dates and repeated occurrences require explicit review.
Unrecognized natural language stays untouched and is disclosed to the editor.
"""
from collections import Counter
import hashlib
import json
import re
from app.schemas.time_linkage import TimePreview, TimeSuggestion
from app.schemas.story_information import InformationStatus

TEMPORAL = re.compile(r'(?<![0-9])(?:[12][0-9]{3}-[0-9]{2}-[0-9]{2}|[12][0-9]{3}年(?:[0-9]{1,2}月(?:[0-9]{1,2}[日号])?|(?:春|夏|秋|冬)(?:天|季)?|(?:年初|年底))?|去年|前年|今年|明年|次年|第二年|那年|那一年|当年|那时候|小时候|年轻时|[0-9一二三四五六七八九十]+年后)(?![0-9])')

def utf16(text):
    return len(text.encode('utf-16-le')) // 2

def key(value):
    # Treat two exact date spellings as equivalent, never broaden a full date to a year.
    value = value.strip()
    if re.fullmatch(r'[12][0-9]{3}', value):
        return value + '年'
    full = re.fullmatch(r'([12][0-9]{3})年([0-9]{1,2})月([0-9]{1,2})[日号]', value)
    if full:
        return f'{full[1]}-{int(full[2]):02d}-{int(full[3]):02d}'
    return value

def preview(body):
    old = body.old_time.value or ''
    new = body.new_time.value if body.new_time.status != InformationStatus.missing else None
    new = new.strip() if new else None
    fields = [('title', body.title), ('summary', body.summary)]
    matches = []
    for field, text in fields:
        # Include exact fuzzy wording even when it is not in the temporal recognizer.
        spans = {(m.start(), m.end()) for m in TEMPORAL.finditer(text)}
        if old and not old.isdigit():
            spans.update((m.start(), m.end()) for m in re.finditer(re.escape(old), text))
        # Longest containing expression wins, e.g. "十岁那年" over "那年".
        end = -1
        for a, b in sorted(spans, key=lambda span: (span[0], -span[1])):
            if a < end: continue
            matches.append((field, text, a, b))
            end = b
    distinct = {key(text[a:b]) for _, text, a, b in matches}
    total_counts = Counter(key(text[a:b]) for _, text, a, b in matches)
    counts = Counter((field, key(text[a:b])) for field, text, a, b in matches)
    suggestions = []
    same = (body.old_time.status, old) == (body.new_time.status, body.new_time.value or '')
    for field, text, a, b in matches[:100]:
        before = text[a:b]
        target = bool(old) and key(before) == key(old)
        # Larger expressions containing the old value (2006年6月 vs 2006年) are never truncated.
        after = new if target and not same else None
        if after == before: after = None
        relative = not re.match(r'[12][0-9]{3}', before)
        count = counts[(field, key(before))]
        ambiguous = relative or len(distinct) > 1 or count > 1 or total_counts[key(before)] > 2 or not target
        reason = ('时间归属需要核对，请逐项选择' if ambiguous and after else
                  '对应原时间，可选择替换' if after else
                  '保留原文：没有可直接对应的时间；请按语境手动核对')
        suggestions.append(TimeSuggestion(id=f'{field}:{utf16(text[:a])}', field=field,
            start=utf16(text[:a]), length=utf16(before), before=before, after=after,
            context=text[max(0,a-28):min(len(text),b+40)], ambiguous=ambiguous, reason=reason))
    snapshot = hashlib.sha256(json.dumps(body.model_dump(mode='json'), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    overflow = '时间文字较多，仅展示前 100 处；其他内容请继续手动核对。' if len(matches) > 100 else ''
    return TimePreview(snapshot=snapshot, suggestions=suggestions,
        message=overflow + ('只应用你选中的文字修改；其他日期和聊天原文会保留。' if suggestions else
        '未找到可直接对应的时间文字。标题和正文保持原样，请按语境手动核对。'))

def edited_time(previous, incoming):
    """Clients cannot fabricate original-chat evidence or clear edit provenance."""
    result = incoming.model_copy(deep=True)
    if (previous.status, previous.value) != (incoming.status, incoming.value):
        result.source_message_ids = []
        result.user_edited = True
    else:
        result.source_message_ids = previous.source_message_ids
        result.user_edited = previous.user_edited
    return result


def time_date(information):
    from app.services.story_guidance import exact_date
    if information.time.user_edited and not re.fullmatch(
            r'[0-9]{4}(?:-[0-9]{1,2}-[0-9]{1,2}|/[0-9]{1,2}/[0-9]{1,2}|年[0-9]{1,2}月[0-9]{1,2}[日号])', information.time.value or ''):
        return None
    return exact_date(information)
