"""Persistent topic controller. Models collect evidence; code chooses one question."""
import hashlib
import re
from copy import deepcopy
from uuid import UUID
from app.ai.llm_client import LLMResponseFormatError
from app.schemas.guided_interview import (GuidedInterviewState, GuidedQuestion, GuidedEventAssessment,
                                        GuidedAnswerAssessment, GuidedModuleAssessment)
from app.schemas.story_information import StoryInformation, InformationDimension, SourceQuote
from app.schemas.story_guidance import StoryReadiness, ConversationReply
from app.ai.guided_prompts import GUIDED_EVENT_PROMPT, GUIDED_ANSWER_PROMPT, GUIDED_MODULE_PROMPT

from app.services.interview_modules import (MODULE_NAMES, MODULE_TOPICS, PROFILE_FIELDS,
    STORY_PROFILES, topic_for, module_menu, requested_module)

SESSION_TYPE = 'guided_interview'
# Compatibility export for callers of the childhood pilot.
TOPICS = tuple((topic.profile, topic.text) for topic in MODULE_TOPICS['childhood'])
CONTROL = re.compile(r'^(?:没有(?:了|补充了)?|没有别的补充了|先保存|确认保存|保存吧|就这些|继续|继续聊|接着讲|先休息|先暂停|今天先不聊|暂时不想讲|跳过|跳过这题|略过|这题不适用|这段不想讲|我不想讲了)[。！!\s]*$')


def current_sources(messages):
    return [{'message_id': str(m.id), 'content': m.content} for m in messages
            if m.role == 'user' and m.content.strip() and m.type not in ('notice', 'interview_control')
            and not CONTROL.fullmatch(m.content.strip()) and requested_module(m.content.strip()) is None]


def opening_text(state):
    if not state.module_selected:
        return module_menu()
    if state.topic_index >= 6:
        return f'关于{MODULE_NAMES[state.module]}，您还有什么想留下来的？' + module_menu()
    return topic_for(state).text


def validate_quotes(quotes, texts):
    for q in quotes:
        candidates = texts.get(q.message_id, [])
        if isinstance(candidates, str):
            candidates = [candidates]
        if not any(q.quote in original for original in candidates):
            raise LLMResponseFormatError('Guided evidence must quote disclosed user text verbatim')


def validate_event(value, texts, current_ids):
    keys=[f.key for f in value.facts]
    if len(keys)!=len(set(keys)):
        raise LLMResponseFormatError('Guided fact keys must be unique')
    for fact in value.facts:
        validate_quotes(fact.evidence,texts)
        if fact.status not in ('missing','partial') and not fact.evidence:
            raise LLMResponseFormatError('Guided fact needs evidence')
        if fact.status in ('unknown','declined'):
            pattern='记不清|记不得|不记得|不知道|忘了|想不起|不清楚|说不准' if fact.status=='unknown' else '不想|不愿|不说|不讲|不谈|不回答|先别|不要问'
            if not any(re.search(pattern,q.quote) for q in fact.evidence):
                raise LLMResponseFormatError('Guided unavailable fact needs explicit user evidence')
    unit_ids={u.id for u in value.units}
    if len(unit_ids)!=len(value.units):raise LLMResponseFormatError('Guided unit IDs must be unique')
    for unit in value.units:
        validate_quotes([unit.evidence],texts)
        if unit.operation not in unit.evidence.quote:
            raise LLMResponseFormatError('Operation must be a verbatim part of its evidence')
        if unit.evidence.message_id not in current_ids:
            raise LLMResponseFormatError('Earlier event cannot supply current actions')
    for link in value.links:
        if link.start not in unit_ids or link.end not in unit_ids or link.start==link.end:
            raise LLMResponseFormatError('Guided links must reference distinct current units')
        validate_quotes(link.evidence,texts)
        if any(q.message_id not in current_ids for q in link.evidence):
            raise LLMResponseFormatError('Guided progression needs current event evidence')
    validate_quotes(value.unavailable_evidence,texts)
    if value.process_unavailable!='no' and not value.unavailable_evidence:
        raise LLMResponseFormatError('Process unknown/refusal needs explicit evidence')
    if value.process_unavailable != 'no':
        pattern = (r'记不清|记不得|不记得|不知道|忘了|想不起|不清楚|说不准'
                   if value.process_unavailable == 'unknown' else r'不想|不愿|不说|不讲|不谈|不回答|先别|不要问')
        if not any(q.message_id in current_ids and re.search(pattern,q.quote)
                   for q in value.unavailable_evidence):
            raise LLMResponseFormatError('Unknown/refused process needs explicit current user words; missing detail is not user uncertainty')
        if all(re.search(r'年份|哪.?年|几岁|日期|年月|具体时间|年龄',q.quote) and
               not re.search(r'经过|后来|后面|接着|做了什么|发生',q.quote)
               for q in value.unavailable_evidence):
            raise LLMResponseFormatError('Uncertain date cannot close an unanswered process target')
    return value


