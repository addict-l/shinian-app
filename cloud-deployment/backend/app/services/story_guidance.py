"""Evidence checks, single-question guidance and deterministic readiness rules."""
import re
from datetime import date

from app.ai.llm_client import LLMResponseFormatError
from app.schemas.story_information import StoryInformation, InformationStatus, InformationConflict
from app.schemas.story_guidance import StoryReadiness

DIMENSIONS = ('people', 'event', 'time', 'place', 'feeling', 'detail')
REQUIRED = ('people', 'event')
LABELS = dict(people='人物', event='事件经过', time='时间', place='地点', feeling='感受', detail='细节')


def user_texts(messages):
    return {message.id: message.content.strip() for message in messages
            if message.role == 'user' and message.type != 'notice' and message.content.strip()}



def _without_superseded_alternatives(conflict, excluded_values, new_ids):
    if conflict is None or conflict.dimension not in ('time', 'place'):
        return conflict
    # A later model replay must not revive a statement the user corrected.
    # Newly cited statements can introduce genuine conflicts or restore a fact.
    alternatives = [item for item in conflict.alternatives
                    if item.value not in excluded_values or new_ids.intersection(item.source_message_ids)]
    return conflict.model_copy(update={'alternatives': alternatives}) if len(alternatives) >= 2 else None


