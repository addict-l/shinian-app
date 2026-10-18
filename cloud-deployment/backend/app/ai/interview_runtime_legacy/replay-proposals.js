'use strict';
// Replays already-public development proposals only. This is a code regression audit,
// not a new model run, a gold comparison, or an accuracy estimate.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),G=require('./engine');
const roots=process.argv.slice(2),records=[];
for(const root of roots)for(const name of fs.readdirSync(root).sort()) {
  const caseDir=path.join(root,name);if(!fs.statSync(caseDir).isDirectory())continue;
  for(const turn of fs.readdirSync(caseDir).filter(t=>t.startsWith('turn-')).sort()) {
    const dir=path.join(caseDir,turn);
    for(const name of fs.readdirSync(dir).filter(t=>/^engine-input-.*\.json$/.test(t)).sort()) {
      const filename=path.join(dir,name),raw=fs.readFileSync(filename,'utf8'),input=JSON.parse(raw),p=input.payload;
      let proposal=input.proposal,parseAudit=null;
      if(proposal===null&&input.raw_model_response?.raw_content) {
        parseAudit=G.parseProposal(input.raw_model_response.raw_content,{finish_reason:input.raw_model_response.finish_reason});
        if(parseAudit.ok)proposal=parseAudit.proposal;
      }
      const result=G.analyze(p.question_id,p.sources,proposal,{current_question:p.current_question,focus:p.focus,previous_fields:p.previous_fields,ask_counts:p.ask_counts});
      const oldFile=path.join(dir,name.replace('engine-input-','decision-'));
      const old=fs.existsSync(oldFile)?JSON.parse(fs.readFileSync(oldFile,'utf8')):null;
      records.push({input:filename,input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),used_strict_transport_parse:!!parseAudit?.ok,old_decision:old?.decision,new_decision:result.decision,old_errors:old?.errors,new_errors:result.errors,target:result.target,unbound_material:result.unbound_material.map(x=>({field_id:x.field_id,missing_relation:x.missing_relation})),notices:result.scope_notices.map(x=>({field_id:x.field_id,rule:x.rule}))});
    }
  }
}
const report={kind:'known_development_proposal_code_replay',version:G.version,limitations:'Same saved proposals and contexts; no new DeepSeek calls, no gold read or score. Semantic invalid states remain errors. Original runs are immutable.',records};
fs.writeFileSync(path.join(__dirname,'proposal-replay-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({records:records.length,old_invalid:records.filter(r=>r.old_decision==='invalid').length,new_invalid:records.filter(r=>r.new_decision==='invalid').length,changes:records.filter(r=>r.old_decision!==r.new_decision||JSON.stringify(r.old_errors)!==JSON.stringify(r.new_errors)).map(r=>({...r,notices:undefined}))},null,2));
