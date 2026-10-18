#!/usr/bin/env python3
"""Authoring source. contracts.json is runtime's sole contract input; regenerate Markdown."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = next((candidate for parent in HERE.parents
             for candidate in (parent/'interview-development-baseline.md', parent/'docs/interview-development-baseline.md')
             if candidate.is_file()), None)
if BASE is None:
    raise FileNotFoundError('interview-development-baseline.md not found in an ancestor or its docs/ directory')
text = BASE.read_text()
questions = {}
for line in text.splitlines():
    cells = [x.strip() for x in line.split('|')]
    if len(cells) == 5 and re.fullmatch(r'(CH|GR|WK|FM|LT|RV)\d\d', cells[1]):
        questions[cells[1]] = cells[2]
sk = re.search(r'## 骨架问题 开篇定调\n(.*?)## 骨架问题的要素', text, re.S).group(1)
for line in sk.splitlines():
    cells = [x.strip() for x in line.split('|')]
    if len(cells) == 5 and re.fullmatch(r'SK\d\d', cells[1]):
        questions[cells[1]] = cells[3]
    elif len(cells) == 5 and cells[1].isdigit():
        questions['SK%02d' % int(cells[1])] = cells[3]

contracts = {}
def E(suffix, label, kind, followup, usable, *, none=False, subjects=('self',), period='lifelong', activation=None, requirement='required', notes='', link=None, vague=()):
    return dict(suffix=suffix, label=label, type=kind, question=followup, usable_answer=usable,
                none=none, subjects=list(subjects), period=period, activation=activation,
                requirement=requirement, notes=notes, link=link, vague=list(vague))
def C(qid, title, elements, *, optional, premise=None, notes=''):
    ff=[]
    for f in elements:
        f=dict(f); suffix=f.pop('suffix'); ident=qid+'-'+suffix
        activation=f.pop('activation')
        if activation:
            activation={k:[(qid+'-'+v if isinstance(v,str) and not v.startswith(qid) else v) for v in vals]
                        if isinstance(vals,list) else vals for k,vals in activation.items()}
        if f.get('link'): f['link']['field_id']=qid+'-'+f['link']['field_id']
        subjects=f.pop('subjects'); period=f.pop('period')
        f.update(id=ident, question_id=qid, required=f['requirement']=='required', activation=activation or {'always':True},
                 scope={'subjects':subjects, 'period':period,
                        'object_relation':f['notes'] or '本人在本题实际问答中所指的'+f['label']+'；引用须证明该关系，不从题干假定事实。'},
                 negative_semantics=('本人明确表示没有本项情况；只覆盖本项目标，不由未提及推断。' if f['none'] else '本项不以“没有”替代事实；未知、无适用前提分别记录。'),
                 unknown_semantics='本人明确不知道、记不清或说不清本项目标时记 unknown；稿件未提及只记 missing。',
                 refusal_semantics='明确不愿讲记 declined；明确以后讲记 deferred；范围只限实际拒绝的目标。',
                 allowed_states=['missing','known','unknown','declined','deferred','ambiguous','conflict']+(['none'] if f['none'] else [])+(['not_applicable'] if premise else []))
        ff.append(f)
    ff.append(dict(id=qid+'-O1', question_id=qid, label=optional[0], type=optional[1], question=optional[2],
                   usable_answer=optional[3], required=False, requirement='optional', activation={'never_ask':True},
                   none=True, scope={'subjects':['self','family','other'], 'period':'as_stated', 'object_relation':'只记录本人主动补充且明确属于本题的内容。'},
                   negative_semantics='本人没有可补充内容可记 none，不影响本题完成。', unknown_semantics='保留未知，不追问可选信息。',
                   refusal_semantics='尊重对应范围，不追问。', allowed_states=['missing','known','none','unknown','declined','deferred','ambiguous']))
    if premise:
        ff.insert(0,dict(id=qid+'-A1',question_id=qid,label=premise['label'],type='applicability',question=premise['question'],usable_answer=premise['usable'],
                        required=False,requirement='conditional',activation={'premise_check':True},none=True,
                        scope={'subjects':['self'],'period':'as_stated','object_relation':premise['relation']},
                        negative_semantics=premise['negative'],unknown_semantics='本人明确不知道或不愿确认适用前提，可有限收口；不可假设有相关经历。',
                        refusal_semantics='只关闭本题相关前提分支，其他题目不继承。',allowed_states=['missing','known','none','unknown','declined','deferred','ambiguous','conflict']))
    contracts[qid]={'id':qid,'title':title,'main_question':questions[qid], 'material_type':sorted(set(f['type'] for f in ff if f['requirement']!='optional')),
                    'elements':ff,'premise':premise,'success':'必要要素与实际激活的条件要素均 known 或允许的明确 none，且作用域、关系与原话依据有效；不要求可选项。',
                    'limited':'其余仍开放的必要/已激活条件要素均已处理，部分目标明确 unknown/declined/deferred，或适用前提明确不存在；保留信息有限原因，不把一个未知扩大到全题，不计作材料齐全或已保存。',
                    'notes':notes}

O=lambda label,kind='detail',question='您还有想补充的吗？',usable='本人自愿提供的同题补充；缺少不影响完成。':(label,kind,question,usable)
K=lambda *ids:{'known':list(ids)}
U=lambda *ids:{'unless_none':list(ids)}
P=lambda label,question,usable,negative,pattern:dict(label=label,question=question,usable=usable,negative=negative,no_premise_pattern=pattern,relation='本题本人明确披露的适用经历，不能由其他题的婚育、学校或年龄推断。')
SCHOOL=P('本题是否有求学经历','您有过上学的经历吗？','本人明确有上学经历，或本题已讲出自己的学生经历。','本人明确没上过学，关闭本题学生经历分支。',r'没(?:有)?(?:上过|读过)学|从(?:来)?没(?:有)?(?:上|读)过?学|未(?:曾)?上过学')
PARTNER=P('本题是否有伴侣关系经历','您有过伴侣关系的经历吗？','本人明确的现任或过去伴侣经历均适用；不要求现在仍在婚，未婚不等于没有伴侣。','本人明确没有任何伴侣经历才关闭相应分支；丧偶、分居、离婚、未婚本身不等于从无伴侣。',r'没(?:有|过)?伴侣|从未有过伴侣|没有任何伴侣经历|没有谈过恋爱')
MARRIAGE=P('本题是否有婚姻或组建伴侣家庭经历','您有过婚姻生活或与伴侣组建家庭的经历吗？','本人明确的现任或过去婚姻/伴侣家庭经历适用；不要求现在仍在婚。','本人明确从无婚姻或伴侣家庭生活，可关闭对应分支；离婚、丧偶不等于从无经历。',r'没(?:有|过)?(?:结过婚|结婚|婚姻生活|组建过家庭)|终身未婚|从未结婚')
CHILD=P('本题是否有养育子女经历','您有过养育子女的经历吗？','亲生、收养或实际养育都可，以本人本题表述为准。','本人明确没有子女且无养育经历，关闭养育分支；不推断婚姻或生育原因。',r'没(?:有|过)?(?:子女|孩子|养育过孩子)|从未养育|没有养育经历')

C('SK01','出生与家乡',[
 E('E1','出生时间','time','您大概是哪一年出生的？','本人能确认的年、月、日或大致时期；保留精度与不确定限定。',period='birth'),
 E('E2','出生地点','place','您出生在哪个地方？','可辨认的本人出生地；地点精度不设行政区划门槛。必须本人明说出生关系，或真实定向问出生地时的回答；某地人、籍贯、家乡、住处均不能自动成为出生地。',period='birth',notes='只在出生关系成立时填本字段；同句先讲出生日期再讲某地人，也不把籍贯变成出生地。无法确认出生关系就保持 missing，不补猜。'),
 E('E3.place','地方样貌所对应的地点','place','您刚才说的这处地方，是哪里？','样貌已出现，能由原话关联到出生地、家乡或祖籍之一；不据此推断在此成长。',requirement='conditional',activation=K('E4'),notes='绑定同题 E4 的那项地方描述；允许紧接且唯一的地方指代。'),
 E('E3.period','地方样貌所属时期','period','您刚才说的这处地方的样子，是哪个时候的印象？','小时候、出生时期听家里讲、后来回乡等大致阶段足够。value须含实际时期表达，地点或环境描述本身不算时期。',requirement='conditional',activation=K('E4'),notes='必须绑定 E4 的相同地方描述；其他事件的日期不能代填。'),
 E('E4','出生地、家乡或祖籍的一项样貌','description','关于家乡过去的样子，您记得或听家里讲过些什么？','一项环境属性或生活描述已足够。本人明确说乡间、市区、乡村、山区等城乡/地理环境属性可作最小样貌；纯地名或仅迁居位置不算。不需住房、风俗、邻里故事全部齐备，不从本人住乡下推全家乡居民如何生活。',subjects=('self','family'),period='as_stated',vague=('普通','很普通','一般','还行'))
],optional=O('更细出生信息或地方片段'),notes='描述、地点身份、时期分开记录；只缺绑定时追问绑定，不重复索要描述。')
C('SK02','名字与期许',[
 E('E1','所谈名字的指代','name','您刚才说的是哪个名字？','只有名字或代词确实不清楚时才需要；没有完整姓名不妨碍已清楚的寓意。',requirement='conditional',activation={'if_ambiguous_referent':['E2','E3']},notes='只在多名、代词等影响理解时激活，不为收集姓名额外设门槛。'),
 E('E2','名字的来历或寓意','explanation','您知道这个名字为什么这样取吗？','本人所知的取名缘由、字义、纪念对象任一可用；不将字义当家人期许。',none=True,notes='本人名字的缘由，排除其他人的名字。'),
 E('E3','家人赋予名字的期许','expectation','家里有没有说过，取这个名字是盼着您将来怎样？','家人希望本人怎样，或明确没有寄托；没听家里说过是 unknown。本人自己取名只回答取名者，不代表家人没有期许。',none=True,subjects=('self','parents','family'),notes='家人的期许指向本人；不从名字字面含义、本人自取名或本人自己当年的计划推断。否定也须明确否定家人期许。')
],optional=O('取名者、取名经过或本人感受'))
C('SK03','原生家庭',[
 E('E1','主要共同生活者或照料者及关系','person_relation','您小时候主要跟谁一起生活？','跟父母长大、奶奶带大、住舅舅家或实际照料机构均可；不需姓名。同行、逃难或工作关系不自动证明主要共同生活/照料。',subjects=('self','family','parents','caregiver'),period='childhood',notes='本人是被照料者；只出现父母身份、职业或一次教育行为不证明主要共同生活。'),
 E('E2','父母或照料者实际劳动与家庭生活来源','livelihood','那时家里主要靠什么维持生活？','父母或实际照料者实际做什么或基本生活来源；工作、无薪家务照料、实际活动及机构供给均可，不需工资或正式职位，不需逐位亲属职业。',subjects=('parents','family','caregiver','self'),period='childhood',notes='保留实际活动原话，不把活动改写为有薪职位。只有党籍、信仰等身份仍不能代替实际做什么或生活来源；不强求工资收入。'),
 E('E3','兄弟姐妹情况','sibling_relation','您有兄弟姐妹吗？','有无及大致关系足够；独生子女为明确 none，不需精确人数或逐个资料。',none=True,subjects=('self','siblings','family'),period='childhood',notes='本人同辈亲属；同学、同事、朋友或师兄弟不能当兄弟姐妹。'),
 E('E4','家庭或实际照料环境相处氛围','atmosphere','小时候，家里人平时相处得怎么样？','一句有含义的相处描述；照料机构中已明确的相处氛围也可；生活条件过得去、家乡交通方便不等于相处氛围。',subjects=('self','parents','family','caregiver'),period='childhood',vague=('一般','还行'),notes='实际成长家庭/照料环境中人际相处；生活条件、职业、地理环境不能代填。本人终身孤单等个人情绪不自动描述成长家庭的人际氛围。只说家教严不自动等于家庭不和。')
],optional=O('更多亲属资料或家庭生活片段'))
C('SK04','家教与影响',[
 E('E1','家人怎样教育或管教本人','upbringing','从小到大，家里人一般怎样教导或管教您？','概括风格或一个具体教育行为即可；家人教本人一项技能、劝告鼓励或反对也属具体教育，不要求另有管教风格标签；家里不怎么管也是有效表达。',none=True,subjects=('parents','family','caregiver'),period='as_stated',vague=('正常教育','正常','一般'),notes='家人对本人的具体教育方向；本人对子女管教或家人自己的行为不能代填，不从一次行为扩大一生风格。'),
 E('E2.actor','管教者的所指','person_relation','您说的这种管教方式，是哪位家人这样做的？','仅管教陈述中施事不明且影响理解时澄清；家里一直管得严无需拆人。',subjects=('parents','family','caregiver'),period='as_stated',requirement='conditional',activation={'if_ambiguous_actor':['E1']},notes='只能绑定 E1 的教育行为。'),
 E('E2.period','管教方式所属阶段','period','您说的这种管教方式，是在哪个阶段？','仅多个阶段对应不清且影响理解时澄清；从小、小时候、现在等足够。',period='as_stated',requirement='conditional',activation={'if_ambiguous_period':['E1']},notes='只能绑定 E1 的教育行为，不取旁支事件年代。'),
 E('E3','本人认定的家教对性格的影响','personality_effect','您觉得这样的管教，对后来自己的性格有什么影响吗？','本人讲明对性格/通常处事方式的影响，或明确没影响；说不清是 unknown；不需正面影响。只是听从一次具体建议、完成事情、选择职业或学会技能，没有自述性格作用，不能填本项。',none=True,vague=('影响很大','影响大','有影响'),notes='本人对自己性格的因果理解；不能由服从建议、事件结果、事业选择或家人的性格替本人推断自己的性格影响。')
],optional=O('具体管教经历或现在的看法'))
C('SK05','性格底色',[
 E('E1','本人认可的性格描述','self_trait','回头看，您会怎么形容自己的性格？','至少一个可理解的本人自我描述短词/短句；无需原因、例子或故事。',notes='本人通常性格/相应阶段性格；某次不害怕、爱好或评价讲述方式不自动是性格。'),
 E('R1','他人对本人的性格评价','reported_trait','', '本人转述的他人评价，单独不能完成本题。',subjects=('self','other'),requirement='input',activation={'never_ask':True},notes='报告评价的人与被评价的本人区分。'),
 E('E2','本人是否认同他人评价','stance','您自己也这样看自己吗？','认同、不认同、部分认同均可；只有认同/部分认同并有清楚评价可支持 E1。',requirement='conditional',activation={'reported_without_self':['R1','E1']},notes='必须针对本题 R1 的同一条评价；反对他评不能替代本人自我描述。'),
 E('E3','自选性格词的含义或范围','clarification','您说的这个性格特点，对您来说是什么样的？','只在原词确实无法理解时澄清；内向、慢热、执着等普通词无需定义。',requirement='conditional',activation={'if_ambiguous_meaning':['E1']},notes='只解释本人使用的原词，不由模型增设词义门槛。')
],optional=O('本人愿意讲的性格例子或形成过程'))
C('SK06','人生关键词',[
 E('E1','本人选择的人生概括','life_summary','想到自己这一生，您最先想到什么词，或者一句什么话？','至少一个本人用来概括一生的词或短句；三个是邀请，不凑数。',notes='须本人选择概括关系；一般价值观、经历或感谢采访者不自动是关键词。'),
 E('E2','所选概括的对应解释','explanation','您为什么会用这个词来形容这一生？','至少一项本人解释与一个已选概括对应；含义、理由或经历均可，不需完整故事。',requirement='conditional',activation=K('E1'),link={'field_id':'E1','relation':'explains','minimum':1},notes='指向 E1 已存在的本人原词；不能以重复关键词充当解释。'),
 E('E3','概括与解释的对应澄清','clarification','您刚才说的这一点，主要是在解释哪个词？','仅已有解释但对应多义且影响记录时澄清；不能无依据把解释绑定所有词。',requirement='conditional',activation={'if_ambiguous_link':['E2']},notes='仅澄清 E1 与 E2 已有内容的关系。')
],optional=O('更多关键词及其解释'),notes='E1未知/拒绝/推迟则关闭解释分支，有限收口；至少一组已选概括及解释可用才资料足够。')

C('CH01','最早记忆',[
 E('E1','本人记得的一项早年记忆','memory','您最早记得的一件事是什么？','一项可辨认的本人早年记忆；不强求证实最早、年龄或准确日期。',none=True,period='childhood'),
 E('E2','那项记忆中发生的事情','event','那件事里，当时发生了什么？','能理解那项记忆发生了什么；一句经过即可，不需完整故事结构。',requirement='conditional',activation=K('E1'),period='childhood',notes='对应 E1 的同一段记忆，不挪用另一件事。')
],optional=O('本人愿意补充的记忆细节'))
C('CH02','童年生活条件',[
 E('E1','童年家庭的生活条件','condition','小时候，家里的生活条件怎么样？','贫富、吃穿、住房、生活供给任一可理解概括；不要求收入数字。',subjects=('self','family'),period='childhood'),
 E('E2','童年日常生活状态','daily_life','那时候，您平常一天大致怎么过？','一句能理解的日常活动或生活安排；可与条件共用有依据的原话。',subjects=('self','family'),period='childhood')
],optional=O('童年衣食住行的更多片段'))
C('CH03','亲人的疼爱与影响',[
 E('E1','童年疼爱本人的亲人及关系','person_relation','小时候，哪位亲人最疼爱您？','至少一位本人认定疼爱自己的亲人及关系；可明确没有特别的人。',none=True,subjects=('family','caregiver','parents'),period='childhood'),
 E('E2','童年影响深的亲人及关系','person_relation','童年时，哪位亲人对您的影响比较深？','至少一位本人认定影响深的亲人；可与 E1 同人但须有本人依据，不要求排序。',none=True,subjects=('family','caregiver','parents'),period='childhood'),
 E('E3','与所述亲人有关的难忘小事','event','关于刚才说的这位亲人，有什么难忘的小事？','一件本人记得的相关小事足够；没有具体小事可明确 none。',none=True,requirement='conditional',activation={'any_known':['E1','E2']},subjects=('self','family','caregiver'),period='childhood',notes='与 E1 或 E2 的至少一位亲人关联，不强迫每人一个故事。')
],optional=O('亲人带来的感受或更多小事'))
C('CH04','童年喜好与梦想',[
 E('E1','童年喜欢做的事','activity','小时候，您最喜欢做什么事？','一个活动或习惯即可；不要求比较最喜欢。',none=True,period='childhood'),
 E('E2','童年爱好或小梦想','wish','小时候，有什么爱好或者小梦想吗？','爱好或梦想任一即可；同一原话可同时表达喜欢做的事与爱好。',none=True,period='childhood')
],optional=O('喜好或梦想的由来与片段'))
C('CH05','童年印象深刻的事',[
 E('E1','童年一项印象深的困难、委屈或开心的事','event','童年有什么让您印象很深的事吗？','至少一件能理解发生了什么的童年事，困难/委屈/开心任一；明确没有也可。',none=True,period='childhood')
],optional=O('本人自愿补充的经过或感受'))
C('CH06','邻里亲友氛围与温暖',[
 E('E1','童年邻里亲友的相处氛围','atmosphere','小时候，邻里或亲友之间相处得怎么样？','本人对邻里/亲友相处的可理解描述；不必同时覆盖两类人。',subjects=('self','neighbors','relatives'),period='childhood',notes='亲友包括亲属和姻亲；共同居住或属于同一大家庭不取消亲友身份。原话已说明这些人的实际相处即可，不因家庭内部而排除，也不追加邻里一类。仅有亲属身份、同住或家境本身，不能替代相处氛围。'),
 E('E2','至今难忘的人情温暖','memory','有没有至今还记得的一次人情温暖？','一个关照/帮助等片段，或明确没有；不强求温暖的正面经历。',none=True,subjects=('self','neighbors','relatives'),period='childhood')
],optional=O('相关人物与往来的更多细节'))
C('CH07','童年经历与处世观念',[
 E('E1','本人认为有影响的一项童年经历','event','童年哪件经历影响了您后来的待人处事？','本人选出的一项童年经历即可；明确没觉得有也可。',none=True,period='childhood'),
 E('E2','本人认定对处事方式或观念的影响','effect','您觉得这件经历后来怎样影响了您？','本人说出的具体影响或明确没有影响；不由模型推出三观。',none=True,requirement='conditional',activation=K('E1'),notes='必须指向 E1 的同一项童年经历与本人的后来变化。')
],optional=O('本人愿意补充的后续例子'))

C('GR01','入学与求学历程',[
 E('E1','开始上学的大致年纪或时期','time','您大概多大时开始上学的？','本人开始上学时的大致年龄、早晚或可定位人生/历史时期足够；明确从未上学记 none。仅说刚开始上学顺利、后来中断是在评价过程，没有回答何时开始，不能填本项；不逼报具体年龄。',none=True,period='school_years'),
 E('E2','求学过程及是否顺利','school_path','您的求学过程大致顺利吗？','大致读书过程或顺利/不顺利的可理解描述，不需逐校逐年。',requirement='conditional',activation=U('E1'),period='school_years'),
 E('E3','辍学、转学等特殊经历','event','求学期间，有过辍学、转学这类特殊经历吗？','有则可辨认是何种经历，或明确没有；不强迫同时有辍学和转学。',none=True,requirement='conditional',activation=U('E1'),period='school_years')
],optional=O('学校名称、具体年份或更多求学片段'),notes='E1明确没有上过学时关闭 E2/E3，有限收口而非取得求学资料。')
C('GR02','学生性格与成绩',[
 E('E1','本人学生时代的性格','self_trait','学生时代，您会怎么形容自己的性格？','一个本人认可的性格词或短句即可，不在题干例子中强制选择。',period='school_years'),
 E('E2','本人学生时代的成绩水平','evaluation','当时您的学习成绩大致处于什么水平？','大致水平或自己的描述足够；不要求分数、名次、学校。',period='school_years')
],optional=O('学习习惯或校园片段'),premise=SCHOOL)
C('GR03','老师同学的影响',[
 E('E1','影响本人的老师或同学','person_relation','求学时，有没有对您影响比较大的老师或同学？','一个老师或同学及可辨认关系，或明确没有；不要求两类都出现或完整姓名。',none=True,subjects=('teacher','classmate'),period='school_years'),
 E('E2','本人认定他们带来的改变','effect','您觉得这位老师或同学带给您什么改变？','针对至少一人的本人改变或明确没改变；不推断积极结局。',none=True,requirement='conditional',activation=K('E1'),period='school_years',notes='本人是受影响者，老师/同学是影响来源，不能倒置。')
],optional=O('相关师生或同窗片段'),premise=SCHOOL)
C('GR04','少年的烦恼与快乐',[
 E('E1','少年时期的烦恼','feeling','少年时，最让您烦恼的是什么？','一项可理解烦恼或明确没有特别烦恼；不要求比较最大。',none=True,period='school_years'),
 E('E2','少年时期的快乐','feeling','少年时，最让您快乐的是什么？','一项可理解快乐或明确没有特别快乐；不强求正面故事。',none=True,period='school_years')
],optional=O('本人想展开的少年日常或经历'))
C('GR05','家庭条件与求学生活',[
 E('E1','当时的家庭条件','condition','求学那时候，家里的条件怎么样？','本人当时家庭条件的可理解概括或真实安排，如家庭的生活来源、经营规模、照料与劳动安排；不必明说贫穷/富裕，也不必收入数字。',subjects=('self','family'),period='school_years'),
 E('E2','家庭条件对求学或生活的影响','effect','您觉得当时的家庭条件，对求学或生活有什么影响？','本人已明说的求学/生活安排或影响、或明确没影响；如为家里劳动后才能上课、写作业时间受挤压等事实本身即可，不强求另说“这影响我”；两方面无需强凑。',none=True,period='school_years',notes='须是家庭条件对本人求学/生活的事实关系，不由贫富自动推断未说出的影响。原话已经有劳动与上学的关系时，不只存可选O1而漏掉必要项。')
],optional=O('本人自愿补充的具体家庭生活片段'))
C('GR06','青春期迷茫与叛逆',[
 E('E1','青春期迷茫或叛逆阶段的情况','experience','青春期有没有一段迷茫或叛逆的时候？','一项可理解的阶段状态，或明确没有；不需确切年龄或二者都有。',none=True,period='school_years'),
 E('E2','本人怎样度过那一阶段','response','那段时候，您是怎样一步步过来的？','应对、持续困惑、没特别办法或仍未度过都可；不要求成功克服。',none=True,requirement='conditional',activation=K('E1'),period='school_years',notes='与 E1 同一阶段，不把未来结果强套为当时应对。')
],optional=O('当时得到的帮助或更多想法'))
C('GR07','离校时对未来的憧憬',[
 E('E1','离校时的憧憬或规划','expectation','离开校园时，您对未来有过什么想法或打算？','愿景或具体打算任一可用；明确当时没想过/没规划也是回答，不要求实现。',none=True,period='school_years')
],optional=O('憧憬与后来经历的差别'),premise=SCHOOL)

C('WK01','第一份工作与选择',[
 E('E1','本人第一份工作或最初事业','work','您最初做的工作或事业是什么？','本人能辨认的最初工作/劳动/事业；不以是否离校为前提，不需单位和年龄。',none=True,period='youth'),
 E('E2','本人选择这条路的缘由','explanation','当时为什么会选择这条路？','本人讲的原因、被安排/没有选择或现实条件均可。本人用因果叙述交代不能继续原来生活/学习而紧接开始最初工作时，该明确促成的现实处境也是入行原因，不要求另说职业理想；仅按时间并列的事不自动建立因果。后面转行/另一份工作的原因不能填到第一份工作。',none=True,requirement='conditional',activation=K('E1'),period='youth',link={'field_id':'E1','relation':'explains_choice','minimum':1,'require_same_object_evidence':True},notes='只对应 E1 的第一份工作/事业。关系证据必须能连到同一工作，真实定向问本项的短答可绑定，泛问“这个决定”须核对实际指的是哪份工作。')
],optional=O('工作起步时的更多经历'))
C('WK02','初入社会的难题',[
 E('E1','初入社会的一项难题或挫折','event','刚步入社会时，您遇到过什么难题或挫折？','一项能理解的早期困难即可；不强迫证明第一或同时讲两件。',none=True,period='youth'),
 E('E2','面对这项难题的应对或结果','response','面对这件事，当时您是怎样应对的？','应对、未能克服、不了了之或仍受影响均可；无需积极结局。',none=True,requirement='conditional',activation=K('E1'),period='youth',notes='与 E1 同一项难题；不强迫声称克服。')
],optional=O('困难中的帮助或本人感受'))
C('WK03','青年打拼的忙碌',[
 E('E1','本人对青年打拼辛苦程度的看法','evaluation','您觉得青年时期打拼辛苦吗？','辛苦、不辛苦或复杂看法均可；一句本人表达足够。',period='youth'),
 E('E2','本人记得的一段忙碌奔波生活','description','青年时，您记得最忙碌奔波的日子是怎样的？','一段可理解的工作/生活状态，或明确没有特别忙碌的阶段；不需起止日期。',none=True,period='youth')
],optional=O('本人愿意讲的奔波片段'))
C('WK04','第一次小成就',[
 E('E1','工作事业中早期的一项小成就或骄傲','achievement','工作起步时，有什么让您觉得有点成就或骄傲的事吗？','本人认可的一项早期成就/小骄傲，或明确没有；不要求外部奖项、收入或排名。',none=True,period='youth')
],optional=O('成就发生的经过或当时感受'))
C('WK05','青年关键选择',[
 E('E1','本人认定改变方向的青年选择','choice','青年时，有没有一项改变您人生走向的选择？','一项本人认为关键的选择并能理解选了什么；或明确没有，不由模型夸大普通行动。',none=True,period='youth')
],optional=O('选择缘由、经过或后来的影响'))
C('WK06','交友原则与情谊',[
 E('E1','青年时期交友或待人原则','view','青年时，您交朋友或待人处事有什么原则？','一个本人表达的原则或明确没有固定原则；不要求格言或例子。',none=True,period='youth'),
 E('E2','青年时期珍贵的情谊','relationship','那时候，您收获过什么珍贵的情谊？','一段本人认可的情谊或明确没有；可不提供姓名或完整故事。',none=True,subjects=('self','friend','other'),period='youth')
],optional=O('朋友间本人想讲的一次往来'))
C('WK07','中年忙碌与压力',[
 E('E1','本人对中年忙碌压力程度的评价','evaluation','您觉得中年是自己最忙碌、压力最大的阶段吗？','是、不是、某些方面是等本人判断；不必同其他时期量化比较。',period='middle_age'),
 E('E2','中年主要压力来源','explanation','中年时，您的主要压力来自哪里？','本人认定的一项来源或明确没有压力；题干事业家庭养老育儿只是例子。',none=True,period='middle_age')
],optional=O('本人愿意补充的中年生活细节'))
C('WK08','长期深耕的工作',[
 E('E1','本人最专注坚持的一份事业或工作','work','这一生，您最专注坚持的是哪份工作或事业？','本人选出的一份事业/劳动/工作，或明确没有；不强求终身只有一份。',none=True),
 E('E2','从事这份工作的时长','duration','这份工作，您大致坚持了多久？','几年、几十年、很长一段等本人能确认的粗略时长；不强求精确年份。',requirement='conditional',activation=K('E1'),link={'field_id':'E1','require_same_object_evidence':True},notes='只计算 E1 同一份工作，不把全人生工龄混入。'),
 E('E3','这份工作的收获','gain','做这份工作，您觉得有哪些收获？','一项本人认定收获或明确没有；金钱、技能、关系等任意自述，不指定成功。',none=True,requirement='conditional',activation=K('E1'),notes='对应 E1 的工作。'),
 E('E4','这份工作的感悟','view','这些年做这份工作，您有什么感悟？','一句本人理解或明确没有特别感悟；不要求正面结论。',none=True,requirement='conditional',activation=K('E1'),notes='对应 E1 的工作，不由收获自动推出感悟。')
],optional=O('工作方法、变化或更多片段'))
C('WK09','低谷挫折变故',[
 E('E1','本人认定的一项低谷、挫折或变故','event','事业或生活中，有没有一段让您觉得是低谷的经历？','至少一项能理解的本人经历，或明确没有；不比较最大，不要求化解、感悟或积极结局。',none=True)
],optional=O('本人愿意补充的经过或当时状态'))
C('WK10','困难中的支撑',[
 E('E1','艰难时期支撑本人的因素','support','难熬的时候，是什么支撑着您？','本人认定的一项支撑、没有支撑或只是熬着；须能理解它属于本人艰难时刻。',none=True,notes='不读取 WK09；不强迫重讲完整低谷经过，也不假定已经坚持成功。')
],optional=O('本人愿意讲的支撑片段'),premise=P('本题是否有难熬经历','您有过觉得特别难熬的一段日子吗？','本人明确有艰难经历，或本题已经讲到困难中的支撑。','本人明确没有此类日子，可关闭支撑分支。',r'没(?:有|经历过)(?:什么)?(?:难熬|困难|艰难|低谷)(?:的)?(?:日子|时期|经历)?'))
C('WK11','中年的收获与成长',[
 E('E1','本人认定的中年收获','gain','中年这段日子，您觉得最大的收获是什么？','一项本人选出的收获或明确没有；不需证明最大。',none=True,period='middle_age'),
 E('E2','本人认定的中年成长','change','中年阶段，您觉得自己有什么成长？','本人认定的一点变化/成长或明确没有；本人对照过去与现在的态度、处事方式或适应新阶段的做法也可，不要求使用“成长”二字或必须更积极。不从成绩、泛泛自评替本人推出成长。',none=True,period='middle_age')
],optional=O('体现收获或成长的片段'))
C('WK12','责任与自我',[
 E('E1','本人实际承担的家庭责任','responsibility','那时候，您实际需要承担哪些家庭责任？','本人需要承担的照料/养老/育儿等至少一项，或明确没有；不假定同时有老人和子女。原题未限定中年，任何本人实际承担阶段均可，年龄不成为排除条件。',none=True,subjects=('self','family'),period='as_stated'),
 E('E2','平衡责任与自己的方式或困难','response','承担这些责任时，您怎样兼顾自己的需要？','本人做法、取舍、没顾上自己或未能平衡都可；不要求成功兼顾，不限中年。',none=True,requirement='conditional',activation=K('E1'),period='as_stated',notes='对应 E1 的真实责任与实际阶段，不增加未披露的子女或老人，不从原图年龄说明排除真实经历。')
],optional=O('本人愿意谈的照料或取舍片段'))
C('WK13','引以为傲的工作成果',[
 E('E1','本人最引以为傲的一项工作成绩或成果','achievement','这一生工作打拼，有什么成果让您最引以为傲？','本人认可的一项成果或明确没有；普通劳动成果同样可用，不要求奖项或量化收入。',none=True)
],optional=O('成果的过程、意义或更多成果'))

C('FM01','伴侣的相识相伴',[
 E('E1','与伴侣相识的方式','relationship_origin','您和伴侣最初是怎么认识的？','本人和现任/过去伴侣如何认识；不需日期、年龄、婚礼或在婚状态。',subjects=('self','partner'),period='adulthood'),
 E('E2','与伴侣相知的过程','relationship','后来，您们是怎样慢慢了解彼此的？','能理解的熟悉/了解过程；一件事或简短概括足够，不要求恋爱模式。',subjects=('self','partner'),period='adulthood',notes='知道/了解对方某个习惯是已存在的了解状态，不自动说明怎样逐渐熟悉；在已知基础上关心或帮忙也不自动成为相知过程。没有婚前时间限制；婚后真正增加了解的过程同样可用。'),
 E('E3','与伴侣相伴的生活','relationship','您们后来相伴的生活是怎样的？','本人描述的相伴方式或变化；分离、复杂感受也可以，不预设白头偕老。',subjects=('self','partner'),period='adulthood'),
 E('E4','与伴侣一项难忘的相处经历','memory','和伴侣相处，有什么最难忘的一件事？','一件可理解的相处记忆，或明确没有特别故事；不要求正面结局。',none=True,subjects=('self','partner'),period='adulthood')
],optional=O('更多相处细节或本人感受'),premise=PARTNER)
C('FM02','初建家庭的生活与打拼',[
 E('E1','刚组建家庭时的生活条件','condition','刚组建家庭时，您们的生活条件怎么样？','本人初建伴侣家庭时的生活供给/条件；不需收入或房产数字。',subjects=('self','partner','family'),period='adulthood'),
 E('E2','夫妻共同生活打拼的做法','response','那时候，您们两个人是怎样一起维持生活、打拼的？','具体分工或共同努力方式；一人工作、一人照料、未能携手也按本人表述记录。',none=True,subjects=('self','partner'),period='adulthood')
],optional=O('初建家庭的生活片段'),premise=MARRIAGE)
C('FM03','婚姻磨合与相守',[
 E('E1','婚姻磨合、争执或难熬时刻','experience','婚姻中，有没有让您觉得难磨合或难熬的时刻？','一项可理解经历，或明确没有；三类任一即可，不要求隐私细节。',none=True,subjects=('self','partner'),period='adulthood'),
 E('E2','面对婚姻困难的相处与应对','response','面对那样的时刻，您们后来怎样相处、应对？','包容、分开、未解决、仍复杂等本人事实；不强迫原谅、和好或继续相守。',none=True,requirement='conditional',activation=K('E1'),subjects=('self','partner'),period='adulthood',notes='对应 E1 的同一关系/困难，不默认积极结局。')
],optional=O('本人愿意补充的婚姻感受'),premise=MARRIAGE)
C('FM04','养育的辛苦与欣慰',[
 E('E1','养育中辛苦的一刻或状态','experience','养育子女时，您最觉得辛苦的是什么时候？','一项本人养育辛苦的瞬间/状态，或明确没什么辛苦；不需子女姓名年龄。',none=True,subjects=('self','children'),period='adulthood'),
 E('E2','养育中欣慰的一刻或状态','experience','养育子女时，有什么让您觉得欣慰的时刻？','一项本人欣慰经历，或明确没有；不因原题而强求正面体验。',none=True,subjects=('self','children'),period='adulthood')
],optional=O('本人愿意展开的养育片段'),premise=CHILD)
C('FM05','对子女的教育与期望',[
 E('E1','本人对子女的教育理念','view','对子女的教育，您最看重什么？','一句本人理念、做法或明确没有固定理念；不收成父母当年对本人的教育。',none=True,subjects=('self','children'),period='adulthood',notes='教育者是本人，教育对象是本人实际养育的子女，方向与 SK04 相反。'),
 E('E2','本人希望子女成为什么样的人','person_expectation','您希望孩子以后成为什么样的人？','本人对孩子品格、人生或生活方式的期望，或明确没设期望；一次考试成绩、名次等单项学习要求不是其未来人格/人生期望，不能由教育做法自动代填。',none=True,subjects=('self','children'),period='adulthood')
],optional=O('本人愿意补充的教育片段'),premise=CHILD)
C('FM06','家庭和睦的关键',[
 E('E1','本人认为维系家庭和睦的关键','view','您觉得，维系家庭和睦最重要的是什么？','一句本人观点、对自己家庭为何团结和睦的本人解释，或明确无固定原则；不要求格言式标签，也不要求采访者恰好问本题。没想过为 unknown，不是 none；家庭可指本人实际家庭或兄弟姐妹，不强制婚育。',none=True,subjects=('self','family'))
],optional=O('本人自愿分享的家庭相处例子'))
C('FM07','家人的意义',[
 E('E1','本人怎样理解家人的意义','view','对您来说，家人在这一生中意味着什么？','软肋、铠甲、两者都有、都不是或自己的表述均可；不强制二选一。须是本人对家人意义、依靠或牵挂等的自述判断；仅有亲人动作或事件悲伤不替本人总结意义。',none=True,subjects=('self','family')),
 E('E2','让本人感到家人意义的一刻','felt_meaning_experience','有没有一个时刻，让您深切感到家人的意义？','一项由本人认定与家人意义有关的时刻/生活状态，或明确没有；只说家人帮助的动作、悲伤或记忆深刻，不能由模型推断本人感到了家人的意义，不要求重大事件或温暖结局。',none=True,subjects=('self','family'))
],optional=O('本人愿意补充的家人片段或感受'))

C('LT01','现在的生活',[
 E('E1','本人当下的生活状态','description','您现在的日子大致是怎样过的？','本人目前生活状态或日常安排的可理解描述，不强求退休或健康信息。',period='now'),
 E('E2','本人目前喜欢的生活方式','preference','现在您最喜欢怎样安排自己的日常生活？','一种本人喜欢的生活方式，或明确没有特别偏好；不强求爱好清单。',none=True,period='now')
],optional=O('本人愿意展开的一天或近期片段'))
C('LT02','忙碌之后的心态',[
 E('E1','本人相较忙碌时期的心态变化','change','和以前忙碌打拼的时候相比，您现在的心态有什么变化？','本人清楚表达的一点变化、没有变化或仍在忙碌；不强制退休、清闲或变好。',none=True,period='now',notes='比较须来自本人；现在仍忙碌不是失败，可记录无该阶段变化。')
],optional=O('心态变化的缘由或片段'))
C('LT03','对一生的总体评价',[
 E('E1','本人对一生的总体评价','life_evaluation','回头看，您会怎样评价自己这一生？','一句本人总体评价；不需在圆满、无悔、尽力、知足中选择，不要求解释。')
],optional=O('本人愿意补充的评价缘由'))
C('LT04','给晚辈的忠告',[
 E('E1','本人想告诉晚辈的人生话语','message','您想对晚辈说一句什么人生道理或提醒？','一句本人忠告/处世道理即可，或明确没有；不要求确有子女孙辈、例子或故事。',none=True,subjects=('self','younger_generation'))
],optional=O('本人愿意解释的缘由或适用场景'))
C('LT05','希望后人记住什么',[
 E('E1','本人希望后人记住的品格或自我形象','wish','您希望后人记住您什么样的品格？','至少一点本人愿被记住的品质或自我形象，或明确不希望/没有特别想法。在真实“希望后人记住我什么”的问答下，以如何做事/待人、服务目标描述自己也足够，不必强贴负责善良等标签。',none=True,notes='必须有本人自选的希望被记住关联；旁支行为、普通工作目标不能自动成为希望后人记住的品格。'),
 E('E2','本人希望后人记住的故事','wish','有没有一件您希望后人记住的故事？','一项本人选出的故事/经历，能辨认即可；或明确没有，不强求完整讲完。泛泛工作职责、服务目标或通常做事方式不是一项具体故事。',none=True)
],optional=O('本人愿意补充的故事细节或原因'))
C('LT06','未来的心愿',[
 E('E1','本人对未来的心愿或期许','wish','对于以后的日子，您最盼望什么？','至少一个本人心愿/期许或明确没有特别心愿；不需计划、期限或正面措辞。',none=True,period='now')
],optional=O('本人愿意补充的打算或缘由'))

C('RV01','认为正确的选择',[
 E('E1','本人认为正确的一项人生选择','choice','回头看，有哪项选择让您觉得自己选对了？','一项本人认定正确且能理解选了什么的选择，或明确没有；不凑几个，不强制原因。',none=True)
],optional=O('更多选择或选择后的经历'))
C('RV02','遗憾与重来一次',[
 E('E1','本人耿耿于怀的一项遗憾','experience','这一生，有没有一件让您放不下的遗憾？','至少一项本人认定遗憾，或明确没有；不要求释怀。',none=True),
 E('E2','若重来一次的本人选择','hypothetical','如果这件事能重来，您会怎样选择？','本人假设选择或不改变即可；明确没想过/不愿假设才记相应终态。已经触及重选但表达断裂、所指不清时记 ambiguous，不能自动记 unknown/declined；完全未提留 missing。不推定会补救。',none=True,requirement='conditional',activation=K('E1'),notes='针对 E1 的同一遗憾；不把事实改写成真实发生的结果，也不把难以理解的表达等同本人明确不知道或拒绝。')
],optional=O('本人愿意展开的遗憾经过'))
C('RV03','误会与释怀',[
 E('E1','误会别人或被人误会的一项经历','event','有没有一次误会别人、或者被人误会的经历？','一个方向的一项经历足够，或明确没有；谁误会谁要能理解，不需双方都经历。',none=True,subjects=('self','other'),notes='本人是误会者或被误会者必须明确。'),
 E('E2','本人后来是否释怀的状态','resolution_state','对于这件误会，您后来怎么看，还放在心上吗？','本人表达是否仍在意、放不放得下、释怀/未释怀/部分释怀等状态即可。只说学到教训、以后应如何做人，不能代填是否释怀；不要求和解。',requirement='conditional',activation=K('E1'),notes='对应 E1 同一误会；教训或处世原则不是本人是否仍在意的状态，不预设已原谅或关系恢复。')
],optional=O('误会经过或后续往来'))
C('RV04','吃亏与学到的事',[
 E('E1','本人一项吃亏或踩坑的经历','event','人生路上，有什么让您觉得吃过亏或踩过坑的经历？','一项能理解的本人经历，或明确没有；不要求证明最大。',none=True),
 E('E2','本人认为从中学到的事','view','这件事让您学到了什么？','一点本人理解或明确没学到什么；不强求积极教训。',none=True,requirement='conditional',activation=K('E1'),notes='对应 E1 的经历，不由模型生成教训。')
],optional=O('本人愿意补充的过程或代价'))
C('RV05','放弃的梦想与机会',[
 E('E1','放弃的梦想或错过的机会','experience','有没有一个放弃过的梦想、或者错过的机会？','两类任一的一项可理解内容，或明确没有；不强迫本人承认遗憾。',none=True),
 E('E2','本人现在对这项事的看法','view','现在回头看，您怎样看待这件事？','本人当前看法，遗憾、接受、复杂等均可；不要求释怀。',requirement='conditional',activation=K('E1'),period='now',notes='对应 E1 的同一梦想或机会。')
],optional=O('当时缘由或后来变化'))
C('RV06','感谢与亏欠的人',[
 E('E1','本人最感谢的人及关系','person_relation','一路走来，您最想感谢谁？','至少一位可辨认的人/群体及关系，或明确没有特别的人；不必全名或缘由。',none=True,subjects=('self','other','family')),
 E('E2','本人觉得亏欠的人及关系','person_relation','有没有哪位人，让您觉得有所亏欠？','至少一位可辨认的人/群体及关系，或明确没有；不推断愧疚、不要求补偿。',none=True,subjects=('self','other','family'))
],optional=O('感谢或亏欠的缘由与片段'))
C('RV07','重要的品质',[
 E('E1','本人认为人生重要的品质','view','您觉得，人这一生什么品质最重要？','至少一种本人认为重要的品质即可；三个是邀请，不凑齐数量，不要求例子。',none=True)
],optional=O('更多品质或本人解释'))
C('RV08','朋友与计较',[
 E('E1','本人认为值得深交的朋友特质','view','您觉得什么样的朋友值得深交？','一句可理解的本人标准或明确没有固定标准；不要求实际有这类朋友。',none=True),
 E('E2','本人认为不必计较的事情','view','在您看来，什么样的事不必计较？','一种本人认为可不计较的事情/原则，或明确没有；不要求无条件宽容。',none=True)
],optional=O('本人愿意分享的处世例子'))
C('RV09','吃苦努力运气',[
 E('E1','本人对吃苦的理解','view','您怎样理解人生里的“吃苦”？','一句本人对吃苦的理解/态度，或明确没有特别看法；不需故事。',none=True),
 E('E2','本人对努力的理解','view','您怎样理解人生里的“努力”？','一句本人对努力的理解/态度，或明确没有特别看法；不由吃苦观点代填。',none=True),
 E('E3','本人对运气的理解','view','您怎样理解人生里的“运气”？','一句本人对运气的理解/态度，或明确没有特别看法；不强求承认运气重要。',none=True)
],optional=O('本人愿意举的例子或更多看法'))
C('RV10','最看重什么及原因',[
 E('E1','本人对家庭事业健康的重要性判断','view','家庭幸福、事业成功、身体健康，您最看重哪一项？','选择一项、多项并重、无法排序或自己的价值判断均可；不强迫三选一。',none=True),
 E('E2','本人作此判断的原因','explanation','您为什么会这样看？','本人对 E1 判断的一句解释即可；不需故事，不由常识代填。',requirement='conditional',activation=K('E1'),notes='对应 E1 的本人的重要性判断。')
],optional=O('本人愿意补充的相关经历'))
C('RV11','人生的通透',[
 E('E1','本人最大的人生领悟','view','走到今天，您对人生最想明白的一点是什么？','一句本人领悟或明确没有特别领悟；还没想明白为 unknown，不是 none；不要求积极、成熟或完整哲理。',none=True)
],optional=O('本人愿意解释的缘由或经历'))
C('RV12','最珍贵的财富',[
 E('E1','本人认为人生最珍贵的财富','view','您觉得，人生最珍贵的财富是什么？','一句本人认定即可；不受金钱阅历家人本心例子限制、不必说明理由。',none=True)
],optional=O('本人愿意补充的解释'))
C('RV13','感恩的事',[
 E('E1','本人一项感恩的事','experience','这一生，您最想感恩的一件事是什么？','至少一件本人认定感恩的事即可；三个是邀请，不凑数，不强求完整故事。',none=True)
],optional=O('第二第三件或更多感恩的事'))
C('RV14','一句话总结',[
 E('E1','本人总结人生的一句话','life_summary','如果用一句话说自己这一生，您会怎么说？','一句可理解的本人总结即可；不限制字数或文采，不要求理由。')
],optional=O('本人愿意补充的解释'))
C('RV15','是否活得值得',[
 E('E1','本人对一生是否值得的判断','life_evaluation','您觉得，自己这一生活得值得吗？','值得、不值得、复杂/难说等本人可理解立场；说不清则 unknown，不强求正面结论。')
],optional=O('本人愿意说的原因或补充'))
C('RV16','留给后人的心里话',[
 E('E1','本人想补充留下的心里话','message','还有什么您想留给岁月、留给后人的话？','一段本人心里话即可，或明确没有补充；不要求新故事、意义或完整结构。',none=True)
],optional=O('本人自愿继续补充的话'))

order = [f'SK{i:02d}' for i in range(1,7)]+[f'CH{i:02d}' for i in range(1,8)]+[f'GR{i:02d}' for i in range(1,8)]+[f'WK{i:02d}' for i in range(1,7)]+[f'FM{i:02d}' for i in range(1,8)]+[f'WK{i:02d}' for i in range(7,14)]+[f'RV{i:02d}' for i in range(1,13)]+[f'LT{i:02d}' for i in range(1,7)]+[f'RV{i:02d}' for i in range(13,17)]
assert len(order)==len(set(order))==len(contracts)==62
for qid in ['WK03','WK05']:
    for f in contracts[qid]['elements']:
        if f['requirement']=='required':
            f['scope']['stage_binding_required']='youth'
            f['scope']['object_relation']+=' 青年阶段须由本题实际原问或本人原话绑定，离线映射题号不证明阶段；仅婚后创业等无阶段锚的事实先保留，澄清属于人生哪个时候，不重索过程。'
for f in contracts['LT01']['elements']:
    if f['requirement']=='required':f['scope']['stage_binding_required']='now'
next(f for f in contracts['SK03']['elements'] if f['id']=='SK03-E3')['literal_none_patterns']=[r'(?:我|本人)(?:从来|一直|就是|确实|本来)?(?:没有|无)(?:亲)?兄弟(?:姐妹|姐弟|姊妹)?',r'(?:我是|我(?:是)?个|我为)(?:独生子女|独生子|独生女)']
for f in contracts['RV06']['elements']:
    if f['id'] in ['RV06-E1','RV06-E2']:
        f['scope']['subjects']=['self']
        f['scope']['object_roles']=['parents','family','caregiver','friend','teacher','classmate','partner','children','relatives','other']
        f['scope']['object_relation']='态度持有人是本人self；感谢或亏欠指向的人是对象，可为父母等。field.value记录所指的人或群体，不能把态度持有人与对象角色混为一项subject。'
        f['notes']+=' 感谢/亏欠态度的持有人为self；父母等放object/object_role及逐字对象关系证据，不写成subject=parents。'
semantic_roles=json.loads((HERE/'semantic-roles.json').read_text())
for q in contracts.values():
    for f in q['elements']:
        f['semantic_role']=semantic_roles.get(f['id'],f['type'])
        if f['type'] in ('time','duration'):
            f['answer_format']={'known_required_attributes':['precision'],'placement':'precision is a top-level field attribute; no time wrapper','precision':['exact','approximate','as_stated'] if f['type']=='duration' else ['day','month','year','decade','relative','approximate','as_stated']}
        elif f['type']=='stance':
            f['answer_format']={'known_required_attributes':['stance'],'stance':['agree','disagree','partial']}
        f.setdefault('answer_format', {})['value_type']='string_or_string_array' if f['type'] in ('life_summary','explanation') else 'string'
        if f['type']=='life_summary':f['notes']+=' 回答已把概括词与含义/理由连在一起时，分别保留可辨认原词和对应解释；不把解释整段塞入父项，再用原词重述冒充子项解释。只有不可再拆的自选短句时仍可按原意保留，不强造原因。'
        if f['type']=='choice':f['notes']+=' 保留已经选了什么/决定不做什么的原话；不喜欢原状、想要未来的愿望或选择理由不能单独代替选择本身。不得由采访者题干补出行动。'
        if f['type']=='gain':f['notes']='本人明确叙述自己获得或拥有的能力、关系、可支配时间和生活选择也属于非物质所得；不要求使用“收获”字样或证明最大。他人情况或未与本人关联的状态不能代填。'
data={'version':'full-interview-v1.29.0','question_context_mode':'independent',
      'output_protocol':{'relation_evidence':'逐字引用数组；可显式使用 same_as_evidence 引用本字段已验证evidence，展开后按同一关系规则校验，缺省不推断。','alias_requires_explicit_opt_in':True,'model_input_projection':'target_fields_v1','joint_evidence_proof':True,'review_mode':None,'evidence_units':'sentence_units_v1','model_source_fields':['id','text','speaker','question_id','question','target_field_id'],'model_field_contract_keys':['id','label','type','requirement','required','usable_answer','none','allowed_states','activation','scope','link','notes','vague','question','semantic_role','answer_format']},
      'states':{'missing':'尚未涉及','known':'有可用的本人回答','none':'本人明确没有对应情况','unknown':'本人明确不知道或记不清','declined':'本人明确不愿讲','deferred':'本人明确以后再讲','ambiguous':'已涉及目标但指代或含义影响理解','conflict':'本题新旧事实矛盾待澄清','not_applicable':'适用前提明确不成立'},
      'controls':['continue','pause','skip_question','defer_question'],
      'global_rules':['仅使用本题主问/追问所得原话与本题已验证状态；每题独立，不借用其他题资料。','一次只追问一个缺口；已回答/明确否定/未知/拒绝/留后不重复索取。','事实与原话的角色、对象、方向和阶段须匹配；题干不证明实际经历。','描述、观点、性格短句、寄语不强制扩写故事；经历只补影响理解的必要信息。','不强要年龄、精确日期、学校、配偶子女、兄弟人数、最早最大比较或积极结局。','同题兼容多种描述同时留存；明确更正保留原始依据；不能静默覆写。','同题同一素材的阶段明确未知只关闭该素材已确认共用的阶段缺口；保留素材及阶段未知依据，不关闭其它素材或仍未答内容。','协议、引用或格式错误为内部 invalid；保留原始失败，最多一次同通用提示内部重提，不向本人重复索要。','pause优先停止；skip/defer不等同资料齐全；资料达标不等同已确认或已保存。'],
      'default_order':order,'questions':[contracts[q] for q in order]}
(HERE/'contracts.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
lines=['# 全62组逐题要素合同 v1','', '由 contracts.json 生成，运行时只读取 JSON。原题和默认顺序逐字取自业务基准；本稿供主代理审核同步。','',
       '各题独立。known/允许的 none 可满足资料标准；unknown/declined/deferred 或不适用可有限收口，不能算资料齐全。missing/ambiguous/conflict 选择一个缺口追问。pause 立即保留位置停止。所有状态必须有本题本人原话，公开稿未提及不当作未知。','']
for n,qid in enumerate(order,1):
    q=contracts[qid]; lines += [f'## {n}. {qid} {q["title"]}','',f'原题：{q["main_question"]}','']
    if q['premise']: lines += ['适用前提：'+q['premise']['usable']+' '+q['premise']['negative'],'']
    lines += ['| 编号 | 要素／层级 | 最小可用回答与边界 | 单缺口问法 |','| --- | --- | --- | --- |']
    for f in q['elements']:
        activation='' if f['activation'].get('always') else ' 激活：'+json.dumps(f['activation'],ensure_ascii=False)
        negative=' 可明确没有。' if f['none'] else ''
        lines += ['| '+f['id']+' | '+f['label']+'／'+f['requirement']+' | '+f['usable_answer']+negative+activation+' '+f['notes'] if 'notes' in f else '| '+f['id']+' | '+f['label']+'／'+f['requirement']+' | '+f['usable_answer']+negative+activation]
        lines[-1] += ' | '+(f['question'] or '不主动追问')+' |'
    lines += ['', '资料足够：'+q['success'],'','信息有限可收口：'+q['limited'],'']
    if q['notes']: lines += [q['notes'],'']
(HERE/'contracts.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'questions':len(contracts),'fields':sum(len(q['elements']) for q in contracts.values()),'version':data['version']},ensure_ascii=False))
