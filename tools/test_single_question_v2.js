'use strict';
const assert=require('assert'),path=require('path');
const G=require(path.resolve('docs/prototypes/full-interview-v2/single-question-v2/engine.js'));
const C=G.getContract(),checks=[];
function test(name,fn){try{fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:e.message});}}
const P=(fields={})=>({control:{action:'continue',evidence:[]},fields});
function answer(qid,fid,text,state='known',subject='self',period='as_stated'){
 const s={id:'test',question_id:qid,speaker:'narrator',text,question:G.baseQuestion[qid]};
 const e=[{source_id:'test',quote:text}],f={state,value:state==='known'?text:null,evidence:e,scope:{subject,period,relation_evidence:e}};
 if(G.fields[fid].type==='time')f.precision='year';
 return {s,p:P({[fid]:f})};
}
test('every entry and selectable follow-up is one sentence',()=>{for(const q of C.questions){assert.equal((q.main_question.match(/[？?]/g)||[]).length,1);for(const f of q.elements)if(!f.activation.never_ask)assert.equal((f.question.match(/[？?]/g)||[]).length,1);}});
test('all 62 original topics accounted for',()=>assert.equal(new Set(C.questions.map(q=>q.legacy_question_id)).size,62));
test('field ownership is unique and dependencies cannot cross topics',()=>{const ids=new Set();for(const q of C.questions)for(const f of q.elements){assert(!ids.has(f.id));ids.add(f.id);assert.equal(f.question_id,q.id);for(const dep of [...Object.values(f.activation).filter(Array.isArray).flat(),...(f.link?[f.link.field_id]:[])])assert.equal(G.fields[dep].question_id,q.id);}});
test('birth year alone completes year topic without asking location',()=>{const a=answer('SK01','SK01-E1','1984年','known','self','birth');assert.equal(G.analyze('SK01',[a.s],a.p).decision,'ready');});
test('birthplace short answer binds the actual single entry',()=>{const a=answer('SK01b','SK01-E2','江西宜春','known','self','birth');assert.equal(G.analyze('SK01b',[a.s],a.p).decision,'ready');});
test('other split topic cache remains forbidden',()=>{const r=G.analyze('SK01b',[],P(),{previous_fields:{'SK01-E1':{state:'missing',value:null,evidence:[]}}});assert.equal(r.decision,'invalid');});
test('empty keyword answer asks entry, not reason',()=>{const r=G.analyze('SK06',[],P());assert.equal(r.target,'SK06-E1');});
test('keyword answer activates exactly reason follow-up',()=>{const a=answer('SK06','SK06-E1','操心');assert.equal(G.analyze('SK06',[a.s],a.p).target,'SK06-E2');});
test('unknown keyword does not force why',()=>{const a=answer('SK06','SK06-E1','我想不起来了','unknown');const r=G.analyze('SK06',[a.s],a.p);assert.equal(r.decision,'limited');assert.equal(r.target,null);});
test('upbringing reason stays inactive until entry answered',()=>assert.equal(G.analyze('SK04',[],P()).active.includes('SK04-E3'),false));
test('upbringing answer activates its effect',()=>{const a=answer('SK04','SK04-E1','小时候家里管我很严','known','family','childhood');assert.equal(G.analyze('SK04',[a.s],a.p).target,'SK04-E3');});
test('merged childhood interest has one substantive goal',()=>assert.deepEqual(G.getContract('CH04').elements.filter(f=>f.required).map(f=>f.id),['CH04-E1']));
test('regret and hypothetical choice stay together',()=>assert.equal(G.fields['RV02-E2'].question_id,G.fields['RV02-E1'].question_id));
test('gratitude and guilt are separate topics',()=>assert.notEqual(G.fields['RV06-E1'].question_id,G.fields['RV06-E2'].question_id));
test('school premise belongs to each split topic',()=>{for(const qid of ['GR02','GR02b']){const q=G.getContract(qid),f=q.elements.find(f=>f.activation.premise_check);assert(f);assert.equal(f.question_id,qid);assert.equal(G.analyze(qid,[],P()).target,f.id);}});
test('all empty topic states route without internal exceptions',()=>{for(const q of C.questions){const r=G.analyze(q.id,[],P());assert.equal(r.decision,'ask',q.id+':'+r.errors);assert.equal(G.fields[r.target].question_id,q.id);assert.equal((r.question.match(/[？?]/g)||[]).length,1);}});
console.log(JSON.stringify({checks:checks.length,passed:checks.filter(c=>c.passed).length,failures:checks.filter(c=>!c.passed)},null,2));process.exitCode=checks.some(c=>!c.passed)?1:0;