def validate_information(value: StoryInformation, messages, previous=None, compatible_places=(), compatible_times=()):
    texts = user_texts(messages)
    for label, sources in (('地点', compatible_places), ('时间', compatible_times)):
        for source in sources:
            if source.message_id not in texts or source.quote not in texts[source.message_id]:
                raise LLMResponseFormatError(f'兼容{label}判断必须引用本段用户的连续原文')
    def compatible(items, sources):
        return len(sources) >= 2 and all(
            item.status in (InformationStatus.known, InformationStatus.approximate)
            and any(source.message_id in item.source_message_ids and item.value in source.quote
                    for source in sources) for item in items)
    def contradicting_calendar(items):
        # A compatibility claim cannot erase distinct explicit calendar values.
        # Non-calendar periods (e.g. childhood) still need model evidence.
        for pattern in (r'(?<!\d)(\d{4})(?:年|[-/])', r'(?<!\d)(\d{1,2})月', r'(?<!\d)(\d{1,2})(?:日|号)'):
            values = [{int(number) for number in re.findall(pattern, item.value or '')} for item in items]
            values = [value for value in values if value]
            if len(values) > 1 and (any(len(value) != 1 for value in values) or len(set.union(*values)) > 1):
                return True
        iso = [re.search(r'(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)', item.value or '') for item in items]
        for index, pattern in ((1, r'(?<!\d)(\d{1,2})月'), (2, r'(?<!\d)(\d{1,2})(?:日|号)')):
            numbers = {int(match.group(index + 1)) for match in iso if match}
            numbers.update(int(number) for item in items for number in re.findall(pattern, item.value or ''))
            if len(numbers) > 1:
                return True
        return False
    dimensions = [(key, getattr(value, key)) for key in DIMENSIONS]
    dimensions += [(f'conflicts.{conflict.dimension}.alternatives[{index}]', item)
                   for conflict in value.conflicts for index, item in enumerate(conflict.alternatives)]
    for key, item in dimensions:
        if item.status == InformationStatus.missing:
            continue
        if not item.source_message_ids or any(key not in texts for key in item.source_message_ids):
            raise LLMResponseFormatError('Information must cite user text from this session')
        evidence = '\n'.join(texts[key] for key in item.source_message_ids)
        # Values are source excerpts, never inferred dates, emotions or invented descriptions.
        if item.value.strip() not in evidence:
            explanation = ('人物不能拼成“我、某人、另一人”的名单；请选择含主要人物关系的一段连续用户原话，无需列出所有人物。' if key == 'people' else '')
            raise LLMResponseFormatError(f'{key}.value 不是所引用用户消息中的连续原文。{explanation}请逐字复制用户原话，尤其不要把我改为他或改标点；不要从助手消息提取事实。')
        if item.status == InformationStatus.unknown and not any(word in item.value for word in
                ('记不清', '记不得', '不记得', '不知道', '忘了', '想不起来', '不清楚', '无法确定', '不能确定', '不确定', '说不准', '记不准')):
            raise LLMResponseFormatError('Unknown requires an explicit statement')
        if item.status == InformationStatus.withheld and not any(word in item.value for word in
                ('不想', '不愿', '不说', '不讲', '暂不', '不方便', '保密', '不提供', '不谈', '不聊', '不回答', '拒绝', '先别问', '不要问')):
            raise LLMResponseFormatError('Withheld requires an explicit refusal')
    if len({c.dimension for c in value.conflicts}) != len(value.conflicts):
        raise LLMResponseFormatError('Duplicate conflicts')
    for conflict in value.conflicts:
        if any(item.status == InformationStatus.missing for item in conflict.alternatives):
            raise LLMResponseFormatError('Conflict alternatives need evidence')
        if len({item.value for item in conflict.alternatives}) < 2:
            raise LLMResponseFormatError('Conflict alternatives must differ')
    if previous is not None:
        value.excluded_values = list(previous.excluded_values)
        new_ids = set(texts) - set(previous.analyzed_message_ids)
        value.conflicts = [remaining for conflict in value.conflicts
                           if (remaining := _without_superseded_alternatives(conflict, previous.excluded_values, new_ids)) is not None]
        last_question = next((m.content for m in reversed(messages) if m.role == 'assistant' and m.type != 'notice'), '')
        for key in DIMENSIONS:
            old, current = getattr(previous, key), getattr(value, key)
            if (old.status != InformationStatus.missing and current.status == InformationStatus.missing
                and old.source_message_ids and all(mid in texts for mid in old.source_message_ids)
                and old.value in '\n'.join(texts[mid] for mid in old.source_message_ids)):
                # A new answer on a different dimension cannot erase facts already collected.
                setattr(value, key, old)
        for key in ('time', 'place'):
            old, current = getattr(previous, key), getattr(value, key)
            if (current.value in previous.excluded_values and not new_ids.intersection(current.source_message_ids)
                and old.status != InformationStatus.missing and old.value not in previous.excluded_values
                and old.source_message_ids and all(mid in texts for mid in old.source_message_ids)
                and old.value in '\n'.join(texts[mid] for mid in old.source_message_ids)):
                # Keep the accepted correction if the model selects an old source again.
                setattr(value, key, old)
                current = old
            old_conflict = _without_superseded_alternatives(
                next((c for c in previous.conflicts if c.dimension == key), None), previous.excluded_values, new_ids)
            has_conflict = any(c.dimension == key for c in value.conflicts)
            related = [old, current, *(old_conflict.alternatives if old_conflict else [])]
            sources = compatible_places if key == 'place' else compatible_times
            refinement = (not has_conflict and compatible(related, sources)
                          and (key != 'time' or not contradicting_calendar(related)))
            if refinement:
                # The model explicitly assessed semantic compatibility, with
                # every old/current alternative grounded in user text. Keep
                # stricter fallback checks when that assessment is absent.
                continue
            cited_new = new_ids.intersection(current.source_message_ids)
            correction = bool(cited_new) and ((old_conflict is not None and ('？' in last_question or '?' in last_question)
                and all(item.value in last_question for item in old_conflict.alternatives))
                or any(word in texts[mid] for mid in cited_new for word in
                       ('更正', '修订', '修正', '说错', '记错', '不是', '应该是', '确认是', '以此为准', '其实')))
            if old_conflict and not has_conflict and not correction:
                value.conflicts.append(old_conflict)
            elif (not has_conflict and not old_conflict and not correction
                  and old.status in (InformationStatus.known, InformationStatus.approximate)
                  and current.status in (InformationStatus.known, InformationStatus.approximate)
                  and old.value != current.value and old.value not in current.value and current.value not in old.value):
                value.conflicts.append(InformationConflict(dimension=key, alternatives=[old, current]))
            if correction and not has_conflict and (old_conflict or old.value != current.value):
                discarded = old_conflict.alternatives if old_conflict else [old]
                value.excluded_values.extend(item.value for item in discarded if item.value and item.value != current.value
                                             and item.value not in (current.value or ''))
        for key in DIMENSIONS:
            old, current = getattr(previous, key), getattr(value, key)
            if current.status == InformationStatus.withheld and old.value and old.status != InformationStatus.withheld:
                value.excluded_values.append(old.value)
        # A later explicit correction can restore an earlier fact.
        accepted_values = [getattr(value, key).value for key in DIMENSIONS
                           if getattr(value, key).status != InformationStatus.withheld]
        value.excluded_values = list(dict.fromkeys(item for item in value.excluded_values if item not in accepted_values))
    else:
        value.excluded_values = []
    value.analyzed_message_ids = list(texts)
    return value


