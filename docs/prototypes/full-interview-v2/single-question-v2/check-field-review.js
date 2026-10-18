'use strict';
// Synthetic control/assembly integrity tests, never actual model accuracy.
const assert=require('assert'),F=require('./field-review');
const good={control:{action:'pause',evidence_unit_ids:['S1.1']},fields:{}};
const checks=[];function test(name,fn){try{fn();checks.push({name,pass:true});}catch(e){checks.push({name,pass:false,error:e.message});}}
test('missing first control cannot silently become continue',()=>assert.equal(F.assemble({fields:{}},[]).proposal.control,null));
test('unparsed first proposal cannot silently become continue',()=>assert.equal(F.assemble(null,[]).proposal.control,null));
test('explicit first pause remains intact after per-field reviews',()=>assert.deepEqual(F.assemble(good,[{field_id:'SK05-E1',output:{fields:{}}}]).proposal.control,good.control));
test('review cannot return another field unnoticed',()=>assert(F.assemble(good,[{field_id:'SK05-E1',output:{fields:{'SK05-R1':{}}}}]).errors.length));
test('malformed field response cannot silently become missing',()=>assert(F.assemble(good,[{field_id:'SK05-E1',output:null}]).errors.length));
test('duplicate reviews cannot replace another target',()=>assert(F.assemble(good,[{field_id:'SK05-E1',output:{fields:{}}},{field_id:'SK05-E1',output:{fields:{}}}]).errors.length));
const report={kind:'synthetic_atomic_control_integrity',tests:checks.length,passed:checks.filter(x=>x.pass).length,checks};console.log(JSON.stringify(report,null,2));process.exitCode=checks.every(x=>x.pass)?0:1;
