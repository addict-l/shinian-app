'use strict';
// Synthetic controller checks, never actual DS evidence or accuracy counts.
const assert=require('assert'),U=require('./evidence-units');
const sources=[{id:'a',question_id:'SK05',speaker:'narrator',text:'𠮷。我慢熱。\n我認為這也挺好。'},{id:'b',question_id:'SK05',text:'現在我更願意說話。'},{id:'x',question_id:'SK04',text:'別題秘密。'},{id:'host',speaker:'interviewer',text:'採訪者說的話。'}];
const c=U.catalog('SK05',sources);assert(c.length>=4);for(const u of c){assert(sources.find(s=>s.id===u.source_id).text.includes(u.text));assert(!['x','host'].includes(u.source_id));}
const first=c.filter(u=>u.source_id==='a');const r=U.resolve('SK05',sources,first.map(u=>u.id));assert(r.ok);assert.equal(r.refs.length,1);assert.equal(r.refs[0].quote,sources[0].text);
assert(!U.resolve('SK05',sources,['S3.1']).ok);assert(!U.resolve('SK05',sources,['S999.1']).ok);
const gaps=U.resolve('SK05',sources,[first[0].id,first.at(-1).id]);assert.equal(gaps.refs.length,2);
const p={state:'known',value:'慢熱',evidence_unit_ids:[first[1].id],scope:{subject:'self',period:'lifelong',relation_unit_ids:'same_as_evidence'}};
const a=U.expand('SK05',sources,p);assert(a.ok);assert.equal(a.candidate.evidence[0].quote,first[1].text);assert.equal(a.candidate.scope.relation_evidence,'same_as_evidence');assert(p.evidence_unit_ids);
assert(!U.expand('SK05',sources,{...p,evidence:[{source_id:'b',quote:'偽造'}]}).ok);
const other=U.expand('SK05',sources,{...p,evidence_unit_ids:['S4.1']});assert(!other.ok);
console.log(JSON.stringify({kind:'synthetic_evidence_unit_checks',passed:true,narrative_units:c.length,no_DS_calls:true}));
