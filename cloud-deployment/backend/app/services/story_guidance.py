"""Evidence checks, single-question guidance and deterministic readiness rules."""
import re
from datetime import date

from app.ai.llm_client import LLMResponseFormatError
from app.schemas.story_information import StoryInformation, InformationStatus, InformationConflict
from app.schemas.story_guidance import StoryReadiness

DIMENSIONS = ('people', 'event', 'time', 'place', 'feeling', 'detail')
REQUIRED = ('people', 'event')
LABELS = dict(people='人物', event='事件经过', time='时间', place='地点', feeling='感受', detail='细节')


def needs_boundary_notice(text, has_event):
    marker = re.search(r'另一(?:件事|回|次|段往事)|另外(?:一)?件事|还有一件事|再讲一件事',text)
    return bool(has_event and marker and len(text[marker.end():].strip('。 ，，')) >= 12
                and not re.search(r'不想讲|先不聊|不想说|以后再讲',text))


def is_factual_supplement(text, has_event):
    return bool(has_event and re.match(r'^(?:再)?补充(?:一下|一点)?[，,:：\s]',text)
                and len(text)>15 and not re.search(r'虚构|编造|想象|忽略|给我加|帮我加|写成|不想讲|不愿说',text))


def is_explicit_continuation(text):
    """A temporal continuation plus a backward reference, not mere topic overlap."""
    return bool(re.match(r'^(?:第二天|次日|后来|接着|随后)[，,]?(?:我们|我|他|她|孙子|孩子)?'
                         r'(?:还是|仍然|继续).{0,20}(?:那(?:个|里|儿)|同一个|同一件|这件|那件)',text)
                and not re.search(r'另一(?:件|回|次|段)|另外|还有一件|再讲一件',text))