def merge_assessment(state, assessment, latest_id):
    previous={f.key:f for f in state.facts}
    for fact in assessment.facts:
        old=previous.get(fact.key)
        if old and old.status=='present' and fact.status in ('missing','partial','unknown','declined'):
            if not (fact.replaces_previous and any(q.message_id==latest_id and
                    re.search('更正|说错|记错|不是|应该|以此为准',q.quote) for q in fact.evidence)):
                continue
        if fact.replaces_previous and not any(q.message_id==latest_id and
                re.search('更正|说错|记错|不是|应该|以此为准',q.quote) for q in fact.evidence):
            raise LLMResponseFormatError('Fact replacement needs current explicit correction')
        previous[fact.key]=fact
    state.facts=list(previous.values())
    correcting=any(f.replaces_previous for f in assessment.facts)
    # Short replies cannot erase verified actions. Explicit corrections require
    # a fresh full extraction instead of retaining superseded action evidence.
    previous_units=[] if correcting else state.units
    previous_links=[] if correcting else state.links
    combined={};remap={}
    for unit in [*previous_units,*assessment.units]:
        signature=(unit.actor,unit.kind,str(unit.evidence.message_id),unit.operation)
        stable='u'+hashlib.sha256(repr(signature).encode()).hexdigest()[:20]
        remap[unit.id]=stable
        combined[stable]=unit.model_copy(update={'id':stable})
    # Remap old and new IDs separately: model-local u1 cannot overwrite an old u1.
    state.units=list(combined.values())
    links=[]
    for units,relations in ((previous_units,previous_links),(assessment.units,assessment.links)):
        mapping={u.id:'u'+hashlib.sha256(repr((u.actor,u.kind,str(u.evidence.message_id),u.operation)).encode()).hexdigest()[:20] for u in units}
        for link in relations:
            fixed=link.model_copy(update={'start':mapping[link.start],'end':mapping[link.end]})
            if fixed not in links:links.append(fixed)
    state.links=links
    if assessment.process_unavailable!='no':state.process_closed=True


def coverage(state):
    facts={f.key:f for f in state.facts}
    present=lambda key: key in facts and facts[key].status=='present'
    profile=topic_for(state).profile
    actual={u.id:u for u in state.units if u.kind=='actual'}
    progression=any(l.start in actual and l.end in actual for l in state.links)
    process=len(actual)>=2 and progression
    if profile in ('I','H','W'):process=process and any(u.actor=='self' for u in actual.values())
    if profile=='I':process=process and any(u.actor=='other' for u in actual.values())
    if profile in ('S','I','H'):
        # A self-contained account can identify its subject through a verified
        # self action. This does not assert that no one else was present.
        identified_self = (present('self_role') and any(u.actor=='self' for u in actual.values())
                           and not any(u.actor=='other' for u in state.units))
        result={'scope':True,'context':present('activity') and (present('participants') or identified_self),
                'self_role':present('self_role'),'process':process}
    else:
        result={key:process if key=='process' else present(key) for key in PROFILE_FIELDS[profile]}
        if profile == 'Q' and not result['wording']:
            # Remembering only the meaning establishes paraphrase mode; it is
            # not an unanswered demand to recover an exact historical sentence.
            result['wording'] = any(
                re.search(r'大意|大致意思|大概意思|记不清原句|只记得.{0,6}意思|不是原话|原话是|原句是', quote.quote)
                for key in ('wording', 'expression') for quote in (facts[key].evidence if key in facts else []))
    state.coverage=result
    return result