def readiness(information, messages, primary_person_id, completed=False):
    texts = user_texts(messages)
    stale = bool(texts) and set(texts) != set(information.analyzed_message_ids)
    missing = [key for key in REQUIRED if getattr(information, key).status == InformationStatus.missing
               or (key in ('people', 'event') and getattr(information, key).status not in
                   (InformationStatus.known, InformationStatus.approximate))]
    if primary_person_id is None and 'people' not in missing:
        missing.insert(0, 'people')
    conflicts = [c.dimension for c in information.conflicts]
    ready = bool(texts) and not (missing or conflicts or stale or completed)
    if completed:
        message = '这段回忆已保存。'
    elif stale:
        message = '新讲述的信息尚未整理完成，请重试后再生成草稿。'
    elif conflicts:
        message = '请先确认' + '、'.join(LABELS[key] for key in conflicts) + '中的不同说法。'
    elif missing:
        message = '这件事的主要人物和经过还不太清楚，您可以再讲一点。'
    else:
        message = '已有讲述可以整理成草稿，您也可以继续讲。'
    return StoryReadiness(ready=ready, missing_dimensions=missing, conflicting_dimensions=conflicts,
                          needs_analysis=stale, message=message)


def exact_date(information):
    if information.time.status != InformationStatus.known:
        return None
    text = information.time.value or ''
    if any(word in text for word in ('大概', '大约', '差不多', '可能', '左右', '好像', '约莫', '记不清', '记不得',
                                     '不确定', '前后', '大致', '或', '到', '至')):
        return None
    match = re.search(r'(?<!\d)(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})(?:日|号)?(?!\d)', text)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def draft_evidence(information, messages):
    """Only current accepted excerpts reach drafting, so superseded facts stay out."""
    texts = user_texts(messages)
    excerpts = []
    excluded_values = information.excluded_values + [getattr(information, key).value for key in DIMENSIONS
        if getattr(information, key).status == InformationStatus.withheld and getattr(information, key).value]
    for key in DIMENSIONS:
        item = getattr(information, key)
        if item.status in (InformationStatus.missing, InformationStatus.withheld):
            continue
        for message_id in item.source_message_ids:
            if item.value and item.value in texts[message_id]:
                fragments = [item.value]
                for excluded in excluded_values:
                    fragments = [part for fragment in fragments for part in fragment.split(excluded) if part.strip()]
                for fragment in fragments:
                    excerpt = {'id': str(message_id), 'dimension': key, 'content': fragment.strip()}
                    if excerpt not in excerpts:
                        excerpts.append(excerpt)
    return excerpts


def validate_draft(draft, evidence, person=None, information=None):
    texts = {}
    for item in evidence:
        texts.setdefault(item['id'], []).append(item['content'])
    for passage in [draft.title, *draft.paragraphs]:
        for source in passage.sources:
            if not any(source.quote in excerpt for excerpt in texts.get(str(source.message_id), [])):
                raise LLMResponseFormatError('Draft source quote is absent')
        quotes = '\n'.join(source.quote for source in passage.sources)
        # Prevent invented ages, dates and other numeric details during paraphrasing.
        if not set(re.findall(r'\d+', passage.text)).issubset(set(re.findall(r'\d+', quotes))):
            raise LLMResponseFormatError('Draft invented numeric facts')
    if information and information.time.status == InformationStatus.known:
        years = set(re.findall(r'(?<!\d)(\d{4})年', information.time.value or ''))
        accepted_time = '\n'.join(item['content'] for item in evidence if item.get('dimension') == 'time')
        years.intersection_update(re.findall(r'(?<!\d)(\d{4})年', accepted_time))
        body = '\n'.join(p.text for p in draft.paragraphs)
        if not years.issubset(set(re.findall(r'\d{4}', body))):
            raise LLMResponseFormatError('草稿正文遗漏了用户明确提供或更正的年份。保留当前 time 中的明确年份，不使用旧年份；从输入中选择支持该年份的证据索引。')
    if not any('我' in paragraph.text for paragraph in draft.paragraphs):
        raise LLMResponseFormatError('Draft must use the record subject first person')
    accepted = '\n'.join(item['content'] for item in evidence)
    content = draft.title.text + '\n' + '\n'.join(p.text for p in draft.paragraphs)
    for word in ('儿子', '女儿', '孙子', '孙女'):
        if word in content and word not in accepted:
            raise LLMResponseFormatError(f'草稿新增了未提供的性别或亲属称呼“{word}”。子女性别未知时使用孩子，孙辈性别未知时使用孙辈；不得猜测。')
    parent_proxy = any(word in accepted for word in ('我爸', '我妈', '我父亲', '我母亲', '我的父亲', '我的母亲'))
    parent_subject = bool(person and person.get('relationship') in ('爸爸', '父亲', '妈妈', '母亲'))
    if (parent_proxy or parent_subject) and '孙辈' in content and '孙' not in accepted:
        raise LLMResponseFormatError('记录对象是父母，子女代述的“我”是孩子，不是孙辈。请用记录对象第一人称重新写作，不得改变代际关系。')
    return draft