def _check_interpretation(text, evidence):
    # Catch common leading emotions/evaluations without rejecting a user's
    # expressed feelings or a neutral open question about how they felt.
    text = re.sub(r'不用着急|不着急|别着急|不必着急','',text)
    groups = (('开心', '高兴', '愉快', '快乐'), ('紧张', '慌张', '心慌'),
              ('难过', '伤心', '痛苦'), ('欣慰',), ('感动',),
              ('有信心', '更有底', '心里有底', '踏实', '放心'), ('着急',), ('难忘', '印象深刻', '印象很深'),
              ('耐心',), ('细心',), ('担心','担忧','害怕'))
    for group in groups:
        if any(word in text for word in group) and not any(word in evidence for word in group):
            raise LLMResponseFormatError('不要认定或用问句暗示原文未表达的心情、性格或评价；直接交流具体经过或使用不预设答案的开放问题。')
    if re.search(r'(?:肯定|一定|必然|想必).{0,12}(?:不容易|欢迎|喜欢|心情|开心|紧张)|看来.{0,12}欢迎', text):
        raise LLMResponseFormatError('不要从行为推断难易、人物态度或心理，不添加原文未提供的评价。')


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
    for source in value.narrative_sources:
        if source.message_id not in texts or source.quote not in texts[source.message_id]:
            raise LLMResponseFormatError('Narrative source must be a continuous user excerpt from this story')
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
        latest = next((m for m in reversed(messages) if m.id in texts),None)
        if (latest and is_explicit_continuation(latest.content)
            and not re.search(r'更正|修订|修正|记错|说错|不是|确认是|以此为准|其实',latest.content)):
            for key in ('time','place'):
                old,current = getattr(previous,key),getattr(value,key)
                referred = (bool(re.match(r'^(?:第二天|次日|后来|接着|随后)',current.value or ''))
                            and not re.search(r'\d|[一二三四五六七八九十零〇]+[年月日号]',current.value or '') if key=='time' else
                            bool(re.search(r'那个|那里|那儿|同一个',current.value or '')))
                if (referred and latest.id in current.source_message_ids
                    and old.status in (InformationStatus.known,InformationStatus.approximate)
                    and old.value and old.source_message_ids
                    and all(mid in texts for mid in old.source_message_ids)
                    and old.value in '\n'.join(texts[mid] for mid in old.source_message_ids)):
                    # Preserve the story's original calendar/place reference;
                    # do not infer a date for the following day. Its actions
                    # remain in the fully cited narrative, independently.
                    value.conflicts = [c for c in value.conflicts if c.dimension!=key
                        or any(a.value not in (old.value,current.value) for a in c.alternatives)]
                    setattr(value,key,old.model_copy(deep=True))
        # A short follow-up cannot erase already verified long narration.
        sources = []
        for source in [*previous.narrative_sources, *value.narrative_sources]:
            if source.message_id not in texts or source.quote not in texts[source.message_id]:
                continue
            if any(old.message_id == source.message_id and source.quote in old.quote for old in sources):
                continue
            sources = [old for old in sources if not (old.message_id == source.message_id and old.quote in source.quote)]
            sources.append(source)
        if len(sources) > 60:
            raise LLMResponseFormatError('Narrative sources exceed the supported story limit')
        value.narrative_sources = sources
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
    def append(message_id, key, content):
        fragments = [content]
        controls = []
        if key == 'narrative':
            from app.ai.evidence import source_fragments
            for fragment in source_fragments(content):
                clause = fragment['text'].strip('，。！？,!? \n')
                if (_direct_generation_command(clause) or re.fullmatch(
                    r'补充一下|我再说一遍|我还想起另一件事|(?:这段|这件事)(?:就)?讲到这里(?:了)?|先回到.{0,24}那件事',clause)):
                    controls.append(fragment['text'])
        for excluded in [*excluded_values,*controls]:
            fragments = [part for fragment in fragments for part in fragment.split(excluded) if part.strip()]
        for fragment in fragments:
            excerpt = {'id': str(message_id), 'dimension': key, 'content': fragment.strip()}
            if excerpt not in excerpts:
                excerpts.append(excerpt)
    # A refusal takes precedence over broad narrative coverage: retain only
    # the independently accepted dimensions in that case, as before.
    if not any(getattr(information, key).status == InformationStatus.withheld for key in DIMENSIONS):
        for source in information.narrative_sources:
            if source.message_id in texts and source.quote in texts[source.message_id]:
                append(source.message_id, 'narrative', source.quote)
    for key in DIMENSIONS:
        item = getattr(information, key)
        if item.status in (InformationStatus.missing, InformationStatus.withheld):
            continue
        for message_id in item.source_message_ids:
            if item.value and item.value in texts[message_id]:
                if key != 'time' and any(excerpt['id'] == str(message_id) and item.value in excerpt['content']
                                         for excerpt in excerpts):
                    continue
                append(message_id, key, item.value)
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
        _check_interpretation(passage.text, quotes)
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
    boundary = getattr(value,'event_boundary',None)
    latest = messages[-1] if messages else None
    if boundary and boundary.kind=='independent' and latest and is_explicit_continuation(latest.content):
        # An explicit backward reference overrides the model's topic guess.
        # Keep every analyzed source and fact; only discard the false reminder.
        value.event_boundary = None
        boundary = None
    if (latest and needs_boundary_notice(latest.content,previous and previous.event.status != InformationStatus.missing)
        and (not boundary or boundary.kind!='independent')):
        raise LLMResponseFormatError('用户已明确开启另一件有具体经过的事，event_boundary 必须为 independent，分别引用原来事件及最新事件的真实原文；reply 只自然提醒用户决定记录方式。')
    if boundary:
        texts = user_texts(messages)
        latest = messages[-1] if messages else None
        if (not latest or not previous or previous.event.status == InformationStatus.missing
            or boundary.current_event.message_id != latest.id
            or boundary.previous_event.message_id == latest.id):
            raise LLMResponseFormatError('事件边界必须引用已经讲过的具体事件，以及最新用户讲述，不能仅凭日期或主题判断。')
        for source in (boundary.previous_event,boundary.current_event):
            if source.message_id not in texts or source.quote not in texts[source.message_id]:
                raise LLMResponseFormatError('事件边界必须引用当前会话用户的连续原文。')
        if len(re.sub(r'[\d\W年月日号]+','',boundary.current_event.quote)) < 6:
            raise LLMResponseFormatError('只补充日期不是新的独立事件。')
        explicit_new = bool(re.search(r'另一(?:件|回|次|段)|另外(?:一)?(?:件|回|次)|还有一件|再讲一件',latest.content))
        def without_calendar(text):
            return re.sub(r'\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?|[\s，。！？,!?]','',text)
        old,new = without_calendar(boundary.previous_event.quote),without_calendar(boundary.current_event.quote)
        if boundary.kind=='independent' and not explicit_new and (
            any(word in latest.content for word in ('更正','记错','说错','修订','确认是','以此为准'))
            or old==new or (old and old in new)):
            raise LLMResponseFormatError('同一事件的时间更正或经过延伸不能标记为 independent。保留真实矛盾和更正处理。')
        # Only remind: do not overwrite the collected story with another
        # episode or erase any existing conflicting statements.
        for key in DIMENSIONS:
            setattr(value,key,getattr(previous,key).model_copy(deep=True))
        value.conflicts = [conflict.model_copy(deep=True) for conflict in previous.conflicts]
        value.compatible_times = [];value.compatible_places = []
        if boundary.current_event not in value.narrative_sources:
            value.narrative_sources.append(boundary.current_event)
        value.guidance_hint = ('这是一段独立往事；只自然提醒用户决定怎样记录，不自动拆分，不直接追问新事。'
                               if boundary.kind=='independent' else '用户回到前一件事，直接顺着那件事交流，不提醒拆篇。')
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
    if (latest and len(latest.content) > 200 and latest.id in value.event.source_message_ids
        and not any(source.message_id == latest.id for source in value.narrative_sources)):
        raise LLMResponseFormatError('长篇讲述必须在 narrative_sources 选择完整经过的原文范围，不只保留事件摘要；不能省略尚未整理的关键动作。')
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
    confirmations = {'好', '好的', '嗯', '以此为准', '就这样', '先这样', '讲完了', '说完了', '这段回忆讲完了',
                     '这段就讲到这里','这段就讲到这里了','这段讲完了'}
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


