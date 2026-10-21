'use strict';
const assert=require('assert'),U=require('./evidence-units'),rows=[];
const sources=[{id:'own',question_id:'WK01',speaker:'narrator',text:'因为家里缺钱，我没再上学。我的第一份工作是修车。后来我还换过工作。'}];
const candidate=(evidence,relation)=>({state:'known',value:'因为家里缺钱',evidence_unit_ids:evidence,scope:{subject:'self',period:'youth',relation_unit_ids:relation}});
function test(name,fn){try{fn();rows.push({name,pass:true});}catch(e){rows.push({name,pass:false,error:e.message});}}
test('explicit extra relation units augment selected joint answer proof',()=>{
 const r=U.expand('WK01',sources,candidate(['S1.1','S1.2'],['S1.2']),{jointProof:true});assert(r.ok);assert.equal(r.candidate.scope.relation_evidence[0].quote,'因为家里缺钱，我没再上学。我的第一份工作是修车。');
});
test('unselected sentence gaps are never filled',()=>{
 const r=U.expand('WK01',sources,candidate(['S1.1'],['S1.3']),{jointProof:true});assert(r.ok);assert.equal(r.candidate.scope.relation_evidence.length,2);assert(!r.candidate.scope.relation_evidence.some(x=>x.quote.includes('我的第一份工作是修车')));
});
test('explicitly selected foreign unit remains rejected',()=>assert(!U.expand('WK01',sources,candidate(['S1.1'],['S2.1']),{jointProof:true}).ok));
test('legacy non-joint interface does not augment its relation selection',()=>{
 const r=U.expand('WK01',sources,candidate(['S1.1','S1.2'],['S1.2']));assert(r.ok);assert.equal(r.candidate.scope.relation_evidence[0].quote,'我的第一份工作是修车。');
});
const report={kind:'synthetic_joint_proof_union',tests:rows.length,passed:rows.filter(x=>x.pass).length,rows,no_DS_calls:true};console.log(JSON.stringify(report,null,2));process.exitCode=rows.every(x=>x.pass)?0:1;