def readiness(state, messages, person_id, completed=False):
    covered=coverage(state)
    conflicts=[f.key for f in state.facts if f.status=='conflict']
    has_text=bool(current_sources(messages)) and bool(state.facts or state.units)
    # Save/export rights do not depend on filling every optional detail.
    can_draft=has_text and person_id is not None and not conflicts and not completed and state.topic_index<6
    return StoryReadiness(ready=can_draft,missing_dimensions=[k for k,v in covered.items() if not v],
        conflicting_dimensions=conflicts,message='这段回忆已保存。' if completed else
        '可以先整理现有讲述，也可以继续补充。' if can_draft else '请先讲述您想留下的回忆。')


def next_question(state):
    covered=coverage(state);facts={f.key:f for f in state.facts}
    unavailable={f.key for f in state.facts if f.status in ('unknown','declined')}
    missing=[]
    for fact in state.facts:
        if fact.status=='conflict':missing.append((fact.key,'conflict'))
    if not covered.get('context',covered.get('change',True)):
        if not facts.get('activity') or facts['activity'].status!='present':missing.append(('activity','activity'))
        elif not facts.get('participants') or facts['participants'].status!='present':missing.append(('participants','participants'))
    for key in ('activity','participants','before','after','self_role','choice','expression','wording'):
        if key in covered and not covered[key]:missing.append((key,key))
    if 'process' in covered and not covered['process'] and not state.process_closed:
        if not facts.get('self_role') or facts['self_role'].status!='present':missing.insert(0,('self_role','self_role'))
        else:missing.append(('process','process'))
    templates={
      'activity':('您想先讲其中哪一件事？','选定一件活动或经历即可；没有想讲的也可结束'),
      'participants':('您刚说的这位是谁？','一个可区分的称呼或关系，不要求姓名'),
      'before':('这次变化以前，您记得这一方面是什么样？','同一变化对象的前一个状态，不要求详细环境'),
      'after':('这次变化以后，这一方面变成什么样？','同一变化对象的后一个状态'),
      'self_role':('当时您自己做了什么？','本人一个真实动作、回应或在场观察；没有参与也是明确答案'),
      'process':('您记得那次接着发生了什么？','同一事件中紧接已说片段的一项实际变化或后续操作'),
      'conflict':('您刚才讲的不同说法，想以哪一种为准？','明确当前矛盾的一种说法，或者说明尚不确定'),
      'choice':('您当时最后选了怎么做？','本人作出的一项实际选择，不要求两个备选方案'),
      'expression':('您想留下的那句话是什么？','本人一句话或大意即可，不要求感悟或故事'),
      'wording':('这是您记得的原话，还是大致意思？','明确原话或转述；不确定就保留大意'),
    }
    for key,kind in missing:
        if key in unavailable:continue
        anchor=None
        if kind=='process':
            candidates=[u for u in state.units if u.kind=='actual' and u.actor=='self']
            if candidates:anchor=candidates[-1].evidence
        suffix=hashlib.sha256((str(anchor.message_id)+anchor.quote).encode()).hexdigest()[:16] if anchor else 'initial'
        target_key=key+':'+suffix
        if target_key in state.unavailable_targets:continue
        if target_key in state.answered_targets:
            # A target that was answered cannot be silently reset to missing.
            continue
        if state.asked_targets.get(target_key,0)>=2:continue
        text,rule=templates[kind]
        if anchor:
            text=f'您刚讲到“{anchor.quote.strip("。！？?！")[:160]}”，接着发生了什么？'
        return GuidedQuestion(key=target_key,target=key,text=text,accept_rule=rule,anchor=anchor)
    return None


def project_information(previous, state, sources):
    information=previous.model_copy(deep=True)
    facts={f.key:f for f in state.facts};current={s['message_id'] for s in sources}
    for key,target in (('participants','people'),('activity','event')):
        fact=facts.get(key)
        refs=[q for q in fact.evidence if str(q.message_id) in current] if fact else []
        if fact and fact.status=='present' and refs:
            setattr(information,target,InformationDimension(status='known',value=refs[0].quote,
                source_message_ids=[refs[0].message_id]))
    # Narrative remains the full current story, not a field-limited summary.
    controls=CONTROL
    information.narrative_sources=[SourceQuote(message_id=s['message_id'],quote=s['content']) for s in sources
                                   if not controls.fullmatch(s['content'])][-60:]
    information.analyzed_message_ids=[UUID(s['message_id']) for s in sources]
    information.guided_interview=state
    return information


