'use strict';
// Pure field-level review planning/assembly. No model, gold or identity lookup.
const clone=x=>JSON.parse(JSON.stringify(x));
function plan(payload,firstResult) {
  return Object.entries(payload.field_contract).filter(([,f])=>f.requirement!=='optional').map(([fid,f])=>{
    const out=clone(payload);out.field_contract={[fid]:clone(f)};
    out.atomic_review={target_field_id:fid,mode:'independent_source_to_field'};
    out.same_question_targets=Object.fromEntries(Object.entries(payload.field_contract).filter(([id])=>id!==fid).map(([id,d])=>[id,{label:d.label,type:d.type,usable_answer:d.usable_answer}]));
    out.related_fields={};
    const dependencies=new Set([f.link?.field_id,...Object.values(f.activation||{}).filter(Array.isArray).flat()].filter(x=>typeof x==='string'));
    for(const dep of dependencies)if(firstResult.fields?.[dep]&&payload.field_contract[dep])out.related_fields[dep]=clone(firstResult.fields[dep]);
    out.semantic_review={code_validation_errors:[...(firstResult.errors||[]),...(firstResult.semantic_rejections||[]).map(x=>x.field_id+':'+x.reason)].filter(x=>x.startsWith(fid+':')),
      instruction:'Independently locate evidence for this single target field. No expected answers or scores supplied.'};
    return {field_id:fid,payload:out};
  });
}
function assemble(firstProposal,entries) {
  const proposal={control:firstProposal&&Object.prototype.hasOwnProperty.call(firstProposal,'control')?clone(firstProposal.control):null,fields:{}},errors=[];
  const seen=new Set();
  for(const {field_id,output} of entries) {
    if(seen.has(field_id)){errors.push('duplicate_field_review:'+field_id);continue;}seen.add(field_id);
    if(!output||typeof output!=='object'||Array.isArray(output)||!output.fields||typeof output.fields!=='object'||Array.isArray(output.fields)) {errors.push('invalid_field_review_shape:'+field_id);continue;}
    if(Object.keys(output).some(k=>!['control','fields','extra_material'].includes(k)))errors.push('unrecognized_field_review_root:'+field_id);
    if(Object.keys(output.fields).some(k=>k!==field_id)){errors.push('field_review_returned_other_field:'+field_id);continue;}
    if(output.fields[field_id]!==undefined)proposal.fields[field_id]=clone(output.fields[field_id]);
  }
  return {proposal,errors};
}
module.exports={plan,assemble};
