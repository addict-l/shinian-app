'use strict';
// All dependencies are field IDs inside ONE question. No cross-question graph.
const F=require('./field-review'),clone=x=>JSON.parse(JSON.stringify(x));
const OWN=Object.fromEntries(require('./contracts.json').questions.flatMap(q=>q.elements.map(f=>[f.id,q.id])));
function frontier(payload,result,doneIds) {
 const done=new Set(doneIds),qid=payload.question_id,all=Object.entries(payload.field_contract);
 if(all.some(([id])=>OWN[id]!==qid)||[...done].some(id=>OWN[id]!==qid))throw Error('foreign_field_in_steps');
 const pending=all.filter(([id,f])=>!done.has(id)&&f.requirement!=='optional');
 const premise=all.find(([,f])=>f.activation?.premise_check)?.[0];
 let ids=[];
 if(pending.some(([id])=>id===premise))ids=[premise];
 else if(result.fields?.[premise]&&['none','not_applicable','unknown','declined','deferred'].includes(result.fields[premise].state))ids=[];
 else {
  const linkedReady=f=>!f.link||result.fields?.[f.link.field_id]?.state==='known';
  ids=pending.filter(([,f])=>['required','input'].includes(f.requirement)&&linkedReady(f)).map(([id])=>id);
  if(!ids.length)ids=pending.filter(([id,f])=>f.requirement==='conditional'&&(result.active||[]).includes(id)&&linkedReady(f)).map(([id])=>id);
 }
 return F.plan(payload,result).filter(p=>ids.includes(p.field_id));
}
function control(payload,normalize) {
 const last=payload.sources.at(-1);
 if(!last)return {needs_model:false,proposal:{control:null,fields:{}},reason:'no_current_source'};
 return {needs_model:true,payload:{task:'classify_current_interview_control',question_id:payload.question_id,main_question:payload.main_question,
  question_context_mode:'independent',sources:[clone(last)],evidence_units:(payload.evidence_units||[]).filter(u=>u.source_id===last.id).map(clone)},reason:'current_intent_contextual_classifier'};
}
module.exports={frontier,control};

// Only pass an engine-generated result. Reuse independently validated fields
// during the ONE internal protocol repair; a missing delta cannot erase them.
function repairContext(payload,result,contracts) {
 const out=clone(payload),qid=payload.question_id;
 const failed=new Set((result.errors||[]).map(e=>e.split(':')[0]).filter(id=>contracts[id]?.question_id===qid));
 const previous=clone(payload.previous_fields||{}),reused=[];
 for(const [id,field] of Object.entries(result.fields||{})) {
  if(contracts[id]?.question_id!==qid||failed.has(id)||field.state==='missing')continue;
  previous[id]=clone(field);reused.push(id);
 }
 out.previous_fields=previous;
 return {payload:out,reused_field_ids:reused,excluded_error_field_ids:[...failed]};
}
module.exports.repairContext=repairContext;

// Fixed second semantic stage. A draft is never added to validated memory.
function verification(payload,fieldId,draft) {
 const qid=payload.question_id;
 if(OWN[fieldId]!==qid||payload.atomic_review?.target_field_id!==fieldId||Object.keys(payload.field_contract).length!==1||!payload.field_contract[fieldId])throw Error('wrong_single_field_audit_target');
 if(Object.keys(payload.previous_fields||{}).some(id=>OWN[id]!==qid)||Object.keys(payload.related_fields||{}).some(id=>OWN[id]!==qid)||payload.sources.some(s=>s.question_id&&s.question_id!==qid))throw Error('foreign_question_in_field_audit');
 const out=clone(payload),own=draft&&typeof draft==='object'&&!Array.isArray(draft)&&draft.fields&&typeof draft.fields==='object'&&!Array.isArray(draft.fields)?draft.fields[fieldId]:undefined;
 out.atomic_review.mode='source_audit_v1';
 out.semantic_review={...(out.semantic_review||{}),unverified_candidate:{fields:own===undefined?{}:{[fieldId]:clone(own)}},
  instruction:'Audit the draft and independently search all own sources for omissions, wrong target concepts, actors, time frames and truncated proof. A draft is not evidence. Return the final answer for this field only.'};
 return out;
}
module.exports.verification=verification;
