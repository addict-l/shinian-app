'use strict';
/* Isolated, data-driven prototype. No model call, database, save or cross-question inference. */
const contracts = require('./contracts.json');
const evidenceUnits=require('./evidence-units');
const semanticTargets=require('./semantic-targets');
const qmap = Object.fromEntries(contracts.questions.map(q => [q.id, q]));
const fields = Object.fromEntries(contracts.questions.flatMap(q => q.elements.map(f => [f.id, f])));
const baseQuestion = Object.fromEntries(contracts.questions.map(q => [q.id, q.main_question]));
const STATES = new Set(Object.keys(contracts.states));
const TERMINAL = new Set(['known','none','unknown','declined','deferred','not_applicable']);
const UNRESOLVED = new Set(['missing','ambiguous','conflict']);
const PERIODS = new Set(['birth','childhood','school_years','youth','middle_age','adulthood','lifelong','now','unspecified','as_stated']);
const PRECISION = new Set(['day','month','year','decade','relative','approximate','exact','as_stated']);
const UNKNOWN = /(不知道|不清楚|不记得|记不清|记不住|想不起来|想不起|说不清|说不好|忘记|忘了|没听.{0,12}(说|讲|提)|没想好|没想过|没想明白|分不清|不晓得|不知)/;
const DECLINE = /(不想(?:再)?(?:说|谈|讲|聊|回答|提)|不愿|不方便(?:说|谈|讲)|不(?:说|讲|谈)了|别问|别追问|不回答|不说这个|不讲这个|不谈这个|跳过|不想继续)/;
const DEFER = /(以后|下次|改天|回头|往后|先放|先不(?:说|讲|谈|聊)|暂时不(?:说|讲|谈|聊))/;
const NONE = /(没有|没什么|没啥|未曾|从不|不曾|从未|谈不上|没觉得|不觉得|不需要|独生|没(?:上|读|结)|无(?:所谓|需|关|特别|子女|孩子|兄弟|姐妹|遗憾|影响|变化)|不是)/;
const CORRECTION = /(说错|记错|更正|改成|不对|不是.{0,30}(而是|是)|准确地说|纠正|刚才.{0,15}(错|不准))/;
// Full pinned upstream single-character table for rule matching only. Never
// rewrite stored source/value/evidence; do not use conversion as identity proof.
// Apache-2.0 attribution and original dictionary are shipped with this package.
const CHAR_MAP = require('./opencc-ts-char-map.json');
// A common kinship lexical variant used in matching, not a stored-text rewrite.
const MATCH_ALIASES = {'姊':'姐'};
const normalize=t=>[...String(t)].map(c=>MATCH_ALIASES[c]||CHAR_MAP[c]||c).join('');
const normalizeScript=t=>[...String(t)].map(c=>CHAR_MAP[c]||c).join('');
const SUBJECT_ALIAS = {narrator:'self',本人:'self',parent:'parents',spouse:'partner',child:'children',sibling:'siblings',relative:'relatives',neighbor:'neighbors',friends:'friend',teachers:'teacher',classmates:'classmate'};
const clone = x => JSON.parse(JSON.stringify(x));
const missing = () => ({state:'missing',value:null,evidence:[]});
const narrates = s => !s.speaker || ['narrator','user','interviewee','self'].includes(s.speaker);
const STAGE_QUESTION='您说的这段经历，大概是人生哪个时候？';
const stageAnswerMatches=(stage,text)=>{
  const t=normalize(text);
  if(UNKNOWN.test(t)||DECLINE.test(t)||DEFER.test(t))return false;
  if(stage==='now')return /现在|目前|如今|当下/.test(t);
  return stage==='youth'&&(/青年|年轻|年少/.test(t)||/^(?:我(?:那时|当时|那年|大概|约)?|大概|大约|约|那时|当时|那年|那时候)?\s*(?:1[5-9]|2\d|3[0-9]|十[五六七八九]|二十.{0,2}|三十.{0,2})(?:多|来|几)?岁(?:左右|前后|那时|那时候|的时候|吧)?[。！! ]*$/.test(t));
};
const refsText = x => (x || []).map(r => r.quote).join(' ');
const scalarTexts = value => typeof value==='string' ? [value] : Array.isArray(value) ? value.flatMap(v => typeof v==='string'?[v]:v&&typeof v.text==='string'?[v.text]:[]) : [];
function literalDurationPrecision(text) {
  const quantity='(?:[0-9]{1,4}|[〇零一二三四五六七八九十百千万两几数半]{1,8})';
  const matches=[...text.matchAll(new RegExp(quantity+'(?:多|余|来)?(?:个)?(?:年|月|天|日|周|星期|礼拜|载)','g'))]
    .filter(m=>! /^(?:1|2)[0-9]{3}年$/.test(m[0]));
  if(!matches.length)return /(?:多年|很久|不久|长时间|很长一段|短暂|一辈子|半辈子|大半生|一生)/.test(text)?'as_stated':null;
  if(new Set(matches.map(m=>m[0])).size>1)return null;
  const approximate=matches.some(m=>/[几数多余来]/.test(m[0])||/^[一二三四五六七八九两]{2}(?:个)?(?:年|月|天|日|周)/.test(m[0])||
    /(?:大约|大概|差不多|将近|接近|约|近|快|[0-9]+[-—至到])[^，。！？；;]{0,3}$/.test(text.slice(Math.max(0,m.index-12),m.index))||
    /^(?:左右|前后|上下|有余)/.test(text.slice(m.index+m[0].length)));
  return approximate?'approximate':'exact';
}
function actualQuestionTargets(id,question) {
  const t=normalize(question||'');if(t===baseQuestion[fields[id]?.question_id])return false;
  if(id==='SK01-E2')return /出生.{0,8}(?:哪|地点|地方)|在哪.{0,8}出生/.test(t);
  if(id==='SK01-E3.period'||id==='SK04-E2.period')return /哪个(?:时候|阶段|时期)|什么(?:时候|时期)|何时/.test(t);
  return false;
}
function literalBirthplace(item,sources,context) {
  if(typeof item.value!=='string')return false;
  const literal=normalize(item.value).trim();
  const statement=/^(?:我|本人)(?:是)?[0-9〇零一二三四五六七八九十百千万两民国年月日号\s]{0,24}(?:出生(?:于|在)|生于|生在)([^，,。！？;；\n]+)/u.exec(literal);
  if(statement&&!/^[0-9〇零一二三四五六七八九十百千万两民国年月日号\s]+$/u.test(statement[1])&&
     item.evidence?.some(e=>sources.some(s=>s.id===e.source_id&&narrates(s)&&s.text.includes(e.quote)&&e.quote.includes(item.value))))return true;
  const value=normalize(item.value),last=sources.at(-1),escaped=value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  for(const ref of item.evidence||[]) {
    const s=sources.find(s=>s.id===ref.source_id);if(!s)continue;
    const question=s.question||(s.id===last?.id?context.current_question:'');
    const leaf=actualQuestionTargets('SK01-E2',question)||s.target_field_id==='SK01-E2'||(s.id===last?.id&&context.focus?.field_id==='SK01-E2');
    const main=question===baseQuestion.SK01;
    for(const clause of normalize(ref.quote).split(/[，,。！？；;\n]/u)) {
      if(!clause.includes(value)||UNKNOWN.test(clause)||new RegExp('(?:不是|并非|没在|不在)(?:在|于|生于|生在)?'+escaped).test(clause))continue;
      const other=/(?:我(?:的)?)?(?:父亲|母亲|爸爸|妈妈|祖父|祖母|爷爷|奶奶|哥哥|姐姐|弟弟|妹妹|他|她)[^，。！？]{0,20}(?:出生|生于|生在)/.test(clause);
      if(other)continue;
      const at=clause.indexOf(value),end=at+value.length;
      let birthLink=false;
      for(const m of clause.matchAll(/(?:出生(?:在|于)|生于|生在)/g)) {
        if(m.index>=end)continue;
        const between=clause.slice(m.index+m[0].length,at);
        if(between.length<=35&&!/后来|之后|以后|后|搬|迁|住|长大|家乡|祖籍|现居|成长|工作|求学|到了|去了/.test(between))birthLink=true;
      }
      if(/(?:我|本人)[^，,。！？；;]{0,20}(?:在|于)\s*$/.test(clause.slice(0,at))&&/^\s*出生/.test(clause.slice(end)))birthLink=true;
      if(birthLink&&(main||leaf||/(?:我|本人)[^，。！？]{0,15}(?:出生|生于|生在)/.test(clause)))return true;
      if(/家乡|祖籍|成长地|现居|长大|住在|居住|搬到|迁到|工作|求学|旅游|旅行|路过|出生后/.test(clause))continue;
      if(leaf)return true;
      if(main&&/(?:出生(?:的)?(?:地点|地方)|地点|地方)(?:大概|约莫)?(?:是在|位于|是|在)/.test(clause.slice(0,Math.max(at+1,end))))return true;
    }
  }
  return false;
}
function getContract(qid) { return qid ? clone(qmap[qid] || null) : clone(contracts); }
function buildPayload(qid,sources,context={}) {
  if(!qmap[qid]) throw new Error('unknown_question');
  const ownSources=sources.filter(s=>!s.question_id||s.question_id===qid).map(s=>Object.fromEntries(contracts.output_protocol.model_source_fields.filter(k=>k in s).map(k=>[k,clone(s[k])])));
  const ownPrior=Object.fromEntries(Object.entries(context.previous_fields||{}).filter(([id])=>fields[id]?.question_id===qid));
  return {question_id:qid,main_question:baseQuestion[qid],question_context_mode:'independent',
    current_question:context.current_question||baseQuestion[qid],focus:context.focus||null,
    field_contract:Object.fromEntries(qmap[qid].elements.map(f=>[f.id,Object.fromEntries(contracts.output_protocol.model_field_contract_keys.filter(k=>k in f).map(k=>[k,clone(f[k])]))])),
    question_contract:{premise:qmap[qid].premise,success:qmap[qid].success,notes:qmap[qid].notes},
    sources:ownSources,evidence_units:evidenceUnits.catalog(qid,ownSources).map(({id,source_id,text})=>({id,source_id,text})),previous_fields:clone(ownPrior),ask_counts:clone(context.ask_counts||{})};
}
function analyze(qid,sources,proposal,context={}) {
  const q=qmap[qid], errors=[], optionalErrors=[], rejected=[], notices=[], normalizations=[], provenance={}, map={}, effective={};
  const result={decision:'invalid',target:null,question:null,fields:map,effective,active:[],errors,
    rejected_candidates:rejected,scope_notices:notices,protocol_normalizations:normalizations,optional_errors:optionalErrors,inactive_conditional_errors:[],unbound_material:[],provenance,version:contracts.version};
  if(!q) {errors.push('unknown_question');return result;}
  const defs=q.elements, sm=new Map();
  if(!Array.isArray(sources)) {errors.push('invalid_sources');return result;}
  for(const s of sources) {
    if(!s||typeof s.id!=='string'||typeof s.text!=='string'||sm.has(s.id)) {errors.push('invalid_or_duplicate_source');continue;}
    if(s.question_id && s.question_id!==qid) {errors.push('cross_question_source:'+s.id);continue;}
    sm.set(s.id,s);
  }
  const last=sources[sources.length-1];
  const evidenceOK=(refs,required=true) => Array.isArray(refs)&&(!required||refs.length>0)&&refs.every(r=>r&&typeof r.source_id==='string'&&typeof r.quote==='string'&&r.quote.trim()&&Object.keys(r).every(k=>['source_id','quote'].includes(k))&&sm.has(r.source_id)&&narrates(sm.get(r.source_id))&&sm.get(r.source_id).text.includes(r.quote));
  const currentRefs=refs=>Array.isArray(refs)&&refs.some(r=>r.source_id===last?.id);
  const isFocused=(id,refs,allowContext=true)=>refs.some(r=>{
    const s=sm.get(r.source_id);return s&&(s.target_field_id===id||s.question===fields[id]?.question||actualQuestionTargets(id,s.question)||
      (allowContext&&s.id===last?.id&&context.focus?.field_id===id));
  });
  const wholeQuestion=refs=>refs.some(r=>/(这(?:一)?题|这个问题|上面问的这些).{0,15}(?:不知|不记|记不|不清|不想|不愿|不说|不讲|没有|没想)/.test(normalize(r.quote))||/^(?:这些|全部|全都|都)(?:我)?(?:都)?(?:记不清|不记得|不知道|不愿说|不想讲)[。！! ]*$/.test(normalize(r.quote)));
  let validatingPrior=false;
  const semanticReasons=new Set(['family_action_not_narrator_felt_meaning','unknown_without_explicit_basis','refusal_without_explicit_basis','defer_without_explicit_basis','negative_without_explicit_basis','terminal_not_bound_to_actual_target','terminal_attitude_belongs_to_another_person','not_applicable_without_explicit_premise_absence','terminal_without_any_basis','time_requires_usable_when_not_process_evaluation','duration_requires_temporal_extent_not_work_evaluation','family_identity_not_primary_caregiving','care_relation_reversed','location_role_not_birthplace','identity_not_actual_activity_or_livelihood','living_conditions_not_interpersonal_atmosphere','lifelong_self_state_not_household_interaction','peers_not_siblings','upbringing_direction_reversed','child_education_direction_reversed','reported_trait_not_self_endorsement','conversation_evaluation_not_self_trait','conversation_not_selected_summary','specific_advice_or_outcome_not_personality_effect','academic_target_not_child_personhood_expectation','lesson_not_narrator_resolution_state','experience_value_is_only_evaluation_or_person_label','period_requires_temporal_expression']);
  result.semantic_rejections=[];
  for(const reason of ['achievement_not_selected_personal_quality','comfort_not_life_worth_judgment'])semanticReasons.add(reason);
  function fail(id,obj,reason,protocol=true) {
    rejected.push({field_id:id,reason,candidate:clone(obj)});
    const semantic=semanticReasons.has(reason)&&!validatingPrior&&!CORRECTION.test(normalize(last?.text||''));
    if(semantic)result.semantic_rejections.push({field_id:id,reason,retained_state:'missing_or_validated_previous'});
    if(protocol&&!semantic)errors.push(id+':'+reason);
    return null;
  }
  const literalViews=new Map();
  function fieldScopeValid(id,obj,prior=false) {
    validatingPrior=prior;
    const def=fields[id];
    if(obj&&typeof obj==='object'&&('value_unit_ids' in obj||'evidence_unit_ids' in obj||obj.scope&&('relation_unit_ids' in obj.scope||'object_unit_ids' in obj.scope))) {
      const expanded=evidenceUnits.expand(qid,sources,obj,{jointProof:contracts.output_protocol.joint_evidence_proof===true});
      if(!expanded.ok)return fail(id,obj,expanded.error);
      normalizations.push({field_id:id,rule:'expand_selected_original_evidence_units',original_candidate:clone(obj),selections:expanded.events});obj=expanded.candidate;
    }
    if(!prior&&obj&&typeof obj==='object') {
      const owned=['stage_binding','statements','history','provenance','unbound_value'].filter(k=>k in obj);
      if(owned.length){const original=clone(obj);obj=clone(obj);for(const k of owned)delete obj[k];normalizations.push({field_id:id,rule:'discard_untrusted_engine_owned_attributes',attributes:owned,original_candidate:original});}
    }
    if(!obj||typeof obj!=='object'||Array.isArray(obj)||!STATES.has(obj.state))return fail(id,obj||{},'invalid_field_shape');
    // Anchor transcription script variants to a uniquely recoverable literal
    // in the declared local source. Source words are never rewritten; stored
    // evidence is the original span, with the raw proposal in the audit.
    const scriptView=t=>{
      if(literalViews.has(t))return literalViews.get(t);
      const chars=[...String(t)],view=chars.map(c=>CHAR_MAP[c]||c).join('');
      const entry={chars,view,stable:chars.length===[...view].length};literalViews.set(t,entry);return entry;
    };
    const originalSpan=(text,quote)=>{
      if(typeof quote!=='string'||!quote.trim()||text.includes(quote))return null;
      const source=scriptView(text),query=scriptView(quote);
      if(!source.stable||!query.stable||!query.chars.length)return null;
      const matches=[];
      for(let at=source.view.indexOf(query.view);at>=0;at=source.view.indexOf(query.view,at+1)) {
        const i=[...source.view.slice(0,at)].length;
        matches.push({literal:source.chars.slice(i,i+query.chars.length).join(''),start:i,end:i+query.chars.length});
      }
      const distinct=[...new Set(matches.map(m=>m.literal))];
      return distinct.length===1?{literal:distinct[0],spans:matches.map(({start,end})=>({start,end}))}:null;
    };
    if(obj.state!=='missing') {
      const original=clone(obj),restorations=[];obj=clone(obj);
      for(const refs of [obj.evidence,obj.scope?.relation_evidence,obj.scope?.object_evidence]) {
        if(!Array.isArray(refs))continue;
        for(const r of refs) {
          if(!r||typeof r!=='object'||typeof r.source_id!=='string'||typeof r.quote!=='string')continue;
          const src=sm.get(r.source_id);if(!src||!narrates(src))continue;
          const restored=originalSpan(src.text,r.quote);
          if(restored){restorations.push({kind:'quote',source_id:r.source_id,proposed:r.quote,...restored});r.quote=restored.literal;}
        }
      }
      const quotes=(obj.evidence||[]).filter(r=>r&&sm.get(r.source_id)?.text.includes(r.quote)).map(r=>r.quote);
      const restoreValue=v=>{
        if(typeof v!=='string'||quotes.some(q=>q.includes(v)))return v;
        const found=quotes.map(q=>originalSpan(q,v)).filter(Boolean),variants=[...new Set(found.map(x=>x.literal))];
        if(variants.length!==1)return v;
        restorations.push({kind:'value',proposed:v,literal:variants[0]});return variants[0];
      };
      if(obj.state==='known')obj.value=Array.isArray(obj.value)?obj.value.map(v=>typeof v==='string'?restoreValue(v):v):restoreValue(obj.value);
      if(restorations.length)normalizations.push({field_id:id,rule:'restore_unique_script_variant_to_original_literal',original_candidate:original,restorations});
    }
    if(obj.scope&&['links','precision','stance','supersedes','clarifications'].some(k=>k in obj.scope)) {
      const original=clone(obj), lift=['links','precision','stance','supersedes','clarifications'].filter(k=>k in obj.scope);
      if(lift.some(k=>k in obj&&JSON.stringify(obj[k])!==JSON.stringify(obj.scope[k])))return fail(id,obj,'conflicting_misplaced_field_attributes');
      obj=clone(obj);for(const k of lift){obj[k]=obj.scope[k];delete obj.scope[k];}
      normalizations.push({field_id:id,rule:'lossless_field_attribute_lift_from_scope',attributes:lift,original_candidate:original});
      notices.push({field_id:id,rule:'lossless_field_attribute_lift_from_scope'});
    }
    if(['time','duration'].includes(def.type)&&obj[def.type]&&typeof obj[def.type]==='object'&&!Array.isArray(obj[def.type])&&Object.keys(obj[def.type]).length===1&&Object.hasOwn(obj[def.type],'precision')) {
      const original=clone(obj),nested=obj[def.type].precision;
      if(Object.hasOwn(obj,'precision')&&JSON.stringify(obj.precision)!==JSON.stringify(nested))return fail(id,obj,'conflicting_typed_precision_attributes');
      obj=clone(obj);obj.precision=nested;delete obj[def.type];
      normalizations.push({field_id:id,rule:'lossless_typed_precision_wrapper',original_candidate:original});
    }
    // Empty missing has no assertion and therefore no relation to validate.
    // Process before the explicit citation alias: a model may redundantly attach
    // an empty scope. A real value/evidence is still rejected, never discarded.
    if(obj.state==='missing' && (obj.value===null||obj.value===undefined) &&
       (!obj.evidence||Array.isArray(obj.evidence)&&obj.evidence.length===0)) {
      normalizations.push({field_id:id,rule:obj.value===undefined?'missing_without_value_is_canonical_empty':'canonical_empty_missing_before_citation_alias',original_candidate:clone(obj)});
      return missing();
    }
    // A shorthand relation quote is lossless only if a single local source
    // witnesses it. No fuzzy match, cross-question lookup or invented ID.
    if(Array.isArray(obj.scope?.relation_evidence)&&obj.scope.relation_evidence.some(r=>typeof r==='string')) {
      const refs=obj.scope.relation_evidence;
      const bound=refs.map(r=>{
        if(typeof r!=='string')return r;
        const matches=sources.filter(s=>narrates(s)&&sm.has(s.id)&&r.trim()&&s.text.includes(r));
        return matches.length===1?{source_id:matches[0].id,quote:r}:null;
      });
      if(bound.every(Boolean)) {
        const original=clone(obj);obj=clone(obj);obj.scope.relation_evidence=bound;
        normalizations.push({field_id:id,rule:'bind_unique_literal_relation_shorthand_to_same_question_source',original_candidate:original});
      }
    }
    if(obj.scope?.relation_evidence==='same_as_evidence') {
      if(!evidenceOK(obj.evidence))return fail(id,obj,'evidence_alias_requires_valid_literal_evidence');
      const original=clone(obj);obj=clone(obj);obj.scope.relation_evidence=clone(obj.evidence);
      normalizations.push({field_id:id,rule:'expand_explicit_same_field_evidence_alias',original_candidate:original});
      notices.push({field_id:id,rule:'expand_explicit_same_field_evidence_alias'});
    }
    const allowed=['state','value','evidence','scope','precision','stance','supersedes','links','clarifications','statements','history','provenance','unbound_value','stage_binding'];
    if(Object.keys(obj).some(k=>!allowed.includes(k)))return fail(id,obj,'unrecognized_field_attribute');
    if(obj.state==='missing') {
      if(obj.value===undefined&&(!obj.evidence||Array.isArray(obj.evidence)&&obj.evidence.length===0)) {
        normalizations.push({field_id:id,rule:'missing_without_value_is_canonical_empty',original_candidate:clone(obj)});
        return missing();
      }
      if(obj.value!==null||(obj.evidence&&obj.evidence.length))return fail(id,obj,'missing_carries_value');
      return missing();
    }
    if(['none','unknown','declined','deferred','not_applicable'].includes(obj.state)&&obj.value==null&&Array.isArray(obj.evidence)&&!obj.evidence.length)return fail(id,obj,'terminal_without_any_basis');
    if(!def.allowed_states.includes(obj.state))return fail(id,obj,'state_not_allowed');
    if(!evidenceOK(obj.evidence))return fail(id,obj,'invalid_field_evidence');
    if(prior&&!obj.scope&&['unknown','declined','deferred'].includes(obj.state)&&evidenceOK(obj.evidence)&&isFocused(id,obj.evidence,false)) {
      obj=clone(obj);obj.scope={subject:def.scope.subjects.includes('self')?'self':def.scope.subjects[0],period:'unspecified',relation_evidence:clone(obj.evidence)};
      notices.push({field_id:id,rule:'legacy_terminal_cache_bound_to_actual_directed_question'});
    }
    if(Array.isArray(obj.scope?.subject)&&obj.scope.subject.length===1&&typeof obj.scope.subject[0]==='string') {
      const original=clone(obj);obj=clone(obj);obj.scope.subject=obj.scope.subject[0];normalizations.push({field_id:id,rule:'singleton_subject_array_to_scalar',original_candidate:original});
    }
    const sc=obj.scope;
    if(Array.isArray(sc?.subject))return fail(id,obj,'subject_must_be_one_string_not_array_choose_one_allowed_role');
    if(!sc||typeof sc!=='object'||Array.isArray(sc)||!evidenceOK(sc.relation_evidence))return fail(id,obj,'scope_or_relation_evidence_missing');
    if(Object.keys(sc).some(k=>!['subject','period','relation_evidence','object','object_role','object_evidence','domain','kind'].includes(k)))return fail(id,obj,'unknown_scope_attribute');
    let subject=SUBJECT_ALIAS[sc.subject]||sc.subject;
    const premiseAbsence=obj.state==='not_applicable'&&q.premise&&subject==='self'&&new RegExp(q.premise.no_premise_pattern).test(normalize(refsText(obj.evidence)));
    if(!def.scope.subjects.includes(subject)&&!premiseAbsence)return fail(id,obj,'wrong_subject');
    const preferred=semanticTargets.preferredInclusiveFamilySubject(def,subject,normalize(refsText(sc.relation_evidence)));
    if(preferred!==subject) {
      normalizations.push({field_id:id,rule:'explicit_inclusive_family_uses_contract_preferred_self',original_subject:subject,canonical_subject:preferred});subject=preferred;
    }
    if(!PERIODS.has(sc.period))return fail(id,obj,'invalid_scope_period');
    const related=sc.relation_evidence.some(r=>obj.evidence.some(e=>r.source_id===e.source_id&&(r.quote.includes(e.quote)||e.quote.includes(r.quote))));
    if(!related)return fail(id,obj,'relation_not_bound_to_field_evidence');
    if(sc.object_evidence!==undefined&&!evidenceOK(sc.object_evidence))return fail(id,obj,'invalid_object_evidence');
    if(sc.object!==undefined&&(typeof sc.object!=='string'||!sc.object.trim()))return fail(id,obj,'invalid_relation_object');
    if(sc.object!==undefined&&![...(sc.object_evidence||[]),...sc.relation_evidence].some(e=>e.quote.includes(sc.object)))return fail(id,obj,'object_not_in_literal_relation_evidence');
    if(sc.object_role!==undefined&&(!def.scope.object_roles||!def.scope.object_roles.includes(sc.object_role)))return fail(id,obj,'object_role_not_allowed_by_contract');
    const proof=normalize(refsText(sc.relation_evidence)), text=normalize(refsText(obj.evidence)), direct=isFocused(id,obj.evidence,!prior);
    const evidenceContexts=obj.evidence.map(e=>({question:normalize(sm.get(e.source_id)?.question||''),quote:normalize(e.quote),text:normalize(sm.get(e.source_id)?.text||'')}));
    // Absence of any temporal answer is missing, not an invented time ambiguity.
    // A real directed short answer or temporal expression remains untouched.
    if(obj.state==='ambiguous'&&def.type==='period'&&!direct&&!/(?:[0-9〇零一二三四五六七八九十百千万两几多半]{1,8}(?:年|月|日|号|岁)|年代|世纪|民国|抗战|解放|战前|战后|小时候|小的时候|从小|儿时|童年|幼年|幼时|少年|青年|年轻|中年|晚年|成年|年幼|很小|记事|读书|(?:上|读|念).{0,3}学|求学|毕业|工作时|入伍|入职|成家|婚前|婚后|结婚|退休|回乡|当时|那时|那阵|那会|那年|那个时候|这时候|那时候|当初|起初|最初|刚开始|以前|过去|从前|早年|后来|现在|如今|目前|一生|一辈子|这些年|多年|之后|以后|以前|之前|从.{1,20}起)/.test(proof+' '+text))return fail(id,obj,'period_ambiguity_without_temporal_material',false);
    if(obj.state==='ambiguous'&&def.type==='time'&&!direct&&
       !/(?:[0-9〇零一二三四五六七八九十百千万两几多半]{1,8}(?:年|月|日|号|岁)|年代|世纪|民国|抗战|解放|战前|战后|春天|夏天|秋天|冬天|小时候|童年|幼年|少年|青年|中年|成年|年幼|很小|小的时候|上学(?:早|晚)|(?:很|比较|特别|太|算)(?:早|晚))/u.test(proof+' '+text))
      return fail(id,obj,'time_ambiguity_without_when_answer',false);
    const expectedPeriod=def.scope.period;
    if(!['lifelong','as_stated'].includes(expectedPeriod)&&!['unspecified','as_stated',expectedPeriod].includes(sc.period))return fail(id,obj,'wrong_scope_period');
    const out=clone(obj);out.scope.subject=subject;
    if(['none','unknown','declined','deferred','not_applicable'].includes(obj.state)&&typeof obj.value==='string'&&obj.evidence.some(e=>e.quote.includes(obj.value))) {
      normalizations.push({field_id:id,rule:'terminal_display_quote_to_null_before_basis_validation',original_candidate:clone(obj)});
      obj=clone(obj);obj.value=null;out.value=null;
    }
    if(obj.state!=='known'&&obj.value!==null)return fail(id,obj,'nonknown_must_have_null_value');
    // Partial assertions must concern the same target as complete assertions.
    // A parent job/departure is not partial evidence of an upbringing relation.
    if(['known','ambiguous'].includes(obj.state)&&def.semantic_role==='narrator_upbringing_relation'&&!direct) {
      const care=semanticTargets.upbringingRelation(proof);
      if(care.reversed)return fail(id,obj,'care_relation_reversed');
      if(!care.relevant)return fail(id,obj,'family_identity_not_primary_caregiving');
    }
    if(obj.state==='ambiguous') {
      const mismatch=semanticTargets.mismatch(def,proof,text,direct,obj.evidence.map(e=>normalize(sm.get(e.source_id)?.question||'')),text,evidenceContexts);
      if(mismatch){semanticReasons.add(mismatch);return fail(id,obj,mismatch);}
    }
    if(obj.state==='known') {
      const values=scalarTexts(obj.value);
      if(!values.length||values.some(v=>!v.trim()||!obj.evidence.some(e=>e.quote.includes(v))))return fail(id,obj,'value_not_in_evidence');
      if(Array.isArray(obj.value)&&def.answer_format?.value_type!=='string_or_string_array')return fail(id,obj,'scalar_value_required');
      const mismatch=semanticTargets.mismatch(def,proof,normalize(values.join(' ')),direct,obj.evidence.map(e=>normalize(sm.get(e.source_id)?.question||'')),text,evidenceContexts);
      if(mismatch){semanticReasons.add(mismatch);return fail(id,obj,mismatch);}
      if(def.type==='experience'&&values.length===1&&semanticTargets.onlyExistentialExperience(normalize(values[0]))) {
        out.state='ambiguous';out.value=null;out.unbound_value=values[0];out.clarifications=['meaning'];
        notices.push({field_id:id,rule:'existence_does_not_identify_experience'});
      }
      if(def.type==='time'||def.type==='duration') {
        const v=values.join(' ');
        const timing=normalize(v);
        let literalDatePrecision=null;
        if(/(?:民国)?[0-9〇零一二三四五六七八九十百]{1,4}年.{0,4}[0-9一二三四五六七八九十]{1,3}月.{0,4}[0-9一二三四五六七八九十]{1,3}(日|号)/.test(timing))literalDatePrecision='day';
        else if(/(?:民国)?[0-9〇零一二三四五六七八九十百]{1,4}年.{0,4}[0-9一二三四五六七八九十]{1,3}月/.test(timing))literalDatePrecision='month';
        else if(/(?:民国)?[0-9〇零一二三四五六七八九十百]{1,4}年/.test(timing)||/^\d{4}$/.test(timing))literalDatePrecision='year';
        if(def.type==='time'&&literalDatePrecision&&!PRECISION.has(obj.precision)) {
          out.precision=literalDatePrecision;
          normalizations.push({field_id:id,rule:'derive_missing_precision_from_literal_date',derived_precision:literalDatePrecision,original_candidate:clone(obj)});
          notices.push({field_id:id,rule:'derive_missing_precision_from_literal_date'});
        }
        if(def.type==='duration'&&obj.precision==null) {
          const derived=literalDurationPrecision(timing);
          if(derived) {
            out.precision=derived;
            normalizations.push({field_id:id,rule:'derive_missing_precision_from_literal_duration',derived_precision:derived,original_candidate:clone(obj)});
            notices.push({field_id:id,rule:'derive_missing_precision_from_literal_duration'});
          }
        }
        if(!PRECISION.has(out.precision))return fail(id,obj,'precision_required');
        if(def.type==='duration'&&!['exact','approximate','as_stated'].includes(out.precision))return fail(id,obj,'invalid_duration_precision');
        if(def.type==='time'&&/^[^。！？;；]*[0-9〇零一二三四五六七八九十百两几多半]{1,5}(?:多|来|几)?岁/.test(timing)&&!/(?:[0-9〇零一二三四五六七八九十百]{2,4}年|年代)/.test(timing)) {
          out.precision=/(大概|大约|左右|前后|几岁|多岁|来岁)/.test(timing)?'approximate':'relative';
          if(obj.precision!==out.precision)normalizations.push({field_id:id,rule:'age_is_relative_time_not_calendar_year',original_candidate:clone(obj),derived_precision:out.precision});
        }
        const numbers='[0-9〇零一二三四五六七八九十百千万两几多半]';
        const when=new RegExp(numbers+'{1,8}(?:年|月|日|号|岁)|年代|世纪|民国|解放|抗战|文革|战前|战后|春天|夏天|秋天|冬天|小时候|童年|幼年|少年|青年|中年|成年|年幼|很小|小的时候|记事时|上学(?:早|晚)|(?:很|比较|特别|太|算)(?:早|晚)|之后|以后|以前|之前');
        const duration=new RegExp(numbers+'{1,8}(?:个)?(?:年|月|天|日|周|星期|礼拜|载)|一辈子|半辈子|大半生|一生|不久|很久|多年|长时间|很长一段|短暂|到现在|一直到|至今');
        if(def.type==='time'&&!when.test(timing)&&!/^\d{4}$/.test(timing)&&!(direct&&/^\d{1,3}$/.test(timing)))return fail(id,obj,'time_requires_usable_when_not_process_evaluation');
        if(def.type==='duration'&&!duration.test(timing))return fail(id,obj,'duration_requires_temporal_extent_not_work_evaluation');
        let literalPrecision=null;
        if(/\d{4}年.{0,4}\d{1,2}月.{0,4}\d{1,2}(日|号)/.test(v))literalPrecision='day';
        else if(/\d{4}年.{0,4}\d{1,2}月/.test(v))literalPrecision='month';
        else if(/\d{4}年/.test(v)&&!/(左右|大概|约|前后|可能)/.test(v))literalPrecision='year';
        if(def.type==='time'&&literalPrecision&&obj.precision!==literalPrecision) {out.precision=literalPrecision;notices.push({field_id:id,rule:'literal_date_precision_preserved'});}
      }
      if(def.type==='stance'&&!['agree','disagree','partial'].includes(obj.stance))return fail(id,obj,'stance_required');
      if(def.type==='period'&&!/(?:[0-9〇零一二三四五六七八九十百千万两几多半]{1,8}(?:年|月|日|号|岁)|年代|世纪|民国|抗战|战前|战后|小时候|小的时候|童年|幼年|少年|青年|年轻|中年|成年|年幼|很小|记事|读书|(?:上|读|念).{0,3}学|求学|毕业|工作时|成家|婚前|婚后|结婚|退休|回乡|当时|那时|那个时候|这时候|那时候|以前|过去|从前|后来|现在|如今|目前|一生|一辈子|这些年|多年|之后|以后|以前|之前)/.test(normalize(values.join(' '))))return fail(id,obj,'period_requires_temporal_expression');
      if(['experience','felt_meaning_experience'].includes(def.type)&&values.every(v=>/^(?:(?:这|那)(?:就)?是)?(?:我)?(?:最|最大|最为)(?:自豪|骄傲|难忘|感动|艰苦|幸福|开心|低落|困难)(?:的)?(?:时候|时刻|一刻|经历|事情)?[。！？! ]*$/.test(normalize(v))||/^(?:我)?(?:最|特别|十分|真心|要|想|非常)?(?:感谢|感恩)(?:我的)?[\u4e00-\u9fff]{0,6}(?:先生|女士|老师|同学|父母|母亲|父亲|妈妈|爸爸|朋友|家人|亲人)[。！？! ]*$/.test(normalize(v))))return fail(id,obj,'experience_value_is_only_evaluation_or_person_label');
      if(def.vague?.includes(obj.value)){out.state='ambiguous';out.value=null;notices.push({field_id:id,rule:'unusable_vague_answer'});}
      // Only reject provable role/direction mismatches. Do not require a fixed keyword list for every answer.
      if(id==='SK01-E1'&&values.some(value=>proof.split(/[，。！？；;]/).some(clause=>clause.includes(normalize(value))&&/(?:我(?:的)?)?(?:父亲|母亲|爸爸|妈妈|哥哥|姐姐|弟弟|妹妹|孩子|儿子|女儿|伴侣|他|她)(?:是)?[^，。！？]{0,15}(?:出生|生于|生在)/.test(clause))))return fail(id,obj,'birth_belongs_to_another_person');
      if(id==='SK01-E2'&&!literalBirthplace(obj,sources,context))return fail(id,obj,'location_role_not_birthplace');
      if(id==='SK01-E3.period'&&sc.period==='unspecified') {
        const eligible=obj.evidence.some(e=>{
          const s=sm.get(e.source_id),t=normalize(s?.text||'');
          return s?.question===baseQuestion.SK01&&/(当时|那时|那个时候)/.test(normalize(e.quote))&&/(?:\d{4}年|出生)/.test(t)&&/(?:地点|出生(?:在|于))/.test(t)&&!/(后来|上小学|上中学|小时候|童年|长大|现在|如今|回乡|搬|迁)/.test(t);
        });
        if(eligible){out.scope.period='birth';notices.push({field_id:id,rule:'literal_that_time_bound_to_actual_birth_question'});}
        else return fail(id,obj,'scene_period_unbound');
      }
      if(id==='SK03-E2'&&values.every(v=>/^(?:(?:我(?:的)?(?:父亲|母亲|父母|爸爸|妈妈)|父亲|母亲|父母|爸爸|妈妈|他|她)(?:当时|那时|以前)?)?(?:是|都是|为|属于|成为|参加了|加入了)?(?:共产党员|共产党|党籍|基督徒|宗教信仰|红五类|党员)[。！! ]*$/.test(normalize(v))))return fail(id,obj,'identity_not_actual_activity_or_livelihood');
      if(def.type==='atmosphere'&&!direct&&/(?:生活|条件|收入|交通|吃穿).{0,6}(?:过得去|说得过去|方便|困难|不错|富裕|贫穷)/.test(normalize(values.join(' ')))&&!/(相处|关系|互相|互帮|和睦|和气|融洽|吵|争|亲近|冷淡|照顾|来往|疏远|热闹|压抑|团结)/.test(proof))return fail(id,obj,'living_conditions_not_interpersonal_atmosphere');
      if(def.type==='atmosphere'&&!direct&&/(一生|一辈子|终生|这辈子|一直到现在).{0,10}(?:孤单|孤独|寂寞|自己一个人|一个人)/.test(normalize(values.join(' ')))&&!/(家里人|家人|家庭|父母|父亲|母亲|爸爸|妈妈|照料者).{0,20}(?:相处|关系|互相|互帮|和睦|和气|融洽|争吵|来往|疏远|冷淡|团结)/.test(proof))return fail(id,obj,'lifelong_self_state_not_household_interaction');
      if(id==='SK03-E3'&&/(师兄|师弟|同学|同事|朋友)/.test(proof)&&!/(兄弟姐妹|哥哥|姐姐|弟弟|妹妹|独生|家.{0,5}(?:个|口|兄弟|孩子)|我们兄弟|我们姐妹)/.test(proof))return fail(id,obj,'peers_not_siblings');
      if(id==='SK03-E3'&&/(?:我是|我(?:是)?个|我为)(?:独生子|独生女|独生子女)/.test(proof)&&!/(?:当时|那时|小时候|以前|曾经|原来|最初|后来)/.test(proof)) {out.state='none';out.value=null;notices.push({field_id:id,rule:'literal_only_child_is_explicit_none'});}
      if(def.none&&def.literal_none_patterns?.some(p=>new RegExp(p).test(proof))&&!UNKNOWN.test(proof)) {out.state='none';out.value=null;notices.push({field_id:id,rule:'contract_literal_absence_canonicalized_to_none'});}
      if(id==='SK04-E1'&&/我(?:对|给).{0,8}(?:子女|孩子|儿子|女儿).{0,12}(?:教育|管|教)/.test(proof)&&!/(父母|家人|父亲|母亲|爸爸|妈妈|爷爷|奶奶).{0,12}(?:对我|给我|让我|教我|管我)/.test(proof))return fail(id,obj,'upbringing_direction_reversed');
      if(id==='FM05-E1'&&/(父母|父亲|母亲|爸爸|妈妈).{0,12}(?:教我|管我|教育我|对我)/.test(proof)&&!/(我(?:对|给|教育|希望|教)|我的孩子|我的子女)/.test(proof))return fail(id,obj,'child_education_direction_reversed');
      if(id==='SK05-E1'&&!direct&&/(别人说|人家说|他们说|她们说|大家说)/.test(proof)&&!/(我(?:也|自己)?(?:觉得|认为|认同)|我就是|我确实)/.test(proof))return fail(id,obj,'reported_trait_not_self_endorsement');
      if(id==='SK05-E1'&&!direct&&/(讲得|说得|讲述|表达得|不连贯|不好意思)/.test(proof)&&!/(性格|我是个|我这个人|平时我|慢热|内向|外向|要强|倔|执着|乐观|坚韧)/.test(proof))return fail(id,obj,'conversation_evaluation_not_self_trait');
      if(id==='SK06-E1'&&!direct&&/(谢谢|感谢您|感谢你|今天就|讲得|说得)/.test(proof)&&!/(一生|这辈子|人生|关键词|概括|总结|形容)/.test(proof))return fail(id,obj,'conversation_not_selected_summary');
      if(def.type==='personality_effect'&&!direct) {
        const enduring=/(性格|脾气|为人|待人|处事|做人|养成|变得|变成|形成|从此|后来我|一向|凡事|不敢|独立|谨慎|内向|外向|要强|倔|执着|乐观|坚韧|诚实|守信|责任|负责|胆小|大胆|慢热|急躁|温和|自信|自卑|坚强|懂事|自律|叛逆|顺从|不爱|不喜欢)/.test(proof);
        const attributedChange=/(?:我|自己).{0,8}(?:受|因为|由于).{0,16}(?:父母|家人|父亲|母亲|师长|家教|管教|教育).{0,10}(?:影响|教育|管教)[^。！？;；]{0,24}(?:由|从).{1,10}转(?:向|为|成)/.test(proof);
        if(!enduring&&!attributedChange)return fail(id,obj,'specific_advice_or_outcome_not_personality_effect');
      }
      if(def.type==='felt_meaning_experience'&&!direct&&!semanticTargets.explicitFeltMeaning(proof))return fail(id,obj,'family_action_not_narrator_felt_meaning');
      if(def.type==='person_expectation'&&/(?:第[一二三四五六七八九十0-9]+名|[一二三四五六七八九十百0-9]+分|成绩|名次)/.test(normalize(values.join(' ')))&&!/(成为|做.{0,6}人|为人|做人|人生|品格|品德|正直|善良|诚实|独立|负责|健康|幸福|快乐|生活)/.test(proof))return fail(id,obj,'academic_target_not_child_personhood_expectation');
      if(def.type==='resolution_state'&&!direct&&/(教训|学到|懂得|明白|做人|待人|处事|应该|必须|以后.{0,8}(?:要|不|别))/.test(normalize(values.join(' ')))&&!/(释怀|释然|放下|放开|放不下|放得下|在意|介意|计较|过去了|看开|心上|心结|耿耿|怨恨|无所谓|不再想|不去想)/.test(proof))return fail(id,obj,'lesson_not_narrator_resolution_state');
    }
    if(['unknown','declined','deferred','none'].includes(obj.state)) {
      if(obj.state==='unknown'&&!UNKNOWN.test(text))return fail(id,obj,'unknown_without_explicit_basis');
      if(obj.state==='declined'&&!DECLINE.test(text))return fail(id,obj,'refusal_without_explicit_basis');
      if(obj.state==='deferred'&&!DEFER.test(text))return fail(id,obj,'defer_without_explicit_basis');
      if(obj.state==='none'&&!NONE.test(text))return fail(id,obj,'negative_without_explicit_basis');
      if(obj.state==='none'&&UNKNOWN.test(text)){out.state='unknown';notices.push({field_id:id,rule:'unknown_is_not_absence'});}
      const normLabel=normalize(def.label), stopPairs=new Set(['本人','一项','时期','当时','认为','现在','所述','人的','一生','生的']);
      const conceptPairs=new Set([...normLabel].slice(0,-1).map((_,i)=>normLabel.slice(i,i+2)).filter(w=>!stopPairs.has(w)));
      let topical=[...conceptPairs].some(w=>proof.includes(w));
      if(def.type==='time')topical=topical||/(哪年|几年|年纪|时间|出生|生日|日期|上学)/.test(proof);
      if(def.type==='duration')topical=topical||/(多久|几年|时长|年头)/.test(proof);
      if(def.type==='applicability'&&q.premise)topical=topical||new RegExp(q.premise.no_premise_pattern).test(proof);
      if(obj.state==='none'&&def.literal_none_patterns?.some(p=>new RegExp(p).test(proof)))topical=true;
      if(id==='SK02-E3')topical=/(?:家人|父母|父亲|母亲|爸爸|妈妈|家里|他们).{0,18}(?:盼|希望|期望|期许|寄托|期待)|(?:没有|没什么|没特别|不知|不清楚).{0,10}(?:期许|期望|寄托|期待)/.test(proof);
      if(!direct&&!wholeQuestion(obj.evidence)&&!topical)return fail(id,obj,'terminal_not_bound_to_actual_target');
      if(['unknown','declined','deferred'].includes(obj.state)&&/(?:他|她|父亲|母亲|同学|老师|朋友|家人|孩子)(?:们)?(?:也|都|一直|其实)?(?:不知道|不清楚|不记得|记不清|不想说|不愿说|以后再说)/.test(text)&&!/(?:我|本人)(?:也|自己|其实)?(?:不知道|不清楚|不记得|记不清|不想说|不愿说|以后再说)/.test(text))return fail(id,obj,'terminal_attitude_belongs_to_another_person');
    }
    if(obj.state==='not_applicable') {
      const p=q.premise;
      if(!p||!new RegExp(p.no_premise_pattern).test(text))return fail(id,obj,'not_applicable_without_explicit_premise_absence');
    }
    if(obj.clarifications!==undefined&&(!Array.isArray(obj.clarifications)||obj.clarifications.some(x=>!['referent','actor','period','meaning','link'].includes(x))))return fail(id,obj,'invalid_clarification_flags');
    if(obj.supersedes!==undefined) {
      if(!Array.isArray(obj.supersedes)||!obj.supersedes.length||obj.supersedes.some(s=>!sm.has(s))||!currentRefs(obj.evidence)||!CORRECTION.test(normalize(last?.text||'')))return fail(id,obj,'invalid_explicit_correction');
    }
    if(obj.links!==undefined) {
      if(Array.isArray(obj.links)&&obj.links.some(l=>Array.isArray(l?.value))&&obj.links.every(l=>l&&typeof l.field_id==='string'&&(typeof l.value==='string'||Array.isArray(l.value)&&l.value.length&&l.value.every(v=>typeof v==='string'&&v.trim())))) {
        const original=clone(obj.links);out.links=obj.links.flatMap(l=>(Array.isArray(l.value)?l.value:[l.value]).map(value=>({field_id:l.field_id,value})));obj={...obj,links:out.links};
        normalizations.push({field_id:id,rule:'expand_explicit_link_value_list',original_links:original});
      }
      if(!Array.isArray(obj.links)||obj.links.some(l=>!l||typeof l.field_id!=='string'||fields[l.field_id]?.question_id!==qid||typeof l.value!=='string'||!l.value.trim()))return fail(id,obj,'invalid_same_question_links');
    }
    if(prior&&obj.unbound_value!==undefined&&(obj.state!=='ambiguous'||typeof obj.unbound_value!=='string'||!obj.evidence.some(e=>e.quote.includes(obj.unbound_value))))return fail(id,obj,'invalid_cached_unbound_value');
    if(prior&&obj.stage_binding!==undefined) {
      const b=obj.stage_binding;
      if(!b||b.stage!==def.scope.stage_binding_required||!['known','unknown','declined','deferred'].includes(b.state)||fields[b.origin_target]?.question_id!==qid||fields[b.origin_target]?.scope.stage_binding_required!==b.stage||!evidenceOK(b.evidence)||!b.evidence.every(e=>sm.get(e.source_id)?.question===STAGE_QUESTION&&(!sm.get(e.source_id).target_field_id||sm.get(e.source_id).target_field_id===b.origin_target))||!(b.state==='known'?stageAnswerMatches(b.stage,refsText(b.evidence)):b.state==='unknown'?UNKNOWN.test(normalize(refsText(b.evidence))):b.state==='declined'?DECLINE.test(normalize(refsText(b.evidence))):DEFER.test(normalize(refsText(b.evidence)))))return fail(id,obj,'invalid_cached_stage_binding');
    }
    // Claims/history are engine-owned. A fresh model output cannot inject unverified memory.
    if(!prior){delete out.statements;delete out.history;delete out.provenance;delete out.stage_binding;delete out.unbound_value;}
    return out;
  }
  for(const f of defs)map[f.id]=missing();
  if(!proposal||typeof proposal!=='object'||Array.isArray(proposal)) {errors.push('invalid_proposal');return result;}
  if(Array.isArray(proposal.links)&&proposal.links.length&&proposal.fields&&typeof proposal.fields==='object') {
    const targets=defs.filter(f=>f.link&&proposal.fields[f.id]?.state==='known'&&proposal.links.every(l=>l&&l.field_id===f.link.field_id&&typeof l.value==='string'&&l.value.trim()));
    if(targets.length===1) {
      const id=targets[0].id,existing=proposal.fields[id].links;
      if(existing===undefined||JSON.stringify(existing)===JSON.stringify(proposal.links)) {
        const original=clone(proposal);proposal=clone(proposal);proposal.fields[id].links=proposal.links;delete proposal.links;
        normalizations.push({field_id:id,rule:'route_root_links_to_unique_declared_explanation',original_proposal:original});
      }
    }
  }
  if(Object.keys(proposal).some(k=>!['control','fields','extra_material'].includes(k)))errors.push('unrecognized_root_field');
  let ctrlValid=false;
  let control=proposal.control;
  if(control&&typeof control==='object'&&'evidence_unit_ids' in control) {
    const expanded=evidenceUnits.expand(qid,sources,control);
    if(!expanded.ok)errors.push('control:'+expanded.error);
    else {normalizations.push({rule:'expand_control_evidence_units',original_control:clone(control),selections:expanded.events});control=expanded.candidate;}
  }

  if(!control||!contracts.controls.includes(control.action)||Object.keys(control).some(k=>!['action','evidence'].includes(k)))errors.push('invalid_control');
  else if(!evidenceOK(control.evidence,control.action!=='continue'))errors.push('invalid_control_evidence');
  else if(control.action!=='continue'&&!currentRefs(control.evidence))errors.push('control_requires_current_source');
  else {
    const t=normalize(refsText(control.evidence));
    const meaning=control.action==='continue'||(control.action==='pause'&&/^(?:我(?:想|要)?|咱们|我们|这次采访|采访)?(?:先|暂时)?(?:暂停|休息|歇)(?:一下|采访|聊天)?[。！.! ]*$|今天.{0,10}(?:先|就).{0,10}(?:到这|停|休息|歇|不聊|不说)|先.{0,8}(?:到这|不聊|不说)|就到这里|不聊了|结束(?:采访|今天)|(?:我|今天).{0,5}累了/.test(t))||
      (control.action==='skip_question'&&/(跳过|换个|换一|下一题|这(?:一)?题.{0,8}(不想|不愿|不说|不讲|略过))/.test(t))||
      (control.action==='defer_question'&&DEFER.test(t));
    if(meaning)ctrlValid=true;else errors.push('control_without_current_intent');
  }
  if(!proposal.fields||typeof proposal.fields!=='object'||Array.isArray(proposal.fields))errors.push('invalid_fields');
  const accepted={};
  for(const[id,obj]of Object.entries(proposal.fields||{})) {
    if(fields[id]?.question_id!==qid) {fail(id,obj||{},'unrecognized_or_cross_question_field');continue;}
    const out=fieldScopeValid(id,obj);if(out)accepted[id]=out;
  }
  // A rejected optional suggestion cannot invalidate independently verified required material.
  // Cross-question sources, unknown field IDs and all required-field errors remain hard failures.
  for(let i=errors.length-1;i>=0;i--) {
    const id=errors[i].split(':')[0];if(fields[id]?.question_id===qid&&fields[id].requirement==='optional') {
      optionalErrors.unshift(errors[i]);errors.splice(i,1);notices.push({field_id:id,rule:'optional_candidate_rejected_without_blocking_required_fields'});
    }
  }
  // Recover only explicit literal household wording after a damaged model citation. No fuzzy text repair.
  const atmosphereId='SK03-E4';
  if(qid==='SK03'&&!accepted[atmosphereId]&&proposal.fields?.[atmosphereId]?.state==='known'&&errors.some(e=>e===atmosphereId+':invalid_field_evidence'||e===atmosphereId+':value_not_in_evidence')) {
    const sourceIds=new Set((proposal.fields[atmosphereId].evidence||[]).map(e=>e.source_id));
    for(const s of sources) {
      if(!sourceIds.has(s.id)||!narrates(s))continue;
      const t=normalize(s.text), addressed=s.question===baseQuestion.SK03||s.question===fields[atmosphereId].question||s.target_field_id===atmosphereId;
      if(UNKNOWN.test(t)||/(邻居|别人|同事|单位|像个家庭)/.test(t))continue;
      const m=t.match(/(?:我们家|我家|家里|家庭)(?:的)?(?:氛围|气氛)(?:很|比较|偏|是|挺)?(?:不|并不|并非)?(?:温暖|和睦|和气|融洽|冷淡|紧张|疏远|亲近)[^。！？；;\n]*/);
      if(!m||(!addressed&&!/(我们家|我家|家里)/.test(m[0])))continue;
      const literal=s.text.slice(m.index,m.index+m[0].length),e=[{source_id:s.id,quote:literal}];
      const recovery={state:'known',value:literal,evidence:e,scope:{subject:'family',period:'childhood',relation_evidence:e}};
      const out=fieldScopeValid(atmosphereId,recovery);if(!out)continue;
      accepted[atmosphereId]=out;
      for(let i=errors.length-1;i>=0;i--)if([atmosphereId+':invalid_field_evidence',atmosphereId+':value_not_in_evidence'].includes(errors[i]))errors.splice(i,1);
      notices.push({field_id:atmosphereId,rule:'explicit_literal_household_atmosphere_after_invalid_citation'});break;
    }
  }
  // An explicit family-to-narrator teaching action is itself a usable educational practice.
  if(qid==='SK04'&&!accepted['SK04-E1']&&!['unknown','declined','deferred','none'].includes(proposal.fields?.['SK04-E1']?.state)) {
    for(const s of sources) {
      if(!narrates(s))continue;
      const t=normalize(s.text),m=t.match(/(?:我(?:的)?)?(?:父亲|母亲|爸爸|妈妈|爷爷|奶奶|外公|外婆|家人|家里人)[^，。！？；;]{0,15}(?:教|教育|管教|叮嘱|嘱咐|要求|鼓励|不准|不让)(?:过|了|着)?(?:我|我们)(?!的孩子|的子女)[^。！？；;]*/);
      if(!m||UNKNOWN.test(m[0])||DECLINE.test(m[0]))continue;
      const literal=s.text.slice(m.index,m.index+m[0].length),e=[{source_id:s.id,quote:literal}],period=/(小时候|从小|童年|幼年)/.test(normalize((s.question||'')+literal))?'childhood':'unspecified';
      const out=fieldScopeValid('SK04-E1',{state:'known',value:literal,evidence:e,scope:{subject:'family',period,relation_evidence:e}});
      if(out){accepted['SK04-E1']=out;notices.push({field_id:'SK04-E1',rule:'literal_family_to_narrator_education_action'});break;}
    }
  }
  // Validate cached records against this question's original sources before merging.
  const previous={};
  for(const[id,obj]of Object.entries(context.previous_fields||{})) {
    if(fields[id]?.question_id!==qid) {errors.push('cross_question_previous_field:'+id);continue;}
    const out=fieldScopeValid(id,obj,true);if(out)previous[id]=out;
  }
  for(let i=errors.length-1;i>=0;i--) {
    const id=errors[i].split(':')[0];if(fields[id]?.question_id===qid&&fields[id].requirement==='optional') {optionalErrors.unshift(errors[i]);errors.splice(i,1);}
  }
  for(const f of defs) {
    const id=f.id, old=previous[id], fresh=accepted[id];
    if(old&&old.state!=='missing')map[id]=old;
    if(!fresh||fresh.state==='missing') {if(old)provenance[id]='reused_same_question';continue;}
    if(!old||old.state==='missing') {map[id]=fresh;continue;}
    const sameProof=JSON.stringify(old.evidence)===JSON.stringify(fresh.evidence);
    const explicitCorrection=Array.isArray(fresh.supersedes)&&(old.evidence||[]).every(e=>fresh.supersedes.includes(e.source_id));
    if(explicitCorrection){map[id]=fresh;map[id].history=[...(old.history||[]),old];provenance[id]='explicit_same_question_correction';continue;}
    if(old.state==='known'&&fresh.state==='known'&&JSON.stringify(old.value)!==JSON.stringify(fresh.value)) {
      const shared=old.evidence.some(a=>fresh.evidence.some(b=>a.source_id===b.source_id&&(a.quote.includes(b.quote)||b.quote.includes(a.quote))));
      if(shared){map[id]=fresh;map[id].statements=mergeStatements(old,fresh);provenance[id]='same_grounded_claim_or_span_extension';}
      else if(['time','place','name','duration','stance'].includes(f.type)) {map[id]=fresh;map[id].history=[...(old.history||[]),old];map[id].state='conflict';map[id].value=null;provenance[id]='changed_fact_requires_clarification';}
      else {map[id]=fresh;map[id].statements=mergeStatements(old,fresh);provenance[id]='compatible_same_question_statements';}
    } else if(old.state==='known'&&fresh.state==='none'&&!sameProof) {map[id]=fresh;map[id].history=[...(old.history||[]),old];map[id].state='conflict';provenance[id]='affirmation_denial_conflict';}
    else {map[id]=fresh;if(!sameProof)map[id].history=[...(old.history||[]),old];}
    if(old.stage_binding&&fresh.state==='known'&&JSON.stringify(old.evidence)===JSON.stringify(fresh.evidence)&&JSON.stringify(old.scope.relation_evidence)===JSON.stringify(fresh.scope.relation_evidence)) {
      map[id].stage_binding=clone(old.stage_binding);
      if(old.stage_binding.state!=='known'){map[id].state='ambiguous';map[id].unbound_value=fresh.value;map[id].value=null;map[id].clarifications=['period'];map[id].provenance='required_stage_not_grounded';}
    }
  }
  // Reuse only a proven same-material stage terminal, never a question-wide unknown.
  const phaseFocus=context.focus?.field_id,phaseOld=previous[phaseFocus],phaseFresh=accepted[phaseFocus];
  const sameMaterial=(a,b)=>{
    if(!a||!b||a.scope.subject!==b.scope.subject)return false;
    if(JSON.stringify(a.evidence)!==JSON.stringify(b.evidence))return false;
    return a.evidence.length===1&&!/[。！？!?][\s\S]*\S/.test(a.evidence[0].quote.replace(/[。！？!?]\s*$/,''))&&!/(另一件|另一个|另一年|后来|与此同时|之后|[一二三四五六七八九十百0-9几多]+年后)/.test(normalize(a.evidence[0].quote));
  };
  if(phaseOld?.provenance==='required_stage_not_grounded'&&phaseFresh&&['unknown','declined','deferred'].includes(phaseFresh.state)&&phaseFresh.evidence.some(e=>e.source_id===last?.id&&sm.get(e.source_id)?.question===STAGE_QUESTION)) {
    for(const f of defs) {
      const old=previous[f.id];
      if(old?.provenance!=='required_stage_not_grounded'||f.scope.stage_binding_required!==fields[phaseFocus].scope.stage_binding_required||!(f.id===phaseFocus||sameMaterial(old,phaseOld)))continue;
      if(accepted[f.id]?.state==='known'&&!sameMaterial(accepted[f.id],old))continue;
      map[f.id]=clone(old);map[f.id].stage_binding={stage:f.scope.stage_binding_required,state:phaseFresh.state,evidence:clone(phaseFresh.evidence),origin_target:phaseFocus};
      map[f.id].provenance='required_stage_not_grounded';provenance[f.id]='reused_same_material_stage_terminal';
      notices.push({field_id:f.id,rule:'same_material_stage_terminal_only',origin_target:phaseFocus});
    }
  }
  // A stage label proposed by the model is not evidence that an otherwise valid fact fits this question.
  for(const f of defs)if(f.scope.stage_binding_required&&map[f.id].state==='known'&&map[f.id].stage_binding?.state!=='known') {
    const obj=map[f.id],stage=f.scope.stage_binding_required,proof=normalize(refsText(obj.scope.relation_evidence));
    const actualQuestions=obj.evidence.map(e=>sm.get(e.source_id)?.question||'');
    const actualMain=actualQuestions.some(t=>t===baseQuestion[qid]);
    const questionText=normalize(actualQuestions.join(' '));
    let anchored=false;
    if(stage==='youth') {
      const refs=obj.scope.relation_evidence, own=obj.evidence;
      const destinations=t=>[...normalize(t).matchAll(/(?:分配到|任教于|到了|到|去|赴)([\u4e00-\u9fff]{2,12}?)(?=教书|工作|任教|生活|定居|去|[，。！？;；])/g)].map(m=>m[1]).filter(t=>!/(哪里|那里|这里|该学校|那所学校|这个地方|别的地方)/.test(t));
      const sameLiteralArrival=(a,b)=>destinations(a).some(x=>destinations(b).some(y=>x===y));
      const groundedRefs=refs.filter(r=>own.some(e=>e.source_id===r.source_id&&(r.quote.includes(e.quote)||e.quote.includes(r.quote)))||refs.some(e=>own.some(v=>e.source_id===v.source_id)&&((obj.scope.object&&obj.scope.object.length>=2&&!/^(学校|单位|工作|地方|生意|家庭|公司)$/.test(obj.scope.object)&&r.quote.includes(obj.scope.object)&&e.quote.includes(obj.scope.object))||sameLiteralArrival(r.quote,e.quote)))||own.some(e=>{
        const from=sources.findIndex(s=>s.id===r.source_id),to=sources.findIndex(s=>s.id===e.source_id);
        return to===from+1&&/(那时|当时|那几年|那段|刚到那|刚到这|初到那|到该|那所|那家)/.test(normalize(sm.get(e.source_id)?.question||''));
      }));
      const selfClauses=groundedRefs.flatMap(r=>normalize(r.quote).split(/[，,。！？；;\n]/)).filter(t=>!/(父亲|母亲|爸爸|妈妈|爷爷|奶奶|祖父|祖母|儿子|女儿|孩子|他|她)/.test(t)||/(?:我|本人)(?:那年|当时|那时|年仅|只有|才|刚|是|在|约|大概)?\s*(?:[0-9一二三四五六七八九十]{1,4}(?:多|来|几)?岁|青年|年轻|年少|中年|晚年|老年|退休)/.test(t));
      const ownStage=selfClauses.join(' ');
      const targetClauses=selfClauses.filter(t=>scalarTexts(obj.value).some(v=>t.includes(normalize(v))||normalize(v).includes(t))).join(' ');
      const counterStage=/(中年|晚年|老年)/.test(targetClauses)||/(?:退休.{0,8}(?:[5-9]\d|[五六七八九]十)(?:多|来|几)?岁|(?:[5-9]\d|[五六七八九]十)(?:多|来|几)?岁.{0,8}退休)/.test(targetClauses);
      if(counterStage) {
        result.unbound_material.push({field_id:f.id,missing_relation:'explicit_other_stage_than_youth',candidate:clone(obj)});
        map[f.id]=missing();provenance[f.id]='explicit_other_stage_not_target';notices.push({field_id:f.id,rule:'retain_outside_stage_material_without_reasking_known_period'});continue;
      }
      const directedStage=refs.some(e=>sm.get(e.source_id)?.question===STAGE_QUESTION&&sm.get(e.source_id)?.target_field_id===f.id&&stageAnswerMatches(stage,e.quote));
      anchored=directedStage||actualMain||/(?:我(?:们)?|本人|当年|当时|那时|那年|年纪|正值|都|还很).{0,8}(?:年轻|年少)(?=人|时|的|了|[，,。！？;； ]|$)|(?:我(?:们)?|本人|当年|当时|那时|那年|正值).{0,8}青年(?=[，,。！？;； ]|$)|(?:青年|年少)(?:时期|时代|时|岁月|们)|年轻(?:的)?时候/.test(ownStage+' '+questionText)||/(?:我|本人|当时|那时|那年)(?:那年|当时|那时|年仅|只有|才|刚|是|在|约|大概)?\s*(?:1[5-9]|2\d|3[0-9]|十[五六七八九]|二十.{0,2}|三十.{0,2})(?:多|来|几)?岁/.test(ownStage);
      // A joint citation is not a license to borrow an age from another event.
      // Inspect the frame up to the selected answer, not later life context.
      const selected=scalarTexts(obj.value).map(normalize);
      const targetIndices=selfClauses.map((t,i)=>t.trim()&&selected.some(v=>t.includes(v)||v.includes(t))?i:-1).filter(i=>i>=0);
      const frame=selfClauses.slice(0,targetIndices.length?Math.max(...targetIndices)+1:0).join('，');
      const resets=[...frame.matchAll(/许多年(?:后|以后)|多年(?:后|以后|之后)|几十年(?:后|以后|之后)|退休(?:后|以后|之后)|(?:我|本人)(?:那年|当时|那时|年仅|已经|是|到了)?\s*(?:[4-9]\d|[四五六七八九]十.{0,2})(?:多|来|几)?岁/g)];
      const lastReset=resets.at(-1);
      const localYouth=/(?:我|本人|那时|当时|那年|正值|我们).{0,8}(?:年轻|青年|年少)|(?:我|本人|当时|那时|那年)(?:那年|当时|那时|年仅|只有|才|刚|是|在|约|大概)?\s*(?:1[5-9]|2\d|3[0-9]|十[五六七八九]|二十.{0,2}|三十.{0,2})(?:多|来|几)?岁/;
      if(lastReset&&!localYouth.test(frame.slice(lastReset.index+lastReset[0].length))) {
        anchored=false;
        notices.push({field_id:f.id,rule:'earlier_stage_does_not_cross_later_event_frame'});
      }
    }
    if(stage==='now') {
      const check=require('./stage-proof').current(obj,sources,normalize);
      anchored=check.anchored;
      if(!anchored)notices.push({field_id:f.id,rule:'selected_current_stage_frame_not_grounded',...check});
    }
    if(anchored&&obj.scope.period!==stage) {
      const originalPeriod=obj.scope.period;obj.scope.period=stage;normalizations.push({field_id:f.id,rule:'grounded_required_stage_period_label',original_period:originalPeriod,grounded_period:stage});
    }
    if(!anchored) {
      result.unbound_material.push({field_id:f.id,missing_relation:stage+'_stage',candidate:clone(obj)});
      obj.unbound_value=obj.value;obj.state='ambiguous';obj.value=null;obj.scope.period='unspecified';obj.clarifications=[...new Set([...(obj.clarifications||[]),'period'])];obj.provenance='required_stage_not_grounded';
      provenance[f.id]='required_stage_not_grounded';notices.push({field_id:f.id,rule:'retain_literal_material_and_clarify_required_stage'});
    }
  }
  // A verified answer to the one stage question also binds only the already-proven
  // same material. Preserve its original content rather than replacing it by an age.
  const confirmed=map[phaseFocus],stageRefs=phaseFresh?.scope?.relation_evidence?.filter(e=>e.source_id===last?.id&&sm.get(e.source_id)?.question===STAGE_QUESTION)||[];
  if(phaseOld?.provenance==='required_stage_not_grounded'&&confirmed?.state==='known'&&stageRefs.length&&stageAnswerMatches(fields[phaseFocus].scope.stage_binding_required,refsText(stageRefs))) {
    for(const f of defs) {
      const old=previous[f.id];
      if(old?.provenance!=='required_stage_not_grounded'||f.scope.stage_binding_required!==fields[phaseFocus].scope.stage_binding_required||!(f.id===phaseFocus||sameMaterial(old,phaseOld)))continue;
      if(f.id!==phaseFocus&&accepted[f.id]?.state==='known'&&!sameMaterial(accepted[f.id],old))continue;
      if(f.id!==phaseFocus){map[f.id]=clone(old);map[f.id].state='known';map[f.id].value=map[f.id].unbound_value;delete map[f.id].unbound_value;map[f.id].scope.period=f.scope.stage_binding_required;map[f.id].scope.relation_evidence.push(...clone(stageRefs));delete map[f.id].clarifications;}
      map[f.id].stage_binding={stage:f.scope.stage_binding_required,state:'known',evidence:clone(stageRefs),origin_target:phaseFocus};
      map[f.id].provenance='same_material_confirmed_stage';provenance[f.id]='same_material_confirmed_stage';notices.push({field_id:f.id,rule:'same_material_confirmed_stage',origin_target:phaseFocus});
    }
  }
  function mergeStatements(a,b) {
    const items=[...(a.statements||scalarTexts(a.value).map(text=>({text,evidence:a.evidence,scope:a.scope}))),...(b.statements||scalarTexts(b.value).map(text=>({text,evidence:b.evidence,scope:b.scope})))];
    return [...new Map(items.map(i=>[JSON.stringify([i.text,i.evidence]),i])).values()];
  }
  // An explicit, narrowly scoped absence of the premise closes only this question.
  const app=map[qid+'-A1'];let absentPremise=false,unavailablePremise=false;
  if(app&&app.state!=='missing') {
    if(app.state==='none') {
      if(!new RegExp(q.premise.no_premise_pattern).test(normalize(refsText(app.evidence))))errors.push(qid+'-A1:absence_does_not_prove_premise');
      else absentPremise=true;
    }
    unavailablePremise=['unknown','declined','deferred'].includes(app.state);
  }
  if(absentPremise)for(const f of defs)if(!['optional','input'].includes(f.requirement)&&f.id!==qid+'-A1'&&map[f.id].state==='missing') {
    map[f.id]={state:'not_applicable',value:null,evidence:clone(app.evidence),scope:clone(app.scope),provenance:'explicit_same_question_premise_absence'};
    provenance[f.id]='explicit_same_question_premise_absence';
  }
  // Endorsement has an object: without an accepted reported trait there is
  // no verified trait for this stance to endorse. Preserve the raw candidate.
  for(const f of defs)if(f.type==='stance'&&f.activation.reported_without_self) {
    const parent=f.activation.reported_without_self[0];
    if(map[f.id].state==='known'&&map[parent]?.state!=='known') {
      const reason='endorsement_without_accepted_evaluation';
      rejected.push({field_id:f.id,reason,candidate:clone(map[f.id])});
      result.semantic_rejections.push({field_id:f.id,reason,retained_state:'missing_or_validated_previous'});
      notices.push({field_id:f.id,rule:reason,parent_field:parent});
      map[f.id]=missing();provenance[f.id]=reason;
    }
  }
  for(const f of defs)effective[f.id]=map[f.id].stage_binding?.state||map[f.id].state;
  const sharedSpan=(a,b)=>a.some(x=>b.some(y=>{
    if(x.source_id!==y.source_id)return false;const text=sm.get(x.source_id)?.text;if(!text)return false;
    for(let i=text.indexOf(x.quote);i>=0;i=text.indexOf(x.quote,i+1))for(let j=text.indexOf(y.quote);j>=0;j=text.indexOf(y.quote,j+1))if(Math.max(i,j)<Math.min(i+x.quote.length,j+y.quote.length))return true;
    return false;
  }));
  for(const[id,anchor]of [['SK01-E3.place','SK01-E4'],['SK01-E3.period','SK01-E4'],['SK04-E2.actor','SK04-E1'],['SK04-E2.period','SK04-E1']]) {
    if(map[id]?.state==='known'&&map[anchor]?.state==='known'&&!isFocused(id,map[id].evidence)&&!sharedSpan(map[id].scope.relation_evidence,map[anchor].evidence))errors.push(id+':binding_belongs_to_another_statement');
  }
  // A reported trait becomes self description only with the narrator's actual endorsement.
  if(qid==='SK05'&&effective['SK05-R1']==='known'&&effective['SK05-E1']==='missing') {
    const attitude=map['SK05-E2'];
    if(attitude.state==='known'&&['agree','partial'].includes(attitude.stance)) {
      map['SK05-E1']={...clone(map['SK05-R1']),scope:{...clone(map['SK05-R1'].scope),subject:'self',relation_evidence:[...map['SK05-R1'].scope.relation_evidence,...attitude.scope.relation_evidence]},provenance:'reported_trait_plus_self_endorsement'};
      effective['SK05-E1']='known';provenance['SK05-E1']='reported_trait_plus_self_endorsement';
    } else if(['unknown','declined','deferred'].includes(attitude.state)){effective['SK05-E1']=attitude.state;provenance['SK05-E1']='self_endorsement_unavailable';}
  }
  // Explanation links are checked against values accepted in this question, including its cache.
  for(const f of defs)if(f.link&&map[f.id].state==='known') {
    const obj=map[f.id], target=map[f.link.field_id], targets=scalarTexts(target?.value).flatMap(v=>[v,...v.split(/[、，,；;]|(?:和|与|及)/).map(t=>t.trim()).filter(Boolean),...(fields[f.link.field_id]?.type==='life_summary'&&v.trim().split(/\s+/u).length>1&&v.trim().split(/\s+/u).every(t=>/^[\p{Script=Han}]+$/u.test(t))?v.trim().split(/\s+/u):[]),...Array.from(v.matchAll(/[“「『‘"]([^”」』’"\n]+)[”」』’"]/g),m=>m[1])]);
    const legacy=Array.isArray(obj.value)?obj.value.flatMap(v=>(v.keywords||[]).map(value=>({field_id:f.link.field_id,value}))):[];
    const links=obj.links||legacy;
    const proof=normalize(refsText(obj.scope.relation_evidence));
    let durationObjectSubspan=false;
    const resolveLink=l=>{
      if(l.field_id!==f.link.field_id)return false;
      if(targets.includes(l.value))return true;
      const scriptMatches=[...new Set(targets.filter(v=>normalizeScript(v)===normalizeScript(l.value)))];
      if(scriptMatches.length===1&&normalizeScript(refsText(obj.scope.relation_evidence)).includes(normalizeScript(scriptMatches[0]))) {
        const proposed=l.value;l.value=scriptMatches[0];normalizations.push({field_id:f.id,rule:'script_link_resolves_unique_accepted_original_word',original_value:proposed,accepted_original:l.value});return true;
      }
      if(!f.link.require_same_object_evidence||l.value.trim().length<2)return false;
      // A duration can cite the literal work+extent part inside a longer work
      // answer. Bare numbers/units do not identify the selected work.
      const literal=normalize(l.value);
      const nested=f.type==='duration'&&literal.length>=12&&/(?:工作|做|干|任职|教|经营|修|务农|务工|从事)/.test(literal)&&proof.includes(literal)&&
        scalarTexts(target?.value).filter(v=>v.includes(l.value)).length===1&&
        obj.scope.relation_evidence.some(e=>e.quote.includes(l.value)&&target.evidence.some(p=>p.source_id===e.source_id&&p.quote.includes(e.quote)));
      if(nested) {
        durationObjectSubspan=true;
        notices.push({field_id:f.id,rule:'literal_work_duration_subspan_binds_selected_work',link_value:l.value});
        return true;
      }
      const matches=scalarTexts(target?.value).filter(v=>v.includes(l.value)&&proof.includes(normalize(v)));
      if(matches.length!==1)return false;
      notices.push({field_id:f.id,rule:'literal_object_subspan_resolves_same_selected_object',link_value:l.value,selected_value:matches[0]});
      return true;
    };
    if(target?.state!=='known'||!links.length||links.some(l=>!resolveLink(l)))errors.push(f.id+':unbound_explanation_link');
    if(f.type==='explanation'&&scalarTexts(obj.value).some(v=>targets.includes(v)))errors.push(f.id+':repetition_is_not_explanation');
    if(f.link.require_same_object_evidence&&!isFocused(f.id,obj.evidence)) {
      const object=normalize(obj.scope.object||'');
      const baseMatch=targets.some(v=>proof.includes(normalize(v)));
      const objectMatch=object.length>=2&&targets.some(v=>normalize(v).includes(object))&&proof.includes(object);
      if(!baseMatch&&!objectMatch&&!durationObjectSubspan)errors.push(f.id+':reason_not_bound_to_same_selected_object');
    }
  }
  const statesFor=ids=>ids.map(id=>effective[id]);
  function active(f) {
    if(['optional','input'].includes(f.requirement))return false;
    if(absentPremise)return f.id===qid+'-A1';
    if(unavailablePremise)return f.id===qid+'-A1';
    const a=f.activation||{};
    if(a.never_ask)return false;
    if(a.premise_check)return !defs.some(d=>d.id!==f.id&&d.requirement!=='optional'&&map[d.id].state!=='missing');
    if(a.known)return statesFor(a.known).every(s=>s==='known');
    if(a.any_known)return statesFor(a.any_known).some(s=>s==='known');
    if(a.unless_none)return !statesFor(a.unless_none).some(s=>['none','not_applicable'].includes(s));
    if(a.reported_without_self)return effective[a.reported_without_self[0]]==='known'&&effective[a.reported_without_self[1]]!=='known';
    for(const[key,flag]of [['if_ambiguous_referent','referent'],['if_ambiguous_actor','actor'],['if_ambiguous_period','period'],['if_ambiguous_meaning','meaning'],['if_ambiguous_link','link']]) {
      if(a[key])return a[key].some(id=>map[id]?.clarifications?.includes(flag))||context.focus?.field_id===f.id;
    }
    return !!a.always||f.required;
  }
  result.active=defs.filter(active).map(f=>f.id);
  // An unusable, unsolicited candidate for an inactive clarification cannot
  // force a question or store a fact. Keep its complete rejection audit while
  // retaining valid required answers. Active conditions remain strict errors.
  const inactiveIds=new Set(defs.filter(f=>f.requirement==='conditional'&&!result.active.includes(f.id)).map(f=>f.id));
  for(let i=errors.length-1;i>=0;i--) {
    const fid=errors[i].split(':',1)[0];
    if(!inactiveIds.has(fid))continue;
    // A user correction must be resolved, never hidden by an old cached value.
    if(CORRECTION.test(normalize(last?.text||'')))continue;
    result.inactive_conditional_errors.unshift(errors[i]);errors.splice(i,1);
    if(previous[fid]&&previous[fid].state!=='missing') {
      map[fid]=clone(previous[fid]);effective[fid]=previous[fid].state;provenance[fid]='validated_cache_survives_invalid_inactive_candidate';
    } else {
      map[fid]=missing();effective[fid]='missing';provenance[fid]='invalid_inactive_conditional_candidate_rejected';
    }
  }
  result.active=defs.filter(active).map(f=>f.id);
  // A validated current pause takes priority even when extraction has independent errors.
  if(ctrlValid&&control.action==='pause'){result.decision='paused';return result;}
  if(errors.length)return result;
  if(ctrlValid&&control.action==='skip_question'){result.decision='skipped';return result;}
  if(ctrlValid&&control.action==='defer_question'){result.decision='deferred';return result;}
  let pending=result.active.filter(id=>UNRESOLVED.has(effective[id]));
  let target=pending.find(id=>['ambiguous','conflict'].includes(effective[id]));
  if(!target&&qid==='SK05'&&pending.includes('SK05-E2'))target='SK05-E2';
  if(!target&&q.premise&&pending.includes(qid+'-A1'))target=qid+'-A1';
  if(!target)target=pending[0];
  if(target) {
    result.target=target;
    if((context.ask_counts||{})[target]>=2){result.decision='ask_defer';result.question='这一点我们先放一放，可以吗？';return result;}
    result.decision='ask';result.question=fields[target].question;
    if(map[target].provenance==='required_stage_not_grounded')result.question=STAGE_QUESTION;
    if(effective[target]==='conflict')result.question='刚才这一点有两种说法，您想采用哪一种？';
    if(target==='SK06-E2'&&map['SK06-E1'].state==='known')result.question='您为什么会用“'+scalarTexts(map['SK06-E1'].value)[0]+'”来形容这一生？';
    return result;
  }
  if(result.active.some(id=>!TERMINAL.has(effective[id]))){errors.push('unknown_effective_state');return result;}
  const limited=absentPremise||unavailablePremise||(qid==='GR01'&&effective['GR01-E1']==='none')||result.active.some(id=>!['known','none'].includes(effective[id]));
  result.decision=limited?'limited':'ready';
  return result;
}
function literalLinkCandidates(payload,known) {
  const rows=[];
  for(const [id,def] of Object.entries(payload.field_contract||{})) {
    const link=fields[id]?.link,parent=link&&known?.[link.field_id];
    if(!link||parent?.state!=='known')continue;
    const units=(payload.evidence_units||[]).filter(u=>(parent.evidence||[]).some(e=>e.source_id===u.source_id&&(e.quote.includes(u.text)||u.text.includes(e.quote))));
    rows.push({field_id:id,parent_field_id:link.field_id,literal_values:scalarTexts(parent.value),parent_units:clone(units),unverified_semantics:true,
      instruction:'Literal same-question link syntax only; not new evidence or a semantic endorsement. Use only when original answer truly explains the selected object. Include required original object and reason proof.'});
  }
  return rows;
}
function modelInput(payload) {
  const out=clone(payload);delete out.current_question;delete out.ask_counts;
  out.task='extract_answers_for_target_field_questions_from_recorded_material';
  out.allowed_evidence_unit_ids=(payload.evidence_units||[]).map(u=>u.id);
  out.nonknown_protocol_example={state:'ambiguous',value:null,evidence_unit_ids:['CHOOSE_AN_ACTUAL_ALLOWED_ID'],scope:{subject:'CHOOSE_ONE_CONTRACT_SUBJECT',period:'as_stated',relation_unit_ids:'same_as_evidence'},clarifications:['referent']};
  out.literal_link_candidates=literalLinkCandidates(payload,payload.previous_fields);
  out.task_note='main_question and field_contract define extraction targets. sources.question is a historical context for interpreting short answers, not the question to answer or summarize.';
  return out;
}
function fieldVerification(payload,id,draft) {
  // The helper first checks all question/field boundaries. The raw A draft
  // remains unverified input; code checking it never inserts it into memory.
  const out=require('./field-steps').verification(payload,id,draft);
  const own=draft&&typeof draft==='object'&&!Array.isArray(draft)&&draft.fields&&typeof draft.fields==='object'&&!Array.isArray(draft.fields)?draft.fields[id]:undefined;
  const prior={...clone(payload.previous_fields||{}),...clone(payload.related_fields||{})};
  const checked=analyze(payload.question_id,payload.sources,
    {control:{action:'continue',evidence_unit_ids:[]},fields:own===undefined?{}:{[id]:own}},
    {current_question:payload.current_question,focus:payload.focus,previous_fields:prior,ask_counts:payload.ask_counts});
  const field=checked.fields[id]||missing();
  out.semantic_review.candidate_validation={candidate_present:own!==undefined,
    field_state:field.state,provenance:field.provenance||checked.provenance[id]||null,
    expected_stage:fields[id].scope.stage_binding_required||null,
    clarifications:clone(field.clarifications||[]),
    rejection_reasons:checked.rejected_candidates.filter(r=>r.field_id===id).map(r=>r.reason),
    errors:checked.errors.filter(e=>e.startsWith(id+':')||!e.includes(':')),
    had_previous_target:Boolean(payload.previous_fields?.[id]),
    instruction:'Code feedback is not evidence or verified memory. Recheck every assertion against the original source; resolve a bad candidate from existing material before any human follow-up.'};
  return out;
}
function reviewInput(modelInput,candidate,checked) {
  const out=clone(modelInput),errors=[...(checked.errors||[]),
    ...(checked.semantic_rejections||[]).map(x=>x.field_id+':'+x.reason),
    ...(checked.unbound_material||[]).map(x=>x.field_id+':'+x.missing_relation)];
  const stageSearch=[];
  const lastSource=modelInput.sources?.at(-1)?.id;
  for(const gap of checked.unbound_material||[]) {
    const stage=fields[gap.field_id]?.scope.stage_binding_required;
    if(!stage||gap.missing_relation!==stage+'_stage')continue;
    const marker=stage==='youth'?/(?:年轻|年少)(?=人|时|的|了|[，,。！？;； ]|$)|青年(?:时期|时代|时|岁月)|[0-9一二三四五六七八九十]{1,4}(?:多|几)?岁/:
      stage==='now'?/(?:现在|目前|如今|最近|近来|当下|平时|日常)/:null;
    if(!marker)continue;
    const units=(modelInput.evidence_units||[]).filter(u=>typeof u.text==='string'&&marker.test(normalize(u.text)))
      .map(clone).sort((a,b)=>Number(b.source_id===lastSource)-Number(a.source_id===lastSource));
    stageSearch.push({field_id:gap.field_id,required_stage:stage,unverified:true,units,
      instruction:'Search hints only, not verified stage or same-event proof. Read each full source and actual question. Select the action and its own stage together; a name, another person, or another event cannot supply this stage.'});
  }
  out.semantic_review={unverified_candidate:clone(candidate??null),
    code_validation_errors:[...new Set(errors)],
    stage_search_candidates:stageSearch,
    literal_link_candidates:literalLinkCandidates(modelInput,checked.fields),
    candidate_validation:Object.fromEntries(Object.entries(checked.fields||{}).map(([id,f])=>[id,
      {state:f.state,provenance:f.provenance||checked.provenance?.[id]||null,
       expected_stage:fields[id]?.scope.stage_binding_required||null,clarifications:clone(f.clarifications||[])}])),
    instruction:'Audit all fields against own sources and contract, including omissions; no gold supplied. Code feedback is not source evidence or a verified memory. An ambiguous or unbound candidate has not passed: reread newer material and choose genuinely grounded evidence, not the old evidence with a changed scope label. Resolve rejected candidates from existing source material before any human follow-up.'};
  return out;
}
module.exports={reviewInput,fieldVerification,version:contracts.version,fields,baseQuestion,getContract,buildPayload,analyze,modelInput,reviewPlan:require('./field-review').plan,assembleFieldReviews:require('./field-review').assemble,repairContext:(payload,result)=>require('./field-steps').repairContext(payload,result,fields),stepFrontier:require('./field-steps').frontier,controlStep:payload=>require('./field-steps').control(payload,normalize),evidenceUnits:(qid,sources)=>evidenceUnits.catalog(qid,sources).map(({id,source_id,text})=>({id,source_id,text})),parseProposal:require('./proposal-parser').parseProposal};
