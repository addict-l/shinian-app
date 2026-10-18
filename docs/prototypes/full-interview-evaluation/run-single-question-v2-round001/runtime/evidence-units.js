'use strict';
// Pure source anchoring. No NLP inference, model, gold, storage or cross-question state.
const narrates=s=>!s.speaker||['narrator','user','interviewee','self'].includes(s.speaker);
function catalog(qid,sources) {
  const units=[];
  sources.forEach((s,sourceIndex)=>{
    if(!s||typeof s.id!=='string'||typeof s.text!=='string'||!narrates(s)||s.question_id&&s.question_id!==qid)return;
    const spans=[];let start=0;
    for(const m of s.text.matchAll(/[。！？!?；;\n]+[”’"）)]*/gu)) {
      const end=m.index+m[0].length;
      if(s.text.slice(start,end).trim())spans.push({start,end});
      start=end;
    }
    if(s.text.slice(start).trim())spans.push({start,end:s.text.length});
    spans.forEach((span,index)=>units.push({id:'S'+(sourceIndex+1)+'.'+(index+1),source_id:s.id,index,...span,text:s.text.slice(span.start,span.end)}));
  });
  return units;
}
function resolve(qid,sources,ids) {
  const c=catalog(qid,sources),byId=new Map(c.map(u=>[u.id,u]));
  const list=typeof ids==='string'?[ids]:ids;
  if(!Array.isArray(list)||list.some(id=>typeof id!=='string'||!byId.has(id)))return {ok:false,error:'invalid_or_foreign_evidence_unit'};
  const chosen=new Set(list),picked=c.filter(u=>chosen.has(u.id)),refs=[];
  for(const u of picked) {
    const last=refs.at(-1),src=sources.find(s=>s.id===u.source_id);
    if(last&&last.source_id===u.source_id&&last.last_index+1===u.index&&!src.text.slice(last.end,u.start).trim()) {
      last.end=u.end;last.last_index=u.index;last.quote=src.text.slice(last.start,last.end);
    } else refs.push({source_id:u.source_id,quote:u.text,start:u.start,end:u.end,last_index:u.index});
  }
  return {ok:true,refs:refs.map(({source_id,quote})=>({source_id,quote})),selected_ids:[...chosen]};
}
function expand(qid,sources,candidate,options={}) {
  if(!candidate||typeof candidate!=='object'||Array.isArray(candidate))return {ok:false,error:'invalid_unit_candidate'};
  const out=JSON.parse(JSON.stringify(candidate)),events=[];
  function place(container,key,destination) {
    if(!(key in container))return null;
    const ids=container[key],r=resolve(qid,sources,ids);
    if(!r.ok)return r.error;
    if(container[destination]!==undefined&&JSON.stringify(container[destination])!==JSON.stringify(r.refs))return 'conflicting_unit_and_literal_evidence';
    container[destination]=r.refs;delete container[key];events.push({attribute:key,selected_ids:r.selected_ids,refs:r.refs});return null;
  }
  // Empty missing asserts no fact. Null optional citation placeholders cannot
  // create evidence or invalidate the question before missing is canonicalized.
  if(out.state==='missing'&&(out.value===null||out.value===undefined)&&
     (out.evidence===undefined||Array.isArray(out.evidence)&&!out.evidence.length)&&
     (out.evidence_unit_ids===undefined||Array.isArray(out.evidence_unit_ids)&&!out.evidence_unit_ids.length)&&
     (out.value_unit_ids===undefined||Array.isArray(out.value_unit_ids)&&!out.value_unit_ids.length)&&
     ['relation_unit_ids','object_unit_ids','relation_evidence','object_evidence'].every(k=>
       out.scope?.[k]===undefined||out.scope[k]===null||out.scope[k]==='same_as_evidence'||Array.isArray(out.scope[k])&&!out.scope[k].length)) {
    return {ok:true,candidate:{state:'missing',value:null,evidence:[]},events:[{rule:'canonical_empty_missing_before_unit_resolution'}]};
  }
  // Non-known states make no value assertion. Preserve state and exact
  // evidence, while normalizing omitted/null display-value syntax only.
  // The engine still validates all explicit terminal/ambiguity bases.
  if(['ambiguous','none','unknown','declined','deferred','not_applicable'].includes(out.state)) {
    if(out.value===undefined) {
      out.value=null;events.push({attribute:'value',rule:'explicit_nonknown_missing_value_to_null'});
    }
    if(out.value_unit_ids!==undefined) {
      const selected=resolve(qid,sources,out.value_unit_ids);
      if(!selected.ok)return {ok:false,error:selected.error};
      const cited=resolve(qid,sources,out.evidence_unit_ids||[]);
      if(!cited.ok)return {ok:false,error:cited.error};
      if(selected.selected_ids.some(id=>!cited.selected_ids.includes(id)))return {ok:false,error:'nonknown_display_units_not_in_declared_evidence'};
      if(out.value!==null)return {ok:false,error:'conflicting_nonknown_display_value'};
      delete out.value_unit_ids;
      events.push({attribute:'value_unit_ids',rule:'nonknown_display_units_are_evidence_not_asserted_value',selected_ids:selected.selected_ids});
    }
  }
  if(out.value_unit_ids!==undefined) {
    if(out.state!=='known')return {ok:false,error:'literal_selection_requires_known'};
    const chosen=resolve(qid,sources,out.value_unit_ids);
    if(!chosen.ok)return {ok:false,error:chosen.error};
    if(chosen.refs.length!==1)return {ok:false,error:'literal_value_must_be_one_contiguous_source_span'};
    const value=chosen.refs[0].quote;
    if(out.value!==undefined&&out.value!==value)return {ok:false,error:'conflicting_literal_value_selection'};
    out.value=value;delete out.value_unit_ids;
    events.push({attribute:'value',rule:'copy_selected_contiguous_original_units',selected_ids:chosen.selected_ids,refs:chosen.refs});
  }
  let error=place(out,'evidence_unit_ids','evidence');if(error)return {ok:false,error};
  if(out.scope&&typeof out.scope==='object')for(const [from,to] of [['relation_unit_ids','relation_evidence'],['object_unit_ids','object_evidence']]) {
    if(out.scope[from]==='same_as_evidence') {
      if(out.scope[to]!==undefined&&out.scope[to]!=='same_as_evidence')return {ok:false,error:'conflicting_unit_and_literal_evidence'};
      out.scope[to]='same_as_evidence';delete out.scope[from];events.push({attribute:from,alias:'same_as_evidence'});
    } else {error=place(out.scope,from,to);if(error)return {ok:false,error};}
  }
  // Selected answer units always remain joint relation proof. Additional
  // relation IDs augment them, rather than replacing their already-selected
  // context. Resolve merges only contiguous selected original units.
  if(options.jointProof&&Array.isArray(candidate.evidence_unit_ids)&&out.evidence?.length&&out.scope&&typeof out.scope==='object'&&!Array.isArray(out.scope)) {
    const extra=candidate.scope?.relation_unit_ids;
    if(Array.isArray(extra)) {
      const combined=resolve(qid,sources,[...candidate.evidence_unit_ids,...extra]);
      if(!combined.ok)return {ok:false,error:combined.error};
      out.scope.relation_evidence=combined.refs;
      events.push({attribute:'relation_evidence',rule:'selected_joint_answer_and_extra_relation_units',selected_ids:combined.selected_ids,refs:combined.refs});
    } else if(out.scope.relation_evidence===undefined) {
      out.scope.relation_evidence='same_as_evidence';
      events.push({attribute:'relation_evidence',rule:'selected_joint_proof_units',selected_ids:candidate.evidence_unit_ids});
    } else if(Array.isArray(out.scope.relation_evidence)) {
      const refs=[...out.evidence,...out.scope.relation_evidence];
      if(refs.some(r=>!r||typeof r.source_id!=='string'||typeof r.quote!=='string'||Object.keys(r).some(k=>!['source_id','quote'].includes(k))))return {ok:false,error:'joint_relation_requires_literal_refs'};
      out.scope.relation_evidence=refs.filter((r,i)=>!refs.some((other,j)=>i!==j&&r.source_id===other.source_id&&other.quote.includes(r.quote)&&(other.quote!==r.quote||j<i)));
      events.push({attribute:'relation_evidence',rule:'selected_joint_answer_and_literal_relation_refs',refs:out.scope.relation_evidence});
    }
  }
  return {ok:true,candidate:out,events};
}
module.exports={catalog,resolve,expand};
