'use strict';
const assert=require('assert'),G=require('./engine'),rows=[];
const q='SK01',text='我出生于2001年3月4日。',r=[{source_id:'one',quote:text}],s=[{id:'one',question_id:q,speaker:'narrator',text,question:G.baseQuestion[q]}];
const f=()=>({state:'known',value:'2001年3月4日',time:{precision:'day'},evidence:r,scope:{subject:'self',period:'birth',relation_evidence:r}});
const run=a=>G.analyze(q,s,{control:{action:'continue',evidence:[]},fields:{'SK01-E1':a}});
function test(name,fn){try{fn();rows.push({name,pass:true});}catch(e){rows.push({name,pass:false,error:e.message});}}
test('same-type singleton precision wrapper is losslessly lifted',()=>{const result=run(f());assert.equal(result.fields['SK01-E1'].state,'known');assert.equal(result.fields['SK01-E1'].precision,'day');assert(result.protocol_normalizations.some(x=>x.rule==='lossless_typed_precision_wrapper'));});
test('same top-level precision is not a conflict',()=>{const a=f();a.precision='day';assert.equal(run(a).fields['SK01-E1'].state,'known');});
test('conflicting precision is never overwritten',()=>{const a=f();a.precision='year';assert.equal(run(a).decision,'invalid');});
test('wrapper with extra semantic properties is still rejected',()=>{const a=f();a.time.calendar='invented';assert.equal(run(a).decision,'invalid');});
test('wrong-type wrapper is still rejected',()=>{const a=f();a.duration=a.time;delete a.time;assert.equal(run(a).decision,'invalid');});
test('moving precision never repairs a forged source',()=>{const a=f();a.evidence=[{source_id:'foreign',quote:text}];assert.equal(run(a).decision,'invalid');});
const report={kind:'synthetic_typed_precision_normalization',tests:rows.length,passed:rows.filter(x=>x.pass).length,rows,no_DS_calls:true};console.log(JSON.stringify(report,null,2));process.exitCode=rows.every(x=>x.pass)?0:1;