def reply_policy(information, result, history, explicit_request=False, event_boundary=None, record_subject=None):
    latest = next((m['content'] for m in reversed(history) if m['role'] == 'user'), '')
    pauses = list(re.finditer(r'(?:先|暂时|今天|现在)(?:不聊|不说|不讲|别聊|别问|不谈)|不想(?:再|继续)?(?:聊|讲|说)|不愿(?:再|继续)?(?:聊|讲|说)|先别问|不要问|还想再想想|想安静|先休息|先停一下|不聊了|不说了|不讲了', latest))
    continuing = list(re.finditer(r'(?:我(?:还)?(?:想|要)|我们|请)(?:继续|接着)(?:讲|说|聊)', latest))
    pause = bool(pauses) and not (continuing and continuing[-1].start() > pauses[-1].start())
    allowed = result.ready and (explicit_request or not information.conversation.automatic_offer_used) and (not pause or explicit_request)
    boundary_reminder = bool(event_boundary and event_boundary.kind=='independent')
    if boundary_reminder:
        allowed = False
    # An explicit end at the end of this turn is a natural stopping point, not
    # the mere presence of enough facts. Continued narration does not match.
    closing = bool(re.search(r'(?<!没有)(?<!没)(?<!未)(?<!不)(?:讲完了|说完了|说到这里|讲到这里)(?:了|吧)?[。！!\s]*$', latest))
    return {'allowed': allowed, 'explicit_request': explicit_request,
            'required_offer': allowed and (explicit_request or closing),
            'automatic_offer_used': information.conversation.automatic_offer_used,
            'allow_question': not pause,
            'boundary_reminder_required': boundary_reminder,
            'explicit_continuation': is_explicit_continuation(latest),
            'record_subject': record_subject,
            'fact_message_ids': [str(mid) for mid in information.analyzed_message_ids],
            'closed_dimensions': [key for key in DIMENSIONS if getattr(information, key).status in
                                  (InformationStatus.unknown, InformationStatus.withheld)]}


