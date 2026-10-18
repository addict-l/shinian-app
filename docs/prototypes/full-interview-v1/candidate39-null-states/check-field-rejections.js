'use strict';
// Synthetic minimized interface/controller failures. Never DS accuracy evidence.
const assert=require('assert'),G=require('./engine');
const src=(q,text)=>[{id:'synthetic',question_id:q,speaker:'narrator',text,question:null}];
const p=fields=>({control:{action:'continue',evidence_unit_ids:[]},fields});
const f=(state,value,subject='self')=>({state,value,evidence_unit_ids:['S1.1'],scope:{subject,period:'lifelong'}});
const results=[];
function test(name,fn){try{fn();results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:e.message});}}
test('selected joint-proof units need no duplicate literal relation attribute',()=>{
 const r=G.analyze('SK05',src('SK05','我是慢热的人。'),p({'SK05-E1':f('known','我是慢热的人')}));
 assert.equal(r.decision,'ready');assert.equal(r.fields['SK05-E1'].scope.relation_evidence[0].quote,'我是慢热的人。');
});
test('terminal quoted display text normalizes to null then explicit basis is still checked',()=>{
 const r=G.analyze('RV02',src('RV02','我没有什么遗憾。'),p({'RV02-E1':f('none','我没有什么遗憾')}));
 assert.equal(r.fields['RV02-E1'].state,'none');assert.equal(r.fields['RV02-E1'].value,null);assert.equal(r.decision,'ready');
});
test('semantic nonanswer is rejected without blocking independent missing-field selection',()=>{
 const r=G.analyze('FM07',src('FM07','母亲给我准备了干粮。'),p({'FM07-E2':f('known','母亲给我准备了干粮。')}));
 assert.equal(r.fields['FM07-E2'].state,'missing');assert.equal(r.decision,'ask');assert.equal(r.target,'FM07-E1');
 assert(r.rejected_candidates.some(x=>x.reason==='family_action_not_narrator_felt_meaning'));
});
test('not mentioning the target cannot become unknown or close it',()=>{
 const r=G.analyze('SK02',src('SK02','我的名字是自己改的。'),p({'SK02-E3':f('unknown',null)}));
 assert.equal(r.fields['SK02-E3'].state,'missing');assert.equal(r.decision,'ask');assert.equal(r.target,'SK02-E2');
});
test('unsupported empty not-applicable is not stored as absence',()=>{
 const r=G.analyze('FM01',src('FM01','我从来没有想过成家。'),p({'FM01-E2':{state:'not_applicable',value:null,evidence_unit_ids:[]}}));
 assert.equal(r.fields['FM01-E2'].state,'missing');assert.equal(r.decision,'ask');assert.equal(r.target,'FM01-A1');
});
test('joint proof does not repair invented unit or source',()=>{
 const b=f('known','我是慢热的人');b.evidence_unit_ids=['S2.1'];
 const r=G.analyze('SK05',src('SK05','我是慢热的人。'),p({'SK05-E1':b}));assert.equal(r.decision,'invalid');assert.equal(r.fields['SK05-E1'].state,'missing');
});
test('wrong role remains hard invalid in the joint proof interface',()=>{
 const r=G.analyze('SK05',src('SK05','我是慢热的人。'),p({'SK05-E1':f('known','我是慢热的人','teacher')}));assert.equal(r.decision,'invalid');assert.equal(r.fields['SK05-E1'].state,'missing');
});
test('semantic terminal rejection cannot erase a valid same-question cache',()=>{
 const sources=src('SK02','父母希望我平安。'),a=f('known','父母希望我平安');
 const old=G.analyze('SK02',sources,p({'SK02-E3':a}));assert.equal(old.fields['SK02-E3'].state,'known');
 sources.push({id:'second',question_id:'SK02',speaker:'narrator',question:null,text:'名字是我自己改的。'});
 const b=f('unknown',null);b.evidence_unit_ids=['S2.1'];
 const r=G.analyze('SK02',sources,p({'SK02-E3':b}),{previous_fields:old.fields});assert.equal(r.fields['SK02-E3'].state,'known');assert.equal(r.fields['SK02-E3'].value,'父母希望我平安');
});
test('explicit correction remains strict even for semantic terminal rejection',()=>{
 const r=G.analyze('SK02',src('SK02','不对，名字是我自己改的。'),p({'SK02-E3':f('unknown',null)}));assert.equal(r.decision,'invalid');assert.equal(r.fields['SK02-E3'].state,'missing');
});
test('quoted terminal display text does not supply absent negative semantics',()=>{
 const r=G.analyze('RV02',src('RV02','这件事发生在学校。'),p({'RV02-E1':f('none','这件事发生在学校')}));assert.equal(r.fields['RV02-E1'].state,'missing');assert.equal(r.decision,'ask');
});
const report={kind:'synthetic_minimized_field_rejection_tests',tests:results.length,passed:results.filter(x=>x.pass).length,results};
console.log(JSON.stringify(report,null,2));process.exitCode=results.every(x=>x.pass)?0:1;