def validate_analysis(value, messages, previous=None):
    validate_information(StoryInformation.model_validate(value.model_dump()), messages,
                         compatible_places=getattr(value, 'compatible_places', ()),
                         compatible_times=getattr(value, 'compatible_times', ()))
    compatibility_errors = []
    texts = user_texts(messages)
    for key, sources in (('time', getattr(value, 'compatible_times', ())),
                         ('place', getattr(value, 'compatible_places', ()))):
        conflict = next((item for item in value.conflicts if item.dimension == key), None)
        if conflict and sources:
            compatibility_errors.append(
                f'{key} 同时出现在 conflicts 和 compatible_{"times" if key == "time" else "places"}，'
                '这两种判断互相矛盾。原文可以同时成立时移除对应 conflicts；'
                '真正互斥或无法确定时保留 conflicts、清空对应兼容字段。'
                '不能复制旧误报后又声称兼容；请根据原文选择一种判断，不改变事实或来源。')
        if previous is not None and sources:
            old_conflict = next((item for item in previous.conflicts if item.dimension == key), None)
            related = [getattr(previous, key), *(old_conflict.alternatives if old_conflict else [])]
            for item in related:
                if (item.value and item.value not in previous.excluded_values and item.source_message_ids
                    and all(mid in texts for mid in item.source_message_ids)
                    and item.value in '\n'.join(texts[mid] for mid in item.source_message_ids)
                    and not any(source.message_id in item.source_message_ids and item.value in source.quote for source in sources)):
                    compatibility_errors.append(
                        f'compatible_{"times" if key == "time" else "places"} 的原文范围没有覆盖 '
                        f'previous_information.{key} 或旧冲突备选的完整 value。'
                        '请用 start_fragment/end_fragment 选择覆盖完整旧原文的范围，'
                        '旧 value 含整句话时不能只选择其中一个时间或地点词。')
                    break
    if compatibility_errors:
        raise LLMResponseFormatError('\n'.join(compatibility_errors))
    latest = messages[-1] if messages else None
    if latest and any(word in latest.content for word in ('更正', '修订', '修正', '说错', '记错', '确认是', '以此为准')):
        for key, words in (('time', ('年', '月', '日期', '时间')), ('place', ('地点', '地方', '地名', '城市'))):
            if any(word in latest.content for word in words) and (
                    latest.id not in getattr(value, key).source_message_ids):
                raise LLMResponseFormatError(f'最新用户明确更正了 {key}。请在 {key} 引用最新用户的纠正原文，不要继续沿用旧说法。')
            if any(word in latest.content for word in words):
                # Honor an evidenced explicit correction even if the model kept
                # a stale conflict. Different alternatives cited from this same
                # latest message remain unresolved and cannot be discarded.
                current = getattr(value, key)
                value.conflicts = [conflict for conflict in value.conflicts if conflict.dimension != key or
                    any(latest.id in alternative.source_message_ids and alternative.value != current.value
                        for alternative in conflict.alternatives)]
    request = getattr(value, 'generation_request', None)
    if request is not None:
        if latest is None or request.message_id != latest.id or request.quote not in latest.content:
            # An old request cannot reopen the offer after new narration.
            value.generation_request = None
        else:
            clause_start = max(latest.content.rfind(mark, 0, latest.content.find(request.quote)) for mark in ('。', '！', '？', '\n', '；')) + 1
            contextual_request = latest.content[clause_start:latest.content.find(request.quote) + len(request.quote)]
            if not requests_generation(request.quote) or not requests_generation(contextual_request):
                value.generation_request = None
    if (getattr(value, 'generation_request', None) is None and hasattr(value, 'generation_request')
        and latest and _direct_generation_command(latest.content)):
        # A clear command must cite the request itself, not only "以此为准".
        # Repair interpretation; never infer permission to generate here.
        raise LLMResponseFormatError('最新用户明确请求整理本段回忆。generation_request 不能为 null；请选择最新用户请求所在原文片段的编号。意图与就绪无关，信息缺失或矛盾也必须识别请求，不代表可以生成。')

    return value


