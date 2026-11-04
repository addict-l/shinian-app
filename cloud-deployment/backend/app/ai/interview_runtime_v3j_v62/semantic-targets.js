'use strict';
// Shared target predicates. No narrator identities, corpus excerpts, gold or IO.
// Inputs are already normalized literal proof from the current question.
function upbringingRelation(proof) {
  const care='(?:照顾|照看|照料|抚养|养育|抚育|收养|带大|养大)';
  const reversed=/我(?:一个人|自己)?(?:把|将)?(?:孩子|儿子|女儿|妹妹|弟弟|你)[^。！？]{0,8}(?:带大|养大|抚养)/.test(proof);
  const shared=/(?:跟|和|与|随).{0,20}(?:长大|一起|生活|同住|住在)|(?:我|本人).{0,12}(?:长大|生活|住在)|(?:我们|我们家|我家|我们的家庭).{0,8}(?:都不分家|共同生活|一起住|同住)|(?:我们家庭|我们家|我家).{0,22}(?:在一起吃饭|共同生活)/.test(proof);
  const caredFor=new RegExp(care+'(?:着|过|了)?(?:我|本人)|(?:把我|带我|将我).{0,8}(?:大|养)|(?:我|本人)(?:(?:小时候|年幼时|从小|当时|一直|主要|都是|后来|幼时)){0,4}(?:由|被).{1,22}'+care+'|由(?!我).{1,18}(?:养|带)').test(proof);
  return {reversed,relevant:shared||caredFor};
}
function explicitFeltMeaning(proof) {
  return /(?:我|让我|使我).{0,12}(?:感到|感受|体会|意识到|明白|懂得|才知道)|(?:使我|让我).{0,8}(?:感动|动容)|(?:家人|亲人|家里人|父母|父亲|母亲|爸爸|妈妈|家).{0,15}(?:意义|重要|意味着|靠山|支柱|铠甲|软肋|珍贵|珍惜)/.test(proof)||
    /(?:给|是|成为|成了).{0,3}我.{0,8}(?:力量|支持|依靠|靠山|支撑|安全感|慰藉)|我.{0,8}(?:像|仿佛|好像)?(?:失去|没了|失去了|有了).{0,4}(?:依靠|靠山|支撑|安全感)|我被.{0,12}(?:感化|打动)|(?:这种|那种|这份|那份|那一刻).{0,4}(?:感觉|感情|感受).{0,8}(?:不同|不一样|难以|无法)/.test(proof);
}
const INEXPRESSIBLE=/(?:说不出|讲不出|道不出|难以言说|难以言表|无法言说|无法言表|无从说起|一言难尽|说不清楚?|讲不清楚?)/;
function onlyExistentialExperience(value) {
  if(!/(?:遗憾|挫折|困难|苦难|委屈|经历|事情|故事|往事)/.test(value)||!/(?:有|经历|发生|留下|说不出来|难以言说)/.test(value))return false;
  if(/(?:没有|没什么|毫无|无)(?:任何|什么)?(?:遗憾|挫折|困难|委屈|经历|事情|故事)/.test(value))return false;
  const rest=value.replace(/(?:当然|其实|真正|总会|都会|也会|还是|可能|多少|很多|不少|一些|各种|一项|一件|一个|这一生|这辈子|一辈子|一生|人生|每个人|人人|本人|我们|我|有过|经历过|经历|发生过|发生|留下|遗憾|挫折|困难|苦难|委屈|事情|故事|往事|说不出来|难以言说|一言难尽|无悔|不后悔|耿耿于怀|但|却|总|都|还|也|过|有|是|会|的|了|啊|吧|呢|嘛|不|能|[，,。！？!?；;、\s])/g,'');
  return rest.length===0;
}
function responseClauses(text) {
  // Keep quoted speech together: a reported accusation must not turn into a
  // fresh first-person action merely because there is a comma inside it.
  const clauses=[];let current='',closing=null;
  const pairs={'“':'”','「':'」','『':'』','"':'"'};
  for(const char of text) {
    if(closing){current+=char;if(char===closing)closing=null;continue;}
    if(pairs[char]){closing=pairs[char];current+=char;continue;}
    if(/[，,。！？!?；;]/.test(char)){if(current.trim())clauses.push({text:current.trim(),sentenceEnd:/[。！？!?；;]/.test(char)});current='';}
    else current+=char;
  }
  if(current.trim())clauses.push({text:current.trim(),sentenceEnd:true});
  return clauses;
}
function interpersonalResponseEvidence(proof,value,evidenceText=proof) {
  const context=evidenceText||proof;
  const clauses=responseClauses(context);
  // Inspect the framing clause even when value only names the requested act.
  // A sufficient act elsewhere cannot license an unrelated selected value.
  const selected=clauses.filter(({text})=>text.includes(value)||value.includes(text));
  let excluded=false,actual=false,conditional=false;
  for(const unit of clauses) {
    const clause=unit.text;
    const lead=clause.replace(/^(?:(?:后来|当时|那时|现在|如今|最后|于是|所以|但是|可是|然而|但|却|还是|事后|为此|一直|从那以后|那以后|再后来|第二天|先)\s*)+/,'');
    const participant=/^(?:我(?:的)?(?:先生|丈夫|妻子|太太|爱人|老伴|伴侣)|我们(?:夫妻|夫妇|两个人|俩)?|我|他(?!们)|她(?!们)|对方|丈夫|妻子|先生|太太|爱人|老伴|伴侣|双方)/.exec(lead);
    const body=participant?lead.slice(participant[0].length):lead;
    const predicate=body.replace(/^(?:(?:就|先|一直|总是|总|通常|每次|后来|主动|开始|也|还|仍然|确实|都|也会|都会|会|只是)\s*)+/,'');
    // The outer, asserted predicate controls modality. Already explaining,
    // asking or comforting is an action even if its content mentions a wish,
    // an accusation, or a hypothetical situation. Hoping to do so is not.
    const firstPerson=participant&&/^(?:我|我们)$|^我们(?:夫妻|夫妇|两个人|俩)$/.test(participant[0]);
    const communication=participant&&(/^(?:商量|协商|沟通|解释|询问|问(?:过|了)?(?:他|她|对方)|劝(?:过|了)?(?:我|他|她|对方)|(?:向|跟|对)(?:我|他|她|对方)(?:解释|说明|表达|提出)|(?:跟|对|和)(?:我|他|她|对方)(?:说|讲|谈))/.test(predicate)||
      (firstPerson&&/^(?:要求(?:他|她|对方)|(?:说|讲)[：:“「『"])/.test(predicate)));
    const opensCondition=/(?:如果|假如|要是|假设)/.test(lead)&&!communication;
    if(opensCondition)conditional=true;
    else if(/^(?:但|可是|然而|不过)?(?:后来|实际上|最终)/.test(clause))conditional=false;
    const hypothetical=conditional||(!communication&&/(?:但愿)/.test(lead));
    if(unit.sentenceEnd)conditional=false;
    if(selected.length&&!selected.includes(unit))continue;
    const mediatesOwnConflict=/(?:帮(?:助)?|替|为)(?:我们(?:夫妻|夫妇|俩)?|我和(?:他|她)|双方).{0,12}(?:调解|劝和|沟通|说和)/.test(lead);
    const thirdParty=(!mediatesOwnConflict&&/^(?:我(?:的)?(?:父亲|母亲|爸爸|妈妈|哥哥|姐姐|弟弟|妹妹|儿子|女儿|朋友|同事|邻居)|邻居|同事|朋友|别人|他们|她们)/.test(lead))||
      /(?:邻居|朋友|同事|别人)(?:夫妻|夫妇|两口子)|(?:我|我们)(?:跟|和|与)(?:同事|邻居|朋友)(?:之间的?|的)(?:矛盾|分歧|争执)/.test(lead);
    const unrealized=/(?:希望|盼望|期待|但愿|应该|应当|如果|假如|要是|打算|想要|想让)/.test(lead)||
      /(?:要求|催促|逼|劝)(?:着|了|过)?(?:我|我们|他|她|双方|对方)/.test(lead)||
      /(?:他|她|丈夫|妻子|先生|太太|老伴|伴侣)(?:就|总|一直|又|还|也|只)?(?:要|让|叫)(?:我|我们)/.test(lead)||
      /^(?:要|让|叫)(?:我|我们)/.test(lead);
    const reportedAccusation=/(?:说|讲|认为|觉得|以为|猜测|嫌|怪|埋怨|抱怨|批评|指责)(?:着|了|过)?[：:“「『" ]*(?:我|我们|你|您|邻居)/.test(lead);
    const negatedDemand=/^(?:我|我们|他|她|双方)(?:后来|从来|一直|也|还|都|就)?(?:没有|没|不再|从不|不曾|不会)(?:再)?(?:要求|逼|催促|强求)(?:我|我们|他|她|对方)/.test(lead);
    if(thirdParty||hypothetical){excluded=true;continue;}
    if(communication){actual=true;continue;}
    if(reportedAccusation||(unrealized&&!negatedDemand)){excluded=true;continue;}
    if(negatedDemand){actual=true;continue;}
    // Negative outcomes and refusals are usable facts; never require success,
    // reconciliation, or a positive psychological state.
    const responseState=/(?:没有|没|尚未|未能|还没|一直没).{0,5}(?:解决|处理|谈拢|说开|沟通|回应|这样做|这么做|那么做)|(?:不再|再也不|停止|没有再|没再).{0,4}(?:骂|吵|争)|(?:各过各的|各自住|分开住|分居|离婚|没有答应|没答应|拒绝了|没有体谅|不理他|不理她|没有下文|不了了之|没有再提|没再提)/.test(lead);
    if(responseState){actual=true;continue;}
    const complaint=/(?:骂|吵架|争吵|批评|指责|埋怨|抱怨|嫌|怪)/.test(lead);
    if(complaint){excluded=true;continue;}
    const handling=/(?:沟通|商量|协商|冷静|道歉|认错|解释给|向.{0,6}解释|包容|妥协|体谅|谅解|理解|倾听|说开|谈开|和解|和好|忍让|退让|调整|分工|分开|劝和|调解|对不起)/.test(body);
    // An actual actor doing something can answer without a named technique
    // (e.g. making tea or changing shifts). Possessive nouns and feelings alone
    // are not performed actions. This is a bounded rejection guard, not a
    // complete language parser: the model still identifies the relevant claim.
    const onlyFeeling=/^(?:很|觉得|认为|感觉|感到|害怕|担心|喜欢|伤心|难过|委屈|心痛|想|希望|应该)/.test(predicate);
    const actorAction=participant&&predicate.trim()&&!/^(?:的|是|有)/.test(predicate)&&!onlyFeeling;
    if(onlyFeeling&&!handling)excluded=true;
    if(handling||actorAction)actual=true;
  }
  return {relevant:!excluded||actual,excluded,actual};
}
function onlyHouseholdComposition(value) {
  const clauses=value.split(/[，,。！？!?；;\n]/).map(t=>t.trim()).filter(Boolean);
  if(!clauses.length)return false;
  return clauses.every(clause=>{
    const body=clause.replace(/^(?:那个时期|那段时间|那个时候|那时候|小时候|当时|那时|以前|从前)/,'')
      .replace(/^(?:(?:我们家庭|我们家|我们一家|我们|我家|家庭|家里人|家里|全家|一家人|家人|人口|成员|一直|从来|共有|超过|大约|大概|有|共|都|超))+/,'');
    return /^(?:不分家|同住|住在一起|一起住|住一块|共同居住|在一起吃饭|一起吃饭|一块吃饭|[0-9一二三四五六七八九十百两几]+(?:多|来)?(?:个|口|人)(?:人)?)$/.test(body);
  });
}
function actionInquiryNotTrait(value,contexts) {
  if(!/^(?:你们|你|您)(?:也|还|居然|竟然)?(?:敢|能|会|要)[^，,。；;\n]+$/.test(value))return false;
  return contexts.some(c=>{
    for(let start=c.text.indexOf(value);start>=0;start=c.text.indexOf(value,start+1)) {
      const frame=c.text.slice(Math.max(0,start-60),start).trim();
      if(/(?:问|讶异|惊讶|疑惑)[^。！？!?]{0,24}[？?]?$/.test(frame))return true;
    }
    return false;
  });
}
function preferenceFromActualQuestion(value,contexts) {
  return contexts.some(c=>c.quote.includes(value)&&/(?:爱好|乐趣|喜欢|喜爱|享受|hobb(?:y|ies)|enjoy|favou?rite)/i.test(c.question));
}
// Sibling-target separation. Where a question splits two neighbouring concepts into separate
// targets (a relative who doted on me vs. one who influenced me deeply; effort/conditions/
// opportunity vs. luck; the teacher vs. the change in me; a way of working vs. one identifiable
// story), material that only shows the sibling concept does not fill this target unless the
// narrator states this target's own concept. Bounded guards; the judge still identifies the claim.
const SIBLING_GUARDS={
  influential_relative:{reason:'affection_or_care_not_selected_influence',
    sibling:/(?:疼|宠|爱护|呵护|照顾|照料|关心|关照|(?:对|待)我(?:很|非常|特别|十分)?好)/,
    own:/(?:影响|改变|榜样|启蒙|塑造|受益|教我|教会|教导|教育我|学会|学到|学他|学她|养成|从此|一辈子|终身|难忘|忘不了|佩服|敬佩|崇拜|感激|感谢|印象(?:最)?深|最深|很深|深远|像(?:他|她)|性格|脾气|为人|做人|处事|习惯|跟着(?:他|她))/},
  luck_view:{reason:'effort_conditions_or_opportunity_not_luck',
    sibling:/(?:努力|勤奋|奋斗|拼搏|吃苦|苦干|条件|天赋|天分|先天|后天|机会|机遇|把握|抓住|本事|能力|实力)/,
    own:/(?:运气|运道|好运|走运|幸运|侥幸|命|天意|老天|福气|福分|造化|缘分|机缘|碰巧|凑巧|巧合|偶然|赶上|碰上|遇上|撞上|可遇不可求|倒霉|时运)/},
  // the sibling here is praise, remembrance or gratitude toward the source person (the person target)
  narrator_change_effect:{reason:'praise_or_remembrance_not_narrator_change',
    sibling:/(?:怀念|想念|永铭|铭记|难忘|不忘|忘不了|感谢|感激|感恩|敬佩|佩服|尊敬|崇拜|优秀|一时之选|了不起|出色|有名|著名|名师|好老师|教养|教导|栽培)/,
    own:/(?:改变|转变|变得|变成|变了|影响|(?:与|跟|和).{0,20}(?:有关|关系|相关)|让我|使我|令我|叫我|教我|教会|学会|学到|养成|从此|此后我|后来我|以后我|奠定|启发|受益|受用|走上|懂得|明白了|爱上|喜欢上|兴趣|信心|习惯|成为|决定|开始|至今|到现在|帮助我|帮我)/},
  selected_identifiable_story:{reason:'general_duty_goal_or_manner_not_story',
    sibling:/(?:为人|待人|处事|做人|做事|尽心尽力|尽职|尽责|兢兢业业|服务|职责|本职|(?:让|使|为)(?:患者|病人|病患|学生|顾客|客人|大家|人们|别人|群众|百姓|人民|孩子们)|每天|总是|一向|向来|始终|从来|平时|通常|凡事)/,
    own:/(?:那次|有一次|一次|那年|那天|那时|当时|当年|那段|第一次|最早|首次|曾经|后来|[0-9一二三四五六七八九十百]+(?:年|岁)|开展|报道|发表|获得|获奖|得奖|创办|创立|建立|完成|参加|发明|发现|带领|主持|出版|考上|考取|救了|救活|抢救|写了|做了|办了|建了|修了)/},
};
function mismatch(def,proof,value,direct,questions=[],evidenceText=proof,contexts=[]) {
  const role=def.semantic_role||def.type;
  const sibling=SIBLING_GUARDS[role];
  if(sibling&&!direct&&sibling.sibling.test(proof)&&!sibling.own.test(proof))return sibling.reason;
  if(def.type==='atmosphere'&&onlyHouseholdComposition(value))return 'household_composition_not_interpersonal_atmosphere';
  if(def.type==='reported_trait'&&actionInquiryNotTrait(value,contexts))return 'event_inquiry_not_reported_trait';
  if(role==='child_personhood_expectation'&&!direct&&/(?:鼓励|教导|告诉|做题|分数|成绩|考.{0,4}名|一百分|读书|上学|辛苦.{0,8}(?:几年|一辈子))/.test(proof)&&
     !/(?:成为|做个|做一|做人|品格|品性|性格|善良|诚实|正直|独立|负责|担当|守信|尊重|宽容|善待|知足|不攀比|自食其力)/.test(proof))return 'education_instruction_not_personhood_expectation';
  if(role==='interpersonal_response'&&!interpersonalResponseEvidence(proof,value,evidenceText).relevant)
    return 'complaint_request_or_other_relationship_not_interpersonal_response';
  // A statement that the experience cannot be put into words is the narrator's own
  // inexpressibility claim (see onlyExistentialExperience), not a concept definition.
  if(def.type==='experience'&&!direct&&questions.some(q=>/(?:是什么|是什么意思|什么叫|何谓)/.test(q||'')&&!/(?:有过|经历|发生|你|您)/.test(q||''))&&
     /(?:所谓|真正|就是|是)/.test(proof)&&!/(?:我|本人|我们|当年|那年|那次|那天|小时候|读书时|\d{2,4}年)/.test(proof)&&
     !INEXPRESSIBLE.test(proof))return 'concept_definition_not_owned_experience';
  if(role==='responsibility_self_arrangement'&&!direct&&/(?:工作|退休|职业|单位|管理|上班|打工)/.test(proof)&&
     !/(?:家庭|家人|父母|子女|儿女|孩子|妻子|丈夫|太太|老伴|老人|照顾|养家|兼顾|平衡|取舍|休息|时间|自己|安排|两头)/.test(proof))return 'occupational_fact_not_responsibility_self_arrangement';
  if(role==='liked_activity'&&!direct&&!preferenceFromActualQuestion(value,contexts)&&/(?:每天|每日|天天|经常|定期|一直|都在|都要|安排|必须)/.test(proof)&&
     !/(?:喜欢|喜爱|爱好|最爱|热爱|乐趣|享受|爱.{0,4}(?:做|看|读|听|玩|唱|种|练)|开心|快乐|愉快|高兴|乐在其中)/.test(proof))return 'routine_not_personal_preference';
  if(role==='gratitude_experience'&&!direct&&/(?:感动|动容|打动|帮助我|帮我|帮过我|对我好|支持我)/.test(proof)&&
     !/(?:感谢|感激|感恩|谢意|恩情|恩德|报恩|铭记.{0,6}(?:帮助|好处|恩)|记得.{0,6}(?:恩|好))/.test(proof))return 'moved_or_helped_not_gratitude';
  if(role==='selected_personal_quality') {
    const achievement=/(?:获.{0,6}(?:奖|勋章)|奖章|奖牌|勋章|作品|出版|拍摄|制作.{0,5}(?:影片|电影|纪录)|修过.{0,6}桥)/.test(value);
    const quality=/(?:为人|待人|处事|做人|品格|品质|性格|认真|诚实|善良|正直|守信|负责|踏实|坚持|尊重|关怀|热心|从不|总是|一向|我是.{0,16}(?:的人|人)|愿意.{0,8}(?:帮助|帮人|服务|为人))/.test(value);
    if(achievement&&!quality)return 'achievement_not_selected_personal_quality';
  }
  if(role==='life_worth_judgment'&&!direct&&/(?:舒服|舒心|满意|没有.{0,4}遗憾|过得.{0,4}(?:好|幸福)|无悔)/.test(value)&&
     !/(?:值得|不值得|很值|值当|值了|没白|不白|白活|白来|一生.{0,8}(?:意义|价值)|人生.{0,8}(?:意义|价值))/.test(proof))return 'comfort_not_life_worth_judgment';
  return null;
}
function preferredInclusiveFamilySubject(def,subject,proof) {
  if(subject!=='family'||def.scope.subjects[0]!=='self')return subject;
  const m=/(?:我们(?:夫妻|夫妇|俩|一家|家庭|家里|家)|我家|(?:我们|我)(?:刚|当时|那时候|那时|开始)?(?:结婚|成家|婚后|住|生活))/.exec(proof);
  if(!m)return subject;
  const prefix=proof.slice(0,m.index);
  if(/(?:[^我]|^)(?:说|讲|问)[：:]/.test(prefix))return subject;
  return 'self';
}
module.exports={upbringingRelation,explicitFeltMeaning,onlyExistentialExperience,interpersonalResponseEvidence,mismatch,preferredInclusiveFamilySubject};