def turn(client, previous, messages):
    state=previous.guided_interview.model_copy(deep=True)
    sources=current_sources(messages)
    latest_message=next(m for m in reversed(messages) if m.role=='user')
    latest={'message_id':str(latest_message.id),'content':latest_message.content}
    latest_id=latest_message.id
    text=latest['content'].strip();prior_phase=state.phase
    if not state.module_selected:
        # An unsolicited narrative stays durable while the user chooses its module.
        return previous.model_copy(deep=True),ConversationReply(
            text='您的讲述已保留。'+module_menu())
    if requested_module(text) == state.module:
        return project_information(previous,state,sources),ConversationReply(
            text=state.pending_question.text if state.pending_question else opening_text(state))
    if re.fullmatch(r'(?:跳过|跳过这题|略过|这题不适用|这段不想讲|我不想讲了)[。！!\s]*',text):
        # A skip must never discard narrative or a pending draft.
        if sources:
            return project_information(previous,state,sources),ConversationReply(
                text='已经讲的内容还保留着。您可以先核对保存这段，或先休息。')
        state.processed_topics[topic_for(state).id]='skipped'
        state=following(state)
        return project_information(previous,state,sources),ConversationReply(text=opening_text(state))
    if re.fullmatch(r'(?:先休息|先暂停|今天先不聊|暂时不想讲)[。！!\s]*',text):
        state.resume_phase=state.phase;state.phase='paused'
        return project_information(previous,state,sources),ConversationReply(text='好，先休息。您的讲述和采访位置都已保留。')
    if state.phase=='paused':state.phase=state.resume_phase or 'exploring';state.resume_phase=None
    if prior_phase=='paused' and re.fullmatch(r'(?:继续|继续聊|接着讲)[。！!\s]*',text):
        return project_information(previous,state,sources),ConversationReply(
            text=state.pending_question.text if state.pending_question else '好，您可以接着讲。')
    if state.phase=='module_review':
        if re.fullmatch(r'(?:没有(?:了|补充了)?|没有别的补充了|就这些)[。！!\s]*',text):
            state.phase='finished'
            return project_information(previous,state,sources),ConversationReply(text=f'好，{MODULE_NAMES[state.module]}这一部分先聊到这里。'+module_menu())
        state.topic_index=5;state.phase='exploring'
    elif state.phase=='finished':
        state.topic_index=5;state.phase='exploring'
    if prior_phase in ('supplement','review') and re.fullmatch(r'(?:没有(?:了|补充了)?|没有别的补充了|先保存|确认保存|保存吧|就这些)[。！!\s]*',text):
        state.phase='review';state.pending_question=None
        return project_information(previous,state,sources),ConversationReply(
            text='好，先核对这段草稿，您确认后再保存。',action='offer_generation')
    if state.pending_question:
        from app.schemas.guided_interview import GuidedAnswerAssessment
        current_texts={latest_id:text}
        def validate_answer(value):
            validate_quotes(value.evidence,current_texts)
            return value
        answer=client._structured(GUIDED_ANSWER_PROMPT,{
            'pending_question':state.pending_question.model_dump(mode='json'),
            'current_source':latest,'event_sources':sources},GuidedAnswerAssessment,validate_answer)
        state.answer_status=answer.status
        if answer.status in ('unknown','declined'):
            state.unavailable_targets.append(state.pending_question.key)
            if state.pending_question.target=='process':state.process_closed=True
        elif answer.status=='answered':state.answered_targets.append(state.pending_question.key)
        elif answer.status=='paused':
            state.resume_phase=state.phase;state.phase='paused'
            return project_information(previous,state,sources),ConversationReply(text='好，先停在这里，您想继续时再讲。')
    from uuid import UUID
    texts={UUID(s['message_id']):s['content'] for s in sources}
    for q in state.background_sources:
        if q.message_id not in texts:
            texts[q.message_id] = [q.quote]
        elif isinstance(texts[q.message_id], list):
            texts[q.message_id].append(q.quote)
    assessment=client._structured(GUIDED_EVENT_PROMPT,{
        'module':MODULE_NAMES[state.module],'topic_id':topic_for(state).id,
        'topic':topic_for(state).text,'profile':topic_for(state).profile,
        'required_fields':PROFILE_FIELDS[topic_for(state).profile],
        'current_sources':sources,'background_sources':[q.model_dump(mode='json') for q in state.background_sources],
        'accepted_facts':[f.model_dump(mode='json') for f in state.facts],
        'pending_question':state.pending_question.model_dump(mode='json') if state.pending_question else None},
        GuidedEventAssessment,lambda value:validate_event(value,texts,{UUID(s['message_id']) for s in sources}))
    merge_assessment(state,assessment,latest_id)
    question=next_question(state)
    state.pending_question=question
    if question:
        state.asked_targets[question.key]=state.asked_targets.get(question.key,0)+1
        state.phase='exploring';reply=ConversationReply(text=question.text)
    elif prior_phase in ('supplement','review'):
        state.phase='review';reply=ConversationReply(text='这部分补充也记下了。您还有想补充的吗？')
    else:
        state.phase='supplement';reply=ConversationReply(text='这段可以先整理成草稿了。您还有什么想补充的吗？',action='offer_generation')
    return project_information(previous,state,sources),reply