def _direct_generation_command(text):
    # Only standalone commands and short confirmations require a repair.
    # All richer narration stays with model interpretation; no keyword fallback
    # enables an offer or bypasses the evidence/readiness boundary.
    if len(text) > 120 or not requests_generation(text):
        return False
    clauses = [re.sub(r'\s+', '', clause) for clause in re.split(r'[。！？!?；;，,\n]', text) if clause.strip()]
    confirmations = {'好', '好的', '嗯', '以此为准', '就这样', '先这样', '讲完了', '说完了', '这段回忆讲完了'}
    commands = [clause for clause in clauses if clause not in confirmations]
    if len(commands) != 1:
        return False
    return bool(re.fullmatch(
        r'(?:请|麻烦|现在|那就|能不能|能否|可以|能|您|你|帮我|帮忙|替我|给我|把|将)*'
        r'(?:这段回忆|这段故事|这份草稿)?(?:整理|生成|保存|记录|记下来|写下来|写成)'
        r'(?:一下)?(?:这段|这份|这个|本段|一段|一份)?(?:回忆|故事|草稿)?'
        r'(?:一下|吧|吗|好吗|可以吗|下来|成草稿|成回忆)*', commands[0]))


def requests_generation(text):
    # The model interprets context; this boundary rejects unsupported or negated requests.
    negation = r'(?:不要|先别|暂不|不想|不用|不必|不需要|不希望|不打算|不能|别|不)(?:再|帮我|现在|马上|立刻|急着|先|直接|自动|进行|去|要|替我|帮忙){0,3}(?:整理|生成|保存|记录|更新|写|存)'
    if re.search(negation, text):
        return False
    return bool(re.search(r'整理|生成|保存|记录|更新(?:回忆|草稿)|记下来|写下来|写成|写到这里|写起来|写吧|存下来|存一下', text))


def conversation_history(messages):
    # Attachments and their URLs never enter either model's text context.
    return [{'id': str(m.id), 'role': m.role, 'content': m.content}
            for m in messages if m.type != 'notice' and m.content.strip()]


def validate_saved_reply(value, title):
    if title not in value.text:
        raise LLMResponseFormatError('逐字引用已保存标题，不改写标题')
    remainder = value.text.replace(title, '')
    if remainder.count('？') + remainder.count('?') > 1 or '你' in remainder:
        raise LLMResponseFormatError('用您称呼，最多一个自然问题')
    if re.search(r'\d|\b(?:ready|missing|known|source_message_ids)\b', remainder):
        raise LLMResponseFormatError('不添加标题之外的数字或后台状态标签')
    if not re.search(r'已.{0,8}(?:保存|存好|留好|记好)|保存好|存好了|留好了|记好了', remainder):
        raise LLMResponseFormatError('明确告知这段回忆已保存')
    return value


def reply_policy(information, result, history, explicit_request=False):
    latest = next((m['content'] for m in reversed(history) if m['role'] == 'user'), '')
    pause = bool(re.search(r'(?:先|暂时|今天|现在)(?:不聊|不说|不讲|别聊|别问|不谈)|不想(?:再|继续)(?:聊|讲|说)|还想再想想|想安静|先休息|先停一下|不聊了|不说了|不讲了', latest))
    allowed = result.ready and (explicit_request or not information.conversation.automatic_offer_used) and (not pause or explicit_request)
    # An explicit end at the end of this turn is a natural stopping point, not
    # the mere presence of enough facts. Continued narration does not match.
    closing = bool(re.search(r'(?<!没有)(?<!没)(?<!未)(?<!不)(?:讲完了|说完了|说到这里|讲到这里)(?:了|吧)?[。！!\s]*$', latest))
    return {'allowed': allowed, 'explicit_request': explicit_request,
            'required_offer': allowed and (explicit_request or closing),
            'automatic_offer_used': information.conversation.automatic_offer_used,
            'allow_question': not pause}