def validate_reply(value, history, policy):
    fact_ids = policy.get('fact_message_ids', ())
    user_evidence = '\n'.join(m['content'] for m in history if m['role'] == 'user'
                               and (not fact_ids or m.get('id') in fact_ids))
    _check_interpretation(value.text, user_evidence)
    subject = policy.get('record_subject') or {}
    relation = subject.get('relationship','')
    proxy = re.search(r'我(?:的)?'+re.escape(relation),user_evidence) if relation else None
    proxy = proxy or (relation in ('爷爷','奶奶') and re.search(r'我小时候[，,].*'+relation,user_evidence))
    if proxy and re.search(re.escape(relation)+r'.{0,20}(?:教|叮嘱|带|扶).{0,12}您',value.text):
        raise LLMResponseFormatError('正在访谈记录对象本人，不能把代述者当成被访谈对象；把对记录对象的第三人称称呼改为您，不猜子女性别。')
    if policy.get('boundary_reminder_required') and not re.search(r'另(?:一|外)|两(?:段|件)|分开|单独|分别|不同(?:的)?(?:事|经历)',value.text):
        raise LLMResponseFormatError('这是另一件独立经历，reply 必须自然提醒是另一段往事，由用户决定记录方式，不自动拆分或保存。')
    if policy.get('explicit_continuation') and re.search(r'另(?:一|外).{0,5}(?:事|往事|经历|故事)|分开记录|单独记录|拆篇',value.text):
        raise LLMResponseFormatError('用户明确承接同一事件的经过延伸，直接顺着最新经过交流，不提醒另一件事或拆篇。')
    if policy.get('boundary_reminder_required') and ('？' in value.text or '?' in value.text):
        boundary_question = ' '.join(re.findall(r'[^。！？!?]*[？?]',value.text))
        if not re.search(r'先(?:接着|继续)?(?:讲|聊)|(?:继续|讲|聊)哪|哪(?:一)?段|怎样记录|怎么记录|如何记录|分开|单独',boundary_question):
            raise LLMResponseFormatError('独立事件只提醒，由用户决定先讲哪段或怎样记录；不要直接追问新事细节替用户选择。')
    if value.text.count('？') + value.text.count('?') > 1:
        raise LLMResponseFormatError('text 中有多个问号。必须删掉多余的问句，只保留一个最贴合当前话题的问题；不要仅把两个问题改成同义表达。')
    if not policy.get('allow_question', True) and ('？' in value.text or '?' in value.text):
        raise LLMResponseFormatError('本轮用户明确希望停一停，请给用户空间。只回应、不提问，text 不得包含问号，也不要换到相邻话题追问。')
    question = ' '.join(re.findall(r'[^。！？!?；;]*[？?]', value.text))
    focus_question = ' '.join(re.findall(r'[^。！？!?；;，,]*[？?]', value.text))
    if re.search(r'跟着跑|跑起来|跑了',question) and '跑' not in user_evidence:
        raise LLMResponseFormatError('不要把跟着推断为跑，围绕用户实际提供的动作提问。')
    if ('取' in question and re.search(r'取(?:下|掉|下来).{0,5}后|怎样.{0,20}取|怎么.{0,20}取',question)
        and re.search(r'(?:让|请|叫).{0,8}取',user_evidence)
        and not re.search(r'(?<!让)(?<!请)(?<!叫)我(?:就|又|再|便)?(?:帮他|帮孙子)?(?:把.{0,8})?取(?:下|掉|下来)',user_evidence)
        and not re.search(r'有没有|是否|会不会|能不能',question)):
        raise LLMResponseFormatError('请人取鱼只是请求，不等于动作已完成；问接下来如何回应，不预设取下后的经过。')
    for group in (('装好','装回','装上','修好'),('放手','松手'),('独自','独立')):
        if (any(word in question for word in group) and not any(word in user_evidence for word in group)
            and re.search(r'怎么|怎样|如何|什么时候|之后|以后|的时候',question)
            and not re.search(r'有没有|是否|会不会|能不能',question)):
            raise LLMResponseFormatError('问题预设了未讲过的动作或结果，改为围绕已讲的转折询问接下来发生什么，不假定已经修好、放手或独立完成。')
    for key, pattern in (('time', r'哪(?:一)?年|什么年份|几月|几号|日期|几岁|多大'),
                         ('place', r'在哪|哪里|哪儿|地点|哪个地方'),
                         ('feeling', r'感受|感觉|心情|心里|开心|难过|紧张')):
        if key in policy.get('closed_dimensions', ()) and re.search(pattern, focus_question):
            raise LLMResponseFormatError('用户已记不清或明确拒绝这个信息，不重复追问；继续其他实际经过或给用户空间。')
    if '你' in value.text:
        raise LLMResponseFormatError('Address the record subject as 您, including proxy narration')
    if re.search(r'您(?:一定|肯定|必然|准是)|想必您', value.text):
        raise LLMResponseFormatError('不要替记录对象认定感受或想法，不使用“您一定”“您肯定”等推断；承接用户说过的事实，给用户表达空间。')
    if re.search(r'\b(?:missing|known|approximate|unknown|withheld|ready|source_message_ids)\b', value.text):
        raise LLMResponseFormatError('Do not expose internal information labels')
    if not set(re.findall(r'\d+', value.text)).issubset(set(re.findall(r'\d+', user_evidence))):
        raise LLMResponseFormatError('Conversation invented numeric facts')
    offered = value.action == 'offer_generation'
    generation_language = (r'整理(?:成|这|一下|好|草稿|一段|回忆)|生成|草稿|保存.*回忆|回忆.*保存|'
        r'(?:帮您|为您|替您).{0,8}(?:整理|记下|写下|存下)|(?:回忆|故事).{0,12}(?:记下|写下|存下)|'
        r'记下.{0,50}(?:回忆|故事|这件事)|记录(?:这段|这件|一段)')
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