def following(previous):
    state=GuidedInterviewState(module=previous.module,topic_index=min(previous.topic_index+1,6),
        processed_topics=dict(previous.processed_topics),material_memory_ids=list(previous.material_memory_ids),
        completed_modules=list(previous.completed_modules),module_checkpoints=dict(previous.module_checkpoints),
        saved_memory_ids=list(previous.saved_memory_ids),qualified_memory_ids=list(previous.qualified_memory_ids),
        chapter_ready=previous.chapter_ready,module_assessment=previous.module_assessment,
        module_assessed_count=previous.module_assessed_count,
        background_sources=list(previous.background_sources))
    if state.topic_index==6:
        state.phase='module_review'
        if state.module not in state.completed_modules:state.completed_modules.append(state.module)
    return state


def assess_module(client, state, memories):
    allowed={memory.id for memory in memories}
    texts={}
    memory_sources={}
    for memory in memories:
        memory_sources[memory.id]={q.message_id for q in memory.information.narrative_sources}
        for q in memory.information.narrative_sources:
            texts.setdefault(q.message_id, []).append(q.quote)
    def validate(value):
        if not set(value.duplicate_memory_ids+value.conflicting_memory_ids).issubset(allowed):
            raise LLMResponseFormatError('Module references must belong to saved interview memories')
        validate_quotes(value.evidence,texts)
        if (value.duplicate_memory_ids or value.conflicting_memory_ids) and not value.evidence:
            raise LLMResponseFormatError('Module objections require saved material evidence')
        for identity in value.duplicate_memory_ids+value.conflicting_memory_ids:
            if not any(q.message_id in memory_sources[identity] for q in value.evidence):
                raise LLMResponseFormatError('Each flagged memory needs its own original evidence')
        return value
    result=client._structured(GUIDED_MODULE_PROMPT,{
        'module':MODULE_NAMES[state.module],
        'controller_metrics':{'saved_count':len(state.saved_memory_ids),'qualified_count':len(state.qualified_memory_ids),
            'material_count':len(state.material_memory_ids),'processed_topics':state.processed_topics,
            'story_target':None if state.module=='reflection' else 5,'pending_save':False},
        'saved_memories':[{'memory_id':str(m.id),'sources':[q.model_dump(mode='json') for q in m.information.narrative_sources]} for m in memories]},
        GuidedModuleAssessment,validate)
    state.module_assessment=result
    state.module_assessed_count=len(state.saved_memory_ids)
    # Reflection is expression, never a quota of five fabricated episodes.
    sufficient=bool(state.material_memory_ids) if state.module=='reflection' else (
        len(state.material_memory_ids)>=5 and bool(state.qualified_memory_ids))
    state.chapter_ready=sufficient and not (result.duplicate_memory_ids or result.conflicting_memory_ids)
    return state
