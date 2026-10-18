'use strict';
// Synthetic property checks across all field contracts. No DS calls, no gold data.
const path=require('path'),fs=require('fs');
const engine=path.resolve(process.argv[2]||'docs/prototypes/full-interview-v1/candidate18-atomic-deliberate/engine.js');
const G=require(engine),checks=[];
const ref=(quote,id='local')=>({source_id:id,quote});
const source=(qid,text,question,target,speaker='narrator')=>[{id:'local',question_id:qid,speaker,text,question,target_field_id:target}];
const proposal=(fields={},control={action:'continue',evidence:[]})=>({control,fields});
function test(name,fn){try{fn();checks.push({name,pass:true});}catch(e){checks.push({name,pass:false,error:e.message});}}
for(const [fid,f] of Object.entries(G.fields)){
 const qid=f.question_id;
 const candidate=(state,text,value=null)=>({state,value,evidence:[ref(text)],scope:{subject:f.scope.subjects[0],period:f.scope.period||'as_stated',relation_evidence:[ref(text)]}});
 test(fid+' forged source reference cannot create a fact',()=>{
  const t='这段是原话。',a=candidate('known',t,t);a.evidence=[ref(t,'invented')];
  const r=G.analyze(qid,source(qid,t,f.question,fid),proposal({[fid]:a}));if(r.fields[fid]?.state==='known')throw Error('forged fact stored');
 });
 test(fid+' interviewer words cannot become narrator fact',()=>{
  const t='这是采访者的话。',r=G.analyze(qid,source(qid,t,f.question,fid,'interviewer'),proposal({[fid]:candidate('known',t,t)}));if(r.fields[fid]?.state==='known')throw Error('interviewer fact stored');
 });
 test(fid+' unrelated literal cannot close field as unknown',()=>{
  const t='这里只记录了一个普通片段。',r=G.analyze(qid,source(qid,t,f.question,fid),proposal({[fid]:candidate('unknown',t)}));if(r.fields[fid]?.state==='unknown')throw Error('unsupported unknown stored');
 });
 if(f.question&&f.allowed_states.includes('unknown'))test(fid+' explicit target unknown survives resume without reasking this field',()=>{
  const t='我记不清这一点了。',ss=source(qid,t,f.question,fid),r=G.analyze(qid,ss,proposal({[fid]:candidate('unknown',t)}),{current_question:f.question,focus:{field_id:fid}});
  if(r.fields[fid]?.state!=='unknown')throw Error('explicit unknown not stored: '+r.errors.join(','));
  const later=G.analyze(qid,ss,proposal(),{previous_fields:r.fields,current_question:'还有补充吗？',ask_counts:{[fid]:2}});
  if(later.fields[fid]?.state!=='unknown')throw Error('unknown lost at resume: '+later.errors.join(','));
  if(later.target===fid)throw Error('closed target reasked');
 });
}
for(const qid of Object.keys(G.baseQuestion)){
 test(qid+' verified current pause takes priority over independent extraction error',()=>{
  const t='今天先到这里。',r=G.analyze(qid,source(qid,t,G.baseQuestion[qid],null),proposal({not_a_field:{state:'known'}},{action:'pause',evidence:[ref(t)]}));if(r.decision!=='paused'||r.question)throw Error('pause not honored');
 });
 test(qid+' foreign question cache cannot be reused',()=>{
  const other=Object.keys(G.fields).find(id=>G.fields[id].question_id!==qid),t='这是一段口述。';
  const r=G.analyze(qid,source(qid,t,G.baseQuestion[qid],null),proposal(),{previous_fields:{[other]:{state:'missing',value:null,evidence:[]}}});if(r.decision!=='invalid')throw Error('foreign cache not rejected');
 });
}
const result={kind:'synthetic_all_contract_boundaries',runtime:G.version,field_contracts:Object.keys(G.fields).length,question_contracts:Object.keys(G.baseQuestion).length,tests:checks.length,passed:checks.filter(x=>x.pass).length,failed:checks.filter(x=>!x.pass),no_DS_calls:true};
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify({...result,checks},null,2)+'\n');
console.log(JSON.stringify(result,null,2));process.exitCode=result.failed.length?1:0;
