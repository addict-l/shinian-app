"""Versioned human-authored baseline contracts; no model may expand the scope."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    profile: str
    text: str


MODULE_NAMES = {
    'childhood': '家乡与童年', 'growth': '求学与成长', 'work': '工作与劳动',
    'family': '家庭生活', 'later_life': '后来的生活', 'reflection': '人生回望',
}

# S=episode/daily life, I=interaction, H=operation, W=change,
# J=choice, Q=reported words, D=comparison, V=personal expression, K=existing memory.
MODULE_TOPICS = {
    'childhood': (
        Topic('CH01', 'S', '小时候家里平常的一天，您最记得哪一段？'),
        Topic('CH02', 'I', '和您小时候一起生活的人，有哪段相处您一直记得？'),
        Topic('CH03', 'S', '小时候喜欢做的事情里，哪一次经历您还记得？'),
        Topic('CH04', 'H', '小时候帮家里做过的事情里，哪一件您还记得？'),
        Topic('CH05', 'W', '童年那些年，家里的日子有没有发生过您记得的变化？'),
        Topic('CH06', 'S', '除了刚才这些，您还想留下哪件小时候的事？'),
    ),
    'growth': (
        Topic('GR01', 'S', '成长时刚开始学东西的日子里，哪一段经历您还记得？'),
        Topic('GR02', 'I', '那段成长日子里，和您记得的人有哪件相处的事愿意讲讲？'),
        Topic('GR03', 'H', '当时学过的东西，您还记得怎样学会其中一样吗？'),
        Topic('GR04', 'S', '那段日子里，还有哪件和别人一起经历的事想留下？'),
        Topic('GR05', 'J', '成长时做过的选择里，有哪一次您愿意讲讲？'),
        Topic('GR06', 'S', '除了刚才这些，您还想留下哪段成长经历？'),
    ),
    'work': (
        Topic('WK01', 'S', '您最初是怎样开始做事或劳动的？'),
        Topic('WK02', 'S', '刚开始做的时候，有哪件事一直记到现在？'),
        Topic('WK03', 'H', '做这些事时，您平常最记得哪一段忙活的过程？'),
        Topic('WK04', 'I', '和您一起做事的人，有哪段相处您愿意讲讲？'),
        Topic('WK05', 'W', '做事的方式发生过您记得的变化吗？'),
        Topic('WK06', 'S', '除了刚才这些，还有哪次做事的经历您特别想留下？'),
    ),
    'family': (
        Topic('FM01', 'I', '和您想先讲的那位家人，有哪件相处的事最先浮现在脑海里？'),
        Topic('FM02', 'S', '和家人一起过日子时，哪一段平常的生活您还记得？'),
        Topic('FM03', 'S', '家人一起做过的事里，有哪一件您想讲讲？'),
        Topic('FM04', 'W', '家里的日子有没有发生过您愿意讲的变化？'),
        Topic('FM05', 'Q', '您记得哪位家人说过的话，想留在书里？'),
        Topic('FM06', 'S', '除了刚才这些，还有哪段和家人有关的经历您想留下？'),
    ),
    'later_life': (
        Topic('LT01', 'S', '后来这段日子里，平常哪一段生活您最记得？'),
        Topic('LT02', 'S', '这些年愿意做的事情里，哪一次经历您还记得？'),
        Topic('LT03', 'I', '和这些年有来往的人，有哪件相处的事您想留下？'),
        Topic('LT04', 'S', '最近这些年，有哪件普通的小事您一直记得？'),
        Topic('LT05', 'D', '和过去相比，您想讲生活哪一方面的变化？'),
        Topic('LT06', 'V', '如今过日子的样子，有什么想让家人知道的？'),
    ),
    'reflection': (
        Topic('RV01', 'K', '讲过的往事里，您想让家人特别记住哪一段？'),
        Topic('RV02', 'V', '现在再想起您选的那段往事，您有什么想说的？'),
        Topic('RV03', 'V', '讲过的人里，您还想为哪一位留下什么话？'),
        Topic('RV04', 'V', '有什么您想亲口对家人说的话，愿意放进这本书里？'),
        Topic('RV05', 'V', '有没有您自己愿意留给家人的生活经验？'),
        Topic('RV06', 'V', '最后，还有什么您想留在这本书里的？'),
    ),
}

PROFILE_FIELDS = {
    'S': ('activity', 'participants', 'self_role', 'process'),
    'I': ('activity', 'participants', 'self_role', 'process'),
    'H': ('activity', 'participants', 'self_role', 'process'),
    'W': ('activity', 'before', 'after', 'self_role', 'process'),
    'J': ('activity', 'choice', 'self_role'),
    'Q': ('participants', 'expression', 'wording'),
    'D': ('activity', 'before', 'after'),
    'V': ('activity', 'expression'),
    'K': ('activity',),
}
STORY_PROFILES = frozenset(('S', 'I', 'H', 'W', 'J'))


LEGACY_MODULE_TOPICS = MODULE_TOPICS


def _contract_topics():
    from app.services.contract_interview_state import questions
    return {module: tuple(Topic(q['id'], 'V', q['main_question']) for q in questions(module))
            for module in MODULE_NAMES}


from app.services.contract_interview_state import runtime_configured, validate_pipeline
if runtime_configured():
    MODULE_TOPICS = _contract_topics()
    validate_pipeline()


def topic_count(state):
    if state.version == 3:
        from app.services.contract_interview_state import questions
        return len(questions(state.module, state.runtime_version))
    return len(MODULE_TOPICS[state.module] if state.version == 3 else LEGACY_MODULE_TOPICS[state.module])


def topic_for(state):
    if state.version == 3:
        from app.services.contract_interview_state import questions
        topics = questions(state.module, state.runtime_version)
        q = topics[min(state.topic_index, len(topics) - 1)]
        return Topic(q['id'], 'V', q['main_question'])
    topics = MODULE_TOPICS[state.module] if state.version == 3 else LEGACY_MODULE_TOPICS[state.module]
    return topics[min(state.topic_index, len(topics) - 1)]


def module_menu():
    return '接下来您想聊哪个部分？可以选：' + '、'.join(MODULE_NAMES.values()) + '，也可以先休息。'


def requested_module(text, allow_label=False):
    """Only a stand-alone explicit command switches modules; narratives are data."""
    import re
    labels = {**{v: k for k, v in MODULE_NAMES.items()}, '童年': 'childhood',
              '成长': 'growth', '工作': 'work'}
    if allow_label and text.strip('。！! \n') in labels:
        return labels[text.strip('。！! \n')]
    match = re.fullmatch(r'(?:我想|想|请)?(?:切换到|换到|进入|聊聊|聊|讲讲|讲)\s*(家乡与童年|童年|求学与成长|成长|工作与劳动|工作|家庭生活|后来的生活|人生回望)[。！!\s]*', text)
    if not match:
        return None
    labels = {**{v: k for k, v in MODULE_NAMES.items()}, '童年': 'childhood',
              '成长': 'growth', '工作': 'work'}
    return labels[match[1]]