def validate_reply(value, history, policy):
    if value.text.count('？') + value.text.count('?') > 1:
        raise LLMResponseFormatError('text 中有多个问号。必须删掉多余的问句，只保留一个最贴合当前话题的问题；不要仅把两个问题改成同义表达。')
    if not policy.get('allow_question', True) and ('？' in value.text or '?' in value.text):
        raise LLMResponseFormatError('本轮用户明确希望停一停，请给用户空间。只回应、不提问，text 不得包含问号，也不要换到相邻话题追问。')
    if '你' in value.text:
        raise LLMResponseFormatError('Address the record subject as 您, including proxy narration')
    if re.search(r'您(?:一定|肯定|必然|准是)|想必您', value.text):
        raise LLMResponseFormatError('不要替记录对象认定感受或想法，不使用“您一定”“您肯定”等推断；承接用户说过的事实，给用户表达空间。')
    if re.search(r'\b(?:missing|known|approximate|unknown|withheld|ready|source_message_ids)\b', value.text):
        raise LLMResponseFormatError('Do not expose internal information labels')
    if not set(re.findall(r'\d+', value.text)).issubset(set(re.findall(r'\d+', '\n'.join(m['content'] for m in history)))):
        raise LLMResponseFormatError('Conversation invented numeric facts')
    offered = value.action == 'offer_generation'
    generation_language = (r'整理(?:成|这|一下|好|草稿|一段|回忆)|生成|草稿|保存.*回忆|回忆.*保存|'
        r'(?:帮您|为您|替您).{0,8}(?:整理|记下|写下|存下)|(?:回忆|故事).{0,12}(?:记下|写下|存下)')
    mentions_generation = bool(re.search(generation_language, value.text))
    if offered and (not policy['allowed'] or not mentions_generation):
        raise LLMResponseFormatError('Generation offer needs eligibility and matching language')
    if (policy.get('required_offer') or (policy['explicit_request'] and policy['allowed'])) and not offered:
        raise LLMResponseFormatError('用户明确讲完或主动要求整理，且本轮允许提示。请尊重收尾，用 offer_generation 和简短自然语言说明先整理草稿、供用户确认；不要继续追问。')
    # Mentioning the user's request or explaining why we must wait is not an
    # invitation. Inspect each clause so "not now, but let's generate" still
    # fails, and a confirmation question cannot masquerade as acknowledgement.
    invitation_clauses = re.split(r'[。！？!?；;，,]|但是|不过|但', value.text)
    def invites_generation(clause):
        if not re.search(generation_language, clause):
            return False
        if (not any(item['role'] == 'user' for item in history)
            and re.match(r'^\s*我是.{0,80}(?:晚辈|助手)', clause)
            and not re.search(r'这段|这份|刚才|现在|马上|已经', clause)):
            # An opening can explain the assistant's general role. It cannot
            # offer to generate a particular story before any narration.
            return False
        if re.search(r'(?:不能|无法|不要|不用|不必|不想|先不|先别|暂不)(?:够|马上|立刻|直接|急着|现在|先|为您|帮您|替您|去){0,3}(?:整理|生成|保存|记下|写下|存下)', clause):
            return False
        if re.match(r'^\s*(?:我知道|我明白|我理解)?(?:您|刚才您)(?:是|还|也)?(?:想|希望|提到|说过|要求|打算)', clause):
            # A question offering generation is not a statement of what the
            # user requested. Its punctuation follows this clause in the split.
            return bool(re.search(re.escape(clause) + r'[？?]', value.text))
        return True
    if not offered and any(invites_generation(clause) for clause in invitation_clauses):
        raise LLMResponseFormatError('Generation language must match the offer action')
    if re.search(r'已(?:经)?(?:帮您|为您|替您)?(?:保存|生成)|保存(?:好|成功|完成)', value.text):
        raise LLMResponseFormatError('Conversation cannot claim it generated or saved a memory')
    return value