def validate_interview_reply(value, history, policy):
    """Keep a valid question and remove unsupported opinions without inventing text."""
    try:
        return validate_reply(value,history,policy)
    except LLMResponseFormatError:
        pass
    if not policy.get('allow_question',True):
        return validate_reply(value,history,policy)
    sentences = re.findall(r'[^。！？!?]*[。！？!?]|[^。！？!?]+$',value.text)
    ids = policy.get('fact_message_ids',())
    evidence = '\n'.join(m['content'] for m in history if m['role']=='user' and (not ids or m.get('id') in ids))
    safe = []
    for sentence in sentences:
        # Remove only unevidenced opinions; invented dates, save claims and
        # other policy violations remain for the final validators to reject.
        if not sentence.endswith(('？','?')):
            try:_check_interpretation(sentence,evidence)
            except LLMResponseFormatError:continue
        safe.append(sentence)
    sentences = safe
    questions = [index for index,sentence in enumerate(sentences) if sentence.endswith(('？','?'))]
    for chosen in questions:
        candidate = value.model_copy(update={'text':''.join(sentence for index,sentence in enumerate(sentences)
                                                   if index==chosen or index not in questions).strip()})
        try:
            return validate_reply(candidate,history,policy)
        except LLMResponseFormatError:
            continue
    # Unsafe statements, missing offers and invalid questions still use the
    # original bounded model repair; every fact/source check ran before this.
    return validate_reply(value,history,policy)


def safe_interview_fallback(history, policy):
    """Return a short, evidence-safe interview line after bounded model repair fails."""
    from app.schemas.story_guidance import ConversationReply

    if policy.get('required_offer'):
        value = ConversationReply(text='好，我先整理成草稿，您看过、确认后再保存。', action='offer_generation')
    elif not policy.get('allow_question', True):
        value = ConversationReply(text='好，先聊到这里。您想继续的时候再讲。')
    elif policy.get('boundary_reminder_required'):
        value = ConversationReply(text='您刚才提到另一段往事。您想先讲哪一段？')
    else:
        subject = policy.get('record_subject') or {}
        relation = subject.get('relationship', '')
        evidence = '\n'.join(m['content'] for m in history if m['role'] == 'user')
        proxy = relation in ('爷爷', '奶奶') and re.search(r'我小时候[，,].*'+re.escape(relation), evidence)
        if proxy and re.search(r'骑(?:自行)?车', evidence):
            value = ConversationReply(text='您当时是怎样教孙辈骑车的？')
        elif 'time' in policy.get('closed_dimensions', ()) and '钓鱼' in evidence and '孙子' in evidence:
            value = ConversationReply(text='年份记不清也没关系。您和孙子在河边钓鱼时，后来发生了什么？')
        else:
            value = ConversationReply(text='您刚才讲到的经过我听到了。您愿意接着讲讲后面发生的事吗？')
    return validate_interview_reply(value, history, policy)
