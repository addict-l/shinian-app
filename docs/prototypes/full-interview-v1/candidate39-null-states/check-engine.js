'use strict';
// Synthetic structural/control regression fixtures; these are not real-material accuracy results.
const assert=require('assert'),fs=require('fs'),path=require('path'),crypto=require('crypto');
const G=require('./engine'),C=require('./contracts.json'),results=[];
const source=(qid,text,id='u1',extra={})=>({id,text,question_id:qid,speaker:'narrator',question:G.baseQuestion[qid],...extra});
const ref=(text,id='u1')=>({source_id:id,quote:text});
const field=(text,subject='self',period='lifelong',extra={})=>({state:'known',value:text,evidence:[ref(text)],scope:{subject,period,relation_evidence:[ref(text)]},...extra});
const terminal=(state,text,subject='self',period='lifelong',extra={})=>field(text,subject,period,{state,value:null,...extra});
const proposal=(fields={},action='continue',evidence=[])=>({control:{action,evidence},fields});
function test(name,fn){try{fn();results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:e.message});}}
test('62 exact original questions and default order',()=>{
 assert.equal(Object.keys(G.baseQuestion).length,62);assert.equal(C.default_order.length,62);
 let scan=__dirname;while(!fs.existsSync(path.join(scan,'interview-development-baseline.md'))&&path.dirname(scan)!==scan)scan=path.dirname(scan);
 const b=fs.readFileSync(path.join(scan,'interview-development-baseline.md'),'utf8');
 for(const q of C.questions)assert(b.includes(q.main_question),q.id);
 assert.equal(C.default_order[26],'FM01');assert.equal(C.default_order[33],'WK07');assert.equal(C.default_order.at(-1),'RV16');
});
for(const q of C.questions)test(q.id+' blank cannot complete and asks one target',()=>{
 const r=G.analyze(q.id,[source(q.id,'嗯。')],proposal());
 assert.equal(r.decision,'ask');assert(G.fields[r.target]);assert.equal(typeof r.question,'string');
 assert.equal(r.question.split('？').filter(Boolean).length,1);
});
test('self trait short phrase enough',()=>assert.equal(G.analyze('SK05',[source('SK05','我是慢热的人。')],proposal({'SK05-E1':field('我是慢热的人。')})).decision,'ready'));
test('one selected summary and linked explanation enough',()=>{
 const text='就操心吧，家里大小事都是我张罗。',a=field('操心');a.evidence=[ref(text)];a.scope.relation_evidence=[ref(text)];
 const b=field('家里大小事都是我张罗');b.evidence=[ref(text)];b.scope.relation_evidence=[ref(text)];b.links=[{field_id:'SK06-E1',value:'操心'}];
 const r=G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':a,'SK06-E2':b}));assert.equal(r.decision,'ready');
});
test('keywords alone asks explanation, never forces third',()=>{
 const r=G.analyze('SK06',[source('SK06','操心、奔波。')],proposal({'SK06-E1':field('操心、奔波')}));assert.equal(r.target,'SK06-E2');
});
test('unknown summary closes reason branch limited',()=>{
 const text='这一题我不知道怎么概括。',r=G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':terminal('unknown',text)}));assert.equal(r.decision,'limited');assert(!r.active.includes('SK06-E2'));
});
test('unknown one field leaves other required fields open',()=>{
 const text='出生哪一年我不知道。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E1':terminal('unknown',text,'self','birth')}));assert.equal(r.decision,'ask');assert.equal(r.target,'SK01-E2');
});
test('actual directed place answer is accepted without redundant birth word',()=>{
 const text='地点是在江苏农村。',s=source('SK01',text,'u1',{question:'您出生在哪个地方？',target_field_id:'SK01-E2'});
 const r=G.analyze('SK01',[s],proposal({'SK01-E2':field('江苏农村','self','birth',{evidence:[ref(text)],scope:{subject:'self',period:'birth',relation_evidence:[ref(text)]}})}),{focus:{field_id:'SK01-E2'},current_question:s.question});
 assert.equal(r.fields['SK01-E2'].state,'known');assert.equal(r.errors.length,0);
});
test('hometown is not automatically birthplace',()=>{
 const text='我家乡是浙江农村。',r=G.analyze('SK01',[source('SK01',text,'u1',{question:'老家在哪里？'})],proposal({'SK01-E2':field(text,'self','birth')}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert(r.question);
});
test('known birth month retained and no completion from missing scene',()=>{
 const text='我1950年3月出生。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E1':field(text,'self','birth',{precision:'year'})}));assert.equal(r.fields['SK01-E1'].precision,'month');assert.equal(r.target,'SK01-E2');
});
test('quote mismatch is internal failure with no user re-question',()=>{
 const text='我是内向的人。',p=proposal({'SK05-E1':field('我是外向的人。')}),r=G.analyze('SK05',[source('SK05',text)],p);assert.equal(r.decision,'invalid');assert.equal(r.target,null);assert.equal(r.question,null);
});
test('forged relation citation cannot complete',()=>{
 const text='我挺内向。',f=field(text);f.scope.relation_evidence=[ref('我很外向。')];assert.equal(G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f})).decision,'invalid');
});
test('cross question source rejected',()=>assert.equal(G.analyze('SK05',[source('SK04','家里很严。')],proposal()).decision,'invalid'));
test('cross question cache rejected',()=>assert.equal(G.analyze('SK05',[source('SK05','我慢热。')],proposal(),{previous_fields:{'SK04-E1':field('我慢热。')}}).decision,'invalid'));
test('same question known cache reused without re-extraction',()=>{
 const s=source('SK05','我慢热。'),r=G.analyze('SK05',[s],proposal({'SK05-E1':field(s.text)}));
 const next=G.analyze('SK05',[s,source('SK05','没有补充。','u2')],proposal(),{previous_fields:r.fields});assert.equal(next.decision,'ready');assert.equal(next.fields['SK05-E1'].value,s.text);
});
test('same question unknown persists instead of re-asking',()=>{
 const text='这一题我不记得了。',r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':terminal('unknown',text)}));
 const next=G.analyze('SK05',[source('SK05',text),source('SK05','嗯。','u2')],proposal(),{previous_fields:r.fields});assert.equal(next.decision,'limited');assert.equal(next.fields['SK05-E1'].state,'unknown');
});
test('current pause dominates malformed extraction',()=>{
 const text='今天累了，先到这里。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E1':field('伪造')},'pause',[ref(text)]));assert.equal(r.decision,'paused');assert.equal(r.question,null);assert(r.errors.length);
});
test('old pause cannot stop current turn',()=>{
 const text='今天累了，先到这里。',r=G.analyze('SK05',[source('SK05',text),source('SK05','继续。','u2')],proposal({},'pause',[ref(text)]));assert.equal(r.decision,'invalid');
});
test('recalled work stoppage is not interview pause',()=>{
 const text='那时候工厂暂停生产。',r=G.analyze('WK09',[source('WK09',text)],proposal({},'pause',[ref(text)]));assert.equal(r.decision,'invalid');
});
test('two unanswered directed asks route consent, never automatic refusal',()=>{
 const r=G.analyze('SK01',[source('SK01','嗯。')],proposal(),{ask_counts:{'SK01-E1':2}});assert.equal(r.decision,'ask_defer');assert.equal(r.fields['SK01-E1'].state,'missing');
});
test('reported trait alone asks self endorsement',()=>{
 const text='别人说我很要强。',r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-R1':field(text,'other')}));assert.equal(r.target,'SK05-E2');
});
test('traditional explicit unknown and negative preserved',()=>{
 const text='我沒有兄弟姐妹。',r=G.analyze('SK03',[source('SK03',text)],proposal({'SK03-E3':terminal('none',text,'self','childhood')}));assert.equal(r.fields['SK03-E3'].state,'none');assert.equal(r.errors.length,0);
 const t='這一題我不記得了。',u=G.analyze('SK05',[source('SK05',t)],proposal({'SK05-E1':terminal('unknown',t)}));assert.equal(u.decision,'limited');assert.equal(u.fields['SK05-E1'].evidence[0].quote,t);
});
test('traditional no schooling closes only own question and survives cache',()=>{
 const text='我沒有上過學。',s=source('GR03',text),r=G.analyze('GR03',[s],proposal({'GR03-A1':terminal('none',text,'self','unspecified')}));assert.equal(r.decision,'limited');assert.equal(r.fields['GR03-E1'].state,'not_applicable');
 const next=G.analyze('GR03',[s,source('GR03','嗯。','u2')],proposal(),{previous_fields:r.fields});assert.equal(next.decision,'limited');assert.equal(next.errors.length,0);
});
test('unmarried alone does not establish absence of partner',()=>{
 const text='我没结过婚。',r=G.analyze('FM01',[source('FM01',text)],proposal({'FM01-A1':terminal('none',text,'self','unspecified')}));assert.equal(r.decision,'ask');assert.equal(r.fields['FM01-A1'].state,'missing');assert.equal(r.target,'FM01-A1');
});
test('wrong explicit stage is rejected',()=>{
 const text='小时候家里很穷。',r=G.analyze('CH02',[source('CH02',text)],proposal({'CH02-E1':field(text,'family','now')}));assert.equal(r.decision,'invalid');
});
test('unrelated long unknown cannot bind birth time by length',()=>{
 const text='父亲一直不知道同事为什么不跟他讲话，这件事他到后来还是记不清。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E1':terminal('unknown',text,'self','birth')}));assert.equal(r.decision,'ask');assert.equal(r.fields['SK01-E1'].state,'missing');assert.equal(r.target,'SK01-E1');
});
test('not thought about it is unknown rather than none',()=>{
 const text='这个问题我还没想明白。',r=G.analyze('RV11',[source('RV11',text)],proposal({'RV11-E1':terminal('unknown',text)}));assert.equal(r.decision,'limited');
});
test('all field contracts carry auditable requirements and scope',()=>{
 for(const f of Object.values(G.fields)){for(const k of ['id','label','type','required','activation','usable_answer','scope','negative_semantics','unknown_semantics','refusal_semantics','question'])assert(k in f,f.id+':'+k);assert(f.scope.subjects.length);assert(f.scope.object_relation);}
});
test('school process evaluation cannot substitute entry age or period',()=>{
 const text='刚开始上学很顺利，后来中断了。',r=G.analyze('GR01',[source('GR01',text)],proposal({'GR01-E1':field('刚开始上学很顺利','self','school_years',{evidence:[ref(text)],scope:{subject:'self',period:'school_years',relation_evidence:[ref(text)]},precision:'relative'})}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert.equal(r.fields['GR01-E1'].state,'missing');
});
test('birth identity after birth date still does not establish birthplace',()=>{
 const text='我1940年出生，某省某县人。',r=G.analyze('SK01',[source('SK01',text,'u1',{question:'请介绍家庭背景。'})],proposal({'SK01-E2':field('某省某县','self','birth',{evidence:[ref(text)],scope:{subject:'self',period:'birth',relation_evidence:[ref(text)]}})}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
});
test('family living adequacy is not interpersonal atmosphere',()=>{
 const text='家乡生活还说得过去。',r=G.analyze('SK03',[source('SK03',text)],proposal({'SK03-E4':field(text,'family','childhood')}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
});
test('following one specific suggestion is not personality effect',()=>{
 const text='妈妈建议我换工作，我按建议去办。',r=G.analyze('SK04',[source('SK04',text)],proposal({'SK04-E3':field(text)}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
});
test('a concrete family teaching action is usable without a style label',()=>{
 const text='爸爸就教我写字。',r=G.analyze('SK04',[source('SK04',text)],proposal());assert.equal(r.fields['SK04-E1'].state,'known');assert.equal(r.target,'SK04-E3');
});
test('self naming cannot negate family expectations',()=>{
 const text='名字是我自己取的，当时没有想到做什么。',r=G.analyze('SK02',[source('SK02',text)],proposal({'SK02-E3':terminal('none',text)}));assert.equal(r.decision,'ask');assert.equal(r.fields['SK02-E3'].state,'missing');
});
test('helping action alone is not narrator stated family meaning',()=>{
 const text='妈妈给我一件东西作盘缠，我记得很难过。',r=G.analyze('FM07',[source('FM07',text)],proposal({'FM07-E2':field(text)}));assert.equal(r.decision,'ask');assert.equal(r.fields['FM07-E2'].state,'missing');assert.equal(r.target,'FM07-E1');
});
test('explicit sibling absence proposed as known becomes none with raw proof',()=>{
 const text='我沒有兄弟姐妹。',r=G.analyze('SK03',[source('SK03',text)],proposal({'SK03-E3':field(text,'self','childhood')}));assert.equal(r.fields['SK03-E3'].state,'none');assert.equal(r.fields['SK03-E3'].evidence[0].quote,text);
});
test('scope links are lifted losslessly and original protocol failure is auditable',()=>{
 const text='因为家里不能再供我读书，我最初就去工厂做工。',a=field('去工厂做工','self','youth',{evidence:[ref(text)],scope:{subject:'self',period:'youth',relation_evidence:[ref(text)]}});
 const b=field('因为家里不能再供我读书','self','youth',{evidence:[ref(text)],scope:{subject:'self',period:'youth',relation_evidence:[ref(text)],links:[{field_id:'WK01-E1',value:'去工厂做工'}]}});
 const r=G.analyze('WK01',[source('WK01',text)],proposal({'WK01-E1':a,'WK01-E2':b}));assert.equal(r.decision,'ready');assert.equal(r.fields['WK01-E2'].links[0].value,'去工厂做工');assert.equal(r.protocol_normalizations.length,1);assert(r.protocol_normalizations[0].original_candidate.scope.links);
});
test('unrelated milestone cannot become family education period',()=>{
 const text='我十七岁去了外地。后来父亲鼓励我读书。',a=field('父亲鼓励我读书','parents','youth',{evidence:[ref('后来父亲鼓励我读书。')],scope:{subject:'parents',period:'youth',relation_evidence:[ref('后来父亲鼓励我读书。')]}});
 const b=field('我十七岁去了外地','self','youth',{evidence:[ref('我十七岁去了外地。')],scope:{subject:'self',period:'youth',relation_evidence:[ref('我十七岁去了外地。')]}});
 const r=G.analyze('SK04',[source('SK04',text)],proposal({'SK04-E1':a,'SK04-E2.period':b}));assert.equal(r.decision,'ask');assert.equal(r.target,'SK04-E3');assert.equal(r.fields['SK04-E2.period'].state,'missing');assert(r.inactive_conditional_errors.length);
});
test('academic rank is not a personhood expectation',()=>{
 const text='我说，妈妈就是要第一名、一百分。',r=G.analyze('FM05',[source('FM05',text)],proposal({'FM05-E2':field('妈妈就是要第一名、一百分','self','adulthood',{evidence:[ref(text)],scope:{subject:'self',period:'adulthood',relation_evidence:[ref(text)]}})}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
});
test('parser may restore only a missing outer brace and preserves original raw failure',()=>{
 const raw='{"control":{"action":"continue","evidence":[]},"fields":{}',r=G.parseProposal(raw,{finish_reason:'stop'});assert(r.ok);assert.deepEqual(r.proposal.fields,{});assert.equal(r.normalizations[0].original_raw,raw);assert(r.original_parse_error);
});
test('parser refuses truncated values, inner objects, strings and token-limit output',()=>{
 for(const raw of ['{"fields":{"x":{}','{"fields":{"x":"abc','{"fields":'])assert(!G.parseProposal(raw,{finish_reason:'stop'}).ok);
 assert(!G.parseProposal('{"fields":{}',{finish_reason:'length'}).ok);
});
test('a lesson alone cannot certify whether the narrator let a misunderstanding go',()=>{
 const text='这件误会教会我以后做人要谨慎。',r=G.analyze('RV03',[source('RV03',text)],proposal({'RV03-E2':field(text)}));assert.equal(r.decision,'ask');assert.equal(r.target,'RV03-E1');assert.equal(r.fields['RV03-E2'].state,'missing');assert(r.semantic_rejections.length);
});
test('unclear hypothetical remains ambiguous without invented refusal or unknown',()=>{
 const text='我遗憾当初离开家。如果重来，那个人，那时候……';
 const e=[ref(text)];const r=G.analyze('RV02',[source('RV02',text)],proposal({'RV02-E1':field('我遗憾当初离开家','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),'RV02-E2':terminal('ambiguous',text)}));
 assert.equal(r.fields['RV02-E2'].state,'ambiguous');assert.equal(r.target,'RV02-E2');assert.equal(r.decision,'ask');
});
test('explicit evidence alias expands only this fields verified references',()=>{
 const text='我比较慢热。',f=field(text);f.scope.relation_evidence='same_as_evidence';
 const r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'ready');assert.deepEqual(r.fields['SK05-E1'].scope.relation_evidence,f.evidence);assert.equal(r.protocol_normalizations[0].original_candidate.scope.relation_evidence,'same_as_evidence');
});
test('missing relation proof is not auto filled without an explicit alias',()=>{
 const text='我比较慢热。',f=field(text);delete f.scope.relation_evidence;
 assert.equal(G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f})).decision,'invalid');
});
test('evidence alias never makes a forged quote valid',()=>{
 const f=field('我很外向。');f.scope.relation_evidence='same_as_evidence';
 assert.equal(G.analyze('SK05',[source('SK05','我比较慢热。')],proposal({'SK05-E1':f})).decision,'invalid');
});
test('evidence alias never overrides a wrong subject',()=>{
 const text='我父亲很内向。',f=field(text,'parents');f.scope.relation_evidence='same_as_evidence';
 assert.equal(G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f})).decision,'invalid');
});
test('evidence alias never converts hometown into birthplace',()=>{
 const text='我的家乡是某县。',f=field('某县','self','birth',{evidence:[ref(text)],scope:{subject:'self',period:'birth',relation_evidence:'same_as_evidence'}});
 assert.equal(G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E2':f})).decision,'ask');
});
test('literal era year supplies only missing precision without calendar conversion',()=>{
 const text='我是民國24年出生的。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E1':field('民國24年','self','birth',{evidence:[ref(text)],scope:{subject:'self',period:'birth',relation_evidence:'same_as_evidence'}})}));assert.equal(r.fields['SK01-E1'].precision,'year');assert.equal(r.fields['SK01-E1'].value,'民國24年');assert.equal(r.errors.length,0);
});
test('rejected optional quote is logged without invalidating a valid required trait',()=>{
 const text='我很慢热。',r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':field(text),'SK05-O1':field('不存在的文字')}));assert.equal(r.decision,'ready');assert(r.optional_errors.length);assert.equal(r.fields['SK05-O1'].state,'missing');assert(r.rejected_candidates.some(x=>x.field_id==='SK05-O1'));
});
test('attitude holder and parent target remain separate roles',()=>{
 const text='我最感谢的是父母。',f=field('父母','self','lifelong',{evidence:[ref(text)],scope:{subject:'self',period:'lifelong',relation_evidence:'same_as_evidence',object:'父母',object_role:'parents',object_evidence:[ref(text)]}});
 const r=G.analyze('RV06',[source('RV06',text)],proposal({'RV06-E1':f}));assert.equal(r.errors.length,0);assert.equal(r.fields['RV06-E1'].scope.subject,'self');assert.equal(r.fields['RV06-E1'].scope.object_role,'parents');
 f.scope.subject='parents';assert.equal(G.analyze('RV06',[source('RV06',text)],proposal({'RV06-E1':f})).decision,'invalid');
});
test('object label needs literal evidence rather than an unsupported tag',()=>{
 const text='我很慢热。',f=field(text);f.scope.object='某个无关人';assert.equal(G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f})).decision,'invalid');
});
test('unanchored marriage-era venture cannot inherit youth from the mapped question',()=>{
 const text='婚后我开了一间店。',s=source('WK05',text,'u1',{question:'请谈谈婚后的事业。'}),r=G.analyze('WK05',[s],proposal({'WK05-E1':field(text,'self','youth')}));assert.equal(r.fields['WK05-E1'].state,'ambiguous');assert(r.unbound_material.length);assert.equal(r.question,'您说的这段经历，大概是人生哪个时候？');
});
test('real stage-specific main question can bind an otherwise unambiguous reply',()=>{
 const text='我决定出去开店。',r=G.analyze('WK05',[source('WK05',text)],proposal({'WK05-E1':field(text,'self','youth')}));assert.equal(r.decision,'ready');
});
test('family responsibility at a later actual stage remains applicable',()=>{
 const text='现在六十多岁了，我要照顾父母，自己只能抽空休息。',e=[ref(text)],r=G.analyze('WK12',[source('WK12',text)],proposal({'WK12-E1':field('我要照顾父母','self','now',{evidence:e,scope:{subject:'self',period:'now',relation_evidence:e}}),'WK12-E2':field('自己只能抽空休息','self','now',{evidence:e,scope:{subject:'self',period:'now',relation_evidence:e}})}));assert.equal(r.decision,'ready');
});
test('actual family activity is retained without inventing paid employment',()=>{
 const text='我父亲参加共产党，打游击去了。',r=G.analyze('SK03',[source('SK03',text)],proposal({'SK03-E2':field(text,'parents','childhood')}));assert.equal(r.fields['SK03-E2'].state,'known');assert.equal(r.fields['SK03-E2'].value,text);
});
test('future activity does not become present preference even if value omits its qualifier',()=>{
 const text='以后我会画画。',e=[ref(text)],r=G.analyze('LT01',[source('LT01',text)],proposal({'LT01-E2':field('画画','self','now',{evidence:e,scope:{subject:'self',period:'now',relation_evidence:e}})}));assert.equal(r.fields['LT01-E2'].state,'ambiguous');assert(r.unbound_material.length);
});
function stageFixture(shared=true){
 const q='WK03',a='婚后开店很辛苦，每天要忙很久。',b='另一年我搬到城里照顾生意。',s=[source(q,a,'u1',{question:'婚后生意怎么样？'})];if(!shared)s.push(source(q,b,'u0',{question:'后来还有什么经历？'}));
 const mk=(value,text,id)=>field(value,'self','youth',{evidence:[ref(text,id)],scope:{subject:'self',period:'youth',relation_evidence:[ref(text,id)]}});
 const p=proposal({'WK03-E1':mk('很辛苦',a,'u1'),'WK03-E2':shared?mk('每天要忙很久',a,'u1'):mk('照顾生意',b,'u0')});
 const first=G.analyze(q,s,p);const text='那段事在人生哪个阶段，我记不清了。',last=source(q,text,'u2',{question:first.question,target_field_id:first.target});
 const t=terminal('unknown',text,'self','unspecified',{evidence:[ref(text,'u2')],scope:{subject:'self',period:'unspecified',relation_evidence:[ref(text,'u2')]}});
 const second=G.analyze(q,[...s,last],proposal({[first.target]:t}),{focus:{field_id:first.target},current_question:first.question,previous_fields:first.fields});return {q,s,last,p,first,second};
}
test('same proven material stage unknown closes only the shared stage gap once',()=>{
 const {second:r}=stageFixture();assert.equal(r.decision,'limited');assert.equal(r.effective['WK03-E1'],'unknown');assert.equal(r.effective['WK03-E2'],'unknown');assert.equal(r.fields['WK03-E2'].state,'ambiguous');assert.equal(r.fields['WK03-E2'].unbound_value,'每天要忙很久');assert.equal(r.fields['WK03-E2'].stage_binding.evidence[0].source_id,'u2');
});
test('same-material stage terminal survives later omission and repeat extraction',()=>{
 const {q,s,last,p,second}=stageFixture();const all=[...s,last,source(q,'没有补充。','u3')];
 assert.equal(G.analyze(q,all,proposal(),{previous_fields:second.fields}).decision,'limited');
 assert.equal(G.analyze(q,all,p,{previous_fields:second.fields}).decision,'limited');
});
test('another material is not closed by the first materials stage unknown',()=>{
 const {second:r}=stageFixture(false);assert.equal(r.effective['WK03-E1'],'unknown');assert.equal(r.effective['WK03-E2'],'ambiguous');assert.equal(r.target,'WK03-E2');assert.equal(r.decision,'ask');
});
test('a still missing other target is not filled by a stage terminal',()=>{
 const {q,s,last,first}=stageFixture();delete first.fields['WK03-E2'];
 const text=last.text,t=terminal('unknown',text,'self','unspecified',{evidence:[ref(text,'u2')],scope:{subject:'self',period:'unspecified',relation_evidence:[ref(text,'u2')]}});
 const r=G.analyze(q,[...s,last],proposal({[first.target]:t}),{focus:{field_id:first.target},current_question:first.question,previous_fields:first.fields});assert.equal(r.effective['WK03-E2'],'missing');assert.equal(r.target,'WK03-E2');
});
test('explicit only-child none binds the sibling field without repeating its label',()=>{
 const text='因為我是獨生子，所以生活中很多事都自己做。',r=G.analyze('SK03',[source('SK03',text,'u1',{question:'请谈原生家庭背景。'})],proposal({'SK03-E3':terminal('none',text,'self','childhood')}));assert.equal(r.errors.length,0);assert.equal(r.fields['SK03-E3'].state,'none');assert.notEqual(r.target,'SK03-E3');
});
test('moving or fleeing alongside people does not establish a primary caregiver',()=>{
 const text='小时候我跟着乡亲逃难。',r=G.analyze('SK03',[source('SK03',text,'u1',{question:'谈谈小时候的经历。'})],proposal({'SK03-E1':field(text,'self','childhood')}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert.equal(r.fields['SK03-E1'].state,'missing');
});
test('narrator attributed disposition change need not use the literal personality label',()=>{
 const text='我自己就是受家人教育的影响，由调皮转向勤学的。',r=G.analyze('SK04',[source('SK04',text,'u1',{question:'家人给您什么影响？'})],proposal({'SK04-E3':field('由调皮转向勤学的','self','lifelong',{evidence:[ref(text)],scope:{subject:'self',period:'lifelong',relation_evidence:[ref(text)]}})}));assert.equal(r.errors.length,0);assert.equal(r.fields['SK04-E3'].state,'known');
});
test('same-object explanation may refer to a grounded continuous short form',()=>{
 const text='家里供不起读书，最初我在厂里做临时工。',e=[ref(text)],a=field('最初我在厂里做临时工','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}}),b=field('家里供不起读书','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e},links:[{field_id:'WK01-E1',value:'厂里做临时工'}]});
 const r=G.analyze('WK01',[source('WK01',text)],proposal({'WK01-E1':a,'WK01-E2':b}));assert.equal(r.decision,'ready');assert(r.scope_notices.some(x=>x.rule==='literal_object_subspan_resolves_same_selected_object'));
});
test('a shared occupational suffix cannot bind a different jobs reason',()=>{
 const text='最初我在工厂做临时工，后来在学校做临时工是为了照顾孩子。',a=field('最初我在工厂做临时工','self','youth',{evidence:[ref(text)],scope:{subject:'self',period:'youth',relation_evidence:[ref(text)]}}),quote='后来在学校做临时工是为了照顾孩子',b=field('为了照顾孩子','self','adulthood',{evidence:[ref(quote)],scope:{subject:'self',period:'adulthood',relation_evidence:[ref(quote)]},links:[{field_id:'WK01-E1',value:'临时工'}]});
 assert.equal(G.analyze('WK01',[source('WK01',text)],proposal({'WK01-E1':a,'WK01-E2':b})).decision,'invalid');
});
test('selected summary words cannot use the object short-form exception',()=>{
 const text='我选操心，因为家里都归我张罗。',e=[ref(text)],a=field('操心','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),b=field('家里都归我张罗','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e},links:[{field_id:'SK06-E1',value:'心'}]});assert.equal(G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':a,'SK06-E2':b})).decision,'invalid');
});
test('a location does not become a period through the models scope tag',()=>{
 const text='我家在山里。',r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E3.period':field('我家在山里','self','lifelong',{evidence:[ref(text)],scope:{subject:'self',period:'lifelong',relation_evidence:[ref(text)]}})}));assert.equal(r.decision,'ask');assert.equal(r.target,'SK01-E1');assert.equal(r.fields['SK01-E3.period'].state,'missing');assert(r.semantic_rejections.length);
});
test('a coarse but real life period remains sufficient',()=>{
 const text='上小学那会儿，村里都是土路。',e=[ref(text)],r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E3.period':field('上小学那会儿','self','childhood',{evidence:e,scope:{subject:'self',period:'childhood',relation_evidence:e}})}));assert.equal(r.errors.length,0);assert.equal(r.fields['SK01-E3.period'].state,'known');
});
test('lifelong solitary feeling does not describe household interaction',()=>{
 const text='因为家里只有我一个孩子，所以我这一生都很孤单。',r=G.analyze('SK03',[source('SK03',text,'u1',{question:'介绍原生家庭背景。'})],proposal({'SK03-E4':field('我这一生都很孤单','self','childhood',{evidence:[ref(text)],scope:{subject:'self',period:'childhood',relation_evidence:[ref(text)]}})}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert.equal(r.fields['SK03-E4'].state,'missing');
});
test('a future subquestion cannot borrow now from a mixed actual question',()=>{
 const text='退休后无论去哪儿，都会慢慢走。有从容的节奏。',s=source('LT01',text,'u1',{question:'现在有什么爱好，退休后打算怎样旅行？'}),r=G.analyze('LT01',[s],proposal({'LT01-E2':field('有从容的节奏','self','now',{evidence:[ref(text)],scope:{subject:'self',period:'now',relation_evidence:[ref(text)]}})}));assert.equal(r.fields['LT01-E2'].state,'ambiguous');assert.equal(r.question,'您说的这段经历，大概是人生哪个时候？');
});
test('two periods inside one sentence are not proven same material',()=>{
 const q='WK03',text='婚后开店很辛苦，十年后到外地忙另一门生意。',e=[ref(text)],mk=v=>field(v,'self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}}),s=[source(q,text,'u1',{question:'后来工作怎样？'})],first=G.analyze(q,s,proposal({'WK03-E1':mk('很辛苦'),'WK03-E2':mk('忙另一门生意')})),t='这件事是哪时候的，我记不清了。',last=source(q,t,'u2',{question:first.question,target_field_id:first.target}),u=terminal('unknown',t,'self','unspecified',{evidence:[ref(t,'u2')],scope:{subject:'self',period:'unspecified',relation_evidence:[ref(t,'u2')]}}),r=G.analyze(q,[...s,last],proposal({[first.target]:u}),{focus:{field_id:first.target},previous_fields:first.fields});assert.equal(r.effective['WK03-E1'],'unknown');assert.equal(r.effective['WK03-E2'],'ambiguous');assert.equal(r.target,'WK03-E2');
});
test('an explicit late-life first job is not made youthful by generic first-job words',()=>{
 const text='我退休后六十岁才开始第一份工作，开店很辛苦。',e=[ref(text)],r=G.analyze('WK03',[source('WK03',text)],proposal({'WK03-E1':field(text,'self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}})}));assert.equal(r.fields['WK03-E1'].state,'missing');assert(r.unbound_material.some(x=>x.missing_relation==='explicit_other_stage_than_youth'));assert.notEqual(r.question,'您说的这段经历，大概是人生哪个时候？');
});
test('a relatives young age cannot bind the narrators venture stage',()=>{
 const text='我父亲二十岁毕业，我后来开店很辛苦。',e=[ref(text)],r=G.analyze('WK03',[source('WK03',text,'u1',{question:'开店情况怎样？'})],proposal({'WK03-E1':field('开店很辛苦','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}})}));assert.equal(r.fields['WK03-E1'].state,'ambiguous');assert.equal(r.question,'您说的这段经历，大概是人生哪个时候？');
});
test('same experience may link a youthful arrival and a later directed hardship answer',()=>{
 const a='我二十岁毕业到河边小学教书。',b='刚到那所学校时，生活很艰苦。',s=[source('WK03',a,'u1',{question:'您毕业后到哪里工作？'}),source('WK03',b,'u2',{question:'您刚到那所学校时，生活怎么样？'})],f=field('生活很艰苦','self','youth',{evidence:[ref(b,'u2')],scope:{subject:'self',period:'youth',relation_evidence:[ref(a,'u1'),ref(b,'u2')]}}),r=G.analyze('WK03',s,proposal({'WK03-E1':f}));assert.equal(r.errors.length,0);assert.equal(r.fields['WK03-E1'].state,'known');
});
test('an unrelated older statement about youth cannot bind a new unlocated episode',()=>{
 const a='我二十岁毕业。',b='开店时生活很艰苦。',s=[source('WK03',a,'u1',{question:'您何时毕业？'}),source('WK03',b,'u2',{question:'请谈开店情况。'})],f=field('生活很艰苦','self','youth',{evidence:[ref(b,'u2')],scope:{subject:'self',period:'youth',relation_evidence:[ref(a,'u1'),ref(b,'u2')]}}),r=G.analyze('WK03',s,proposal({'WK03-E1':f}));assert.equal(r.fields['WK03-E1'].state,'ambiguous');
});
test('traditional stage and current words are normalized only for rule matching',()=>{
 const text='我們年輕人初到這裡，每天工作很辛苦。',e=[ref(text)],r=G.analyze('WK03',[source('WK03',text,'u1',{question:'当时工作怎样？'})],proposal({'WK03-E1':field('每天工作很辛苦','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}})}));assert.equal(r.fields['WK03-E1'].state,'known');assert.equal(r.fields['WK03-E1'].evidence[0].quote,text);
});
test('separate literal stage quotes can connect the same concrete arrival',()=>{
 const a='我二十岁毕业后报名去河边村。',b='对我来说，到了河边村，生活非常艰苦。',s=[source('WK03',a,'u1',{question:null}),source('WK03',b,'u2',{question:null})],f=field('生活非常艰苦','self','youth',{evidence:[ref(b,'u2')],scope:{subject:'self',period:'youth',relation_evidence:[ref(a,'u1'),ref(b,'u2')]}}),r=G.analyze('WK03',s,proposal({'WK03-E1':f}));assert.equal(r.fields['WK03-E1'].state,'known');
});
test('an experience value needs the actual matter rather than only its evaluation label',()=>{
 const text='孩子每天回家陪我吃饭，那是我最自豪的时候。',e=[ref(text)],f=field('我最自豪的时候','self','adulthood',{evidence:e,scope:{subject:'self',period:'adulthood',relation_evidence:e}}),r=G.analyze('FM04',[source('FM04',text)],proposal({'FM04-E2':f}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
 f.value=text;assert.equal(G.analyze('FM04',[source('FM04',text)],proposal({'FM04-E2':f})).errors.length,0);
});
test('gratitude to a named person is not itself the grateful event',()=>{
 const text='我要感谢王老师，他让我免费上学。',e=[ref(text)],f=field('我要感谢王老师','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),r=G.analyze('RV13',[source('RV13',text)],proposal({'RV13-E1':f}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
 f.value=text;assert.equal(G.analyze('RV13',[source('RV13',text)],proposal({'RV13-E1':f})).decision,'ready');
});
test('an omitted value on an explicitly empty missing field creates no fact',()=>{
 const r=G.analyze('SK03',[source('SK03','还没说到。')],proposal({'SK03-E2':{state:'missing'}}));
 assert.equal(r.decision,'ask');assert.equal(r.fields['SK03-E2'].state,'missing');assert.equal(r.fields['SK03-E2'].value,null);assert.equal(r.fields['SK03-E2'].evidence.length,0);assert(r.protocol_normalizations.some(x=>x.rule==='missing_without_value_is_canonical_empty'));
});
test('missing cannot hide a real value or evidence',()=>{
 const r=G.analyze('SK03',[source('SK03','父亲是木工。')],proposal({'SK03-E2':{state:'missing',value:'木工',evidence:[ref('父亲是木工。')]}}));
 assert.equal(r.decision,'invalid');assert(r.errors.some(x=>x.includes('missing_carries_value')));
});
test('a necessary activated scene period stays strict',()=>{
 const text='村里都是土路。',e=[ref(text)],r=G.analyze('SK01',[source('SK01',text)],proposal({'SK01-E4':field('都是土路','self','as_stated',{evidence:e,scope:{subject:'self',period:'as_stated',relation_evidence:e}}),'SK01-E3.period':field('村里','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}})}));
 assert(r.active.includes('SK01-E3.period'));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert(r.semantic_rejections.some(x=>x.field_id==='SK01-E3.period'));assert.equal(r.fields['SK01-E3.period'].state,'missing');
});
test('an actual misunderstanding makes its unresolved mood a strict active target',()=>{
 const text='同桌误会我拿他的书，这件误会教会我以后做人要谨慎。',e=[ref(text)],r=G.analyze('RV03',[source('RV03',text)],proposal({'RV03-E1':field('同桌误会我拿他的书','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),'RV03-E2':field('以后做人要谨慎','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}})}));
 assert(r.active.includes('RV03-E2'));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);assert.equal(r.fields['RV03-E2'].state,'missing');
});
function cachedActorFixture(nextText) {
 const text='小时候父亲管我很严，所以我做事很自律。',e=[ref(text)],a=field('父亲管我很严','parents','childhood',{evidence:e,scope:{subject:'parents',period:'childhood',relation_evidence:e}}),b=field('我做事很自律','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),c=field('父亲','parents','childhood',{evidence:e,scope:{subject:'parents',period:'childhood',relation_evidence:e}}),s=source('SK04',text),first=G.analyze('SK04',[s],proposal({'SK04-E1':a,'SK04-E3':b,'SK04-E2.actor':c}));
 assert.equal(first.fields['SK04-E2.actor'].state,'known');
 const next=source('SK04',nextText,'u2',{question:'您还有想补充的吗？'}),refs=[ref(nextText,'u2')],wrong=field('邻居','neighbors','childhood',{evidence:refs,scope:{subject:'neighbors',period:'childhood',relation_evidence:refs}});
 return G.analyze('SK04',[s,next],proposal({'SK04-E2.actor':wrong}),{previous_fields:first.fields,current_question:next.question});
}
test('a rejected inactive candidate cannot erase a previously validated same-question fact',()=>{
 const r=cachedActorFixture('邻居从门口路过。');assert.equal(r.decision,'ready');assert.equal(r.fields['SK04-E2.actor'].state,'known');assert.equal(r.fields['SK04-E2.actor'].value,'父亲');assert(r.inactive_conditional_errors.length);assert.equal(r.provenance['SK04-E2.actor'],'validated_cache_survives_invalid_inactive_candidate');
});
test('a real user correction cannot be hidden behind cached inactive information',()=>{
 const r=cachedActorFixture('刚才说错了，实际是妈妈教我，邻居只是路过。');assert.equal(r.decision,'invalid');assert(r.errors.some(x=>x.startsWith('SK04-E2.actor:')));
});
test('explicit empty missing normalizes before unused citation alias',()=>{
 const r=G.analyze('SK03',[source('SK03','父亲种田。')],proposal({'SK03-E1':{state:'missing',value:null,evidence:[],scope:{subject:'self',period:'childhood',relation_evidence:'same_as_evidence'}}}));assert.equal(r.decision,'ask');assert.equal(r.fields['SK03-E1'].state,'missing');assert.equal(r.errors.length,0);
});
test('missing carrying real evidence stays invalid even with citation alias',()=>{
 const r=G.analyze('SK03',[source('SK03','父亲种田。')],proposal({'SK03-E1':{state:'missing',value:null,evidence:[ref('父亲种田。')],scope:{subject:'self',period:'childhood',relation_evidence:'same_as_evidence'}}}));assert.equal(r.decision,'invalid');
});
test('age is relative timing, not calendar year or duration exact',()=>{
 const r=G.analyze('GR01',[source('GR01','我九岁才开始上学。')],proposal({'GR01-E1':field('九岁','self','school_years',{precision:'exact',evidence:[ref('我九岁才开始上学。')],scope:{subject:'self',period:'school_years',relation_evidence:[ref('我九岁才开始上学。')]}})}));assert.equal(r.fields['GR01-E1'].precision,'relative');assert.equal(r.errors.length,0);
});
test('literal family act explicitly moves narrator, object-first grammar',()=>{
 const text='我太太决定陪我留下，这句话使我太感动了，我知道家人就是我的依靠。';const r=G.analyze('FM07',[source('FM07',text)],proposal({'FM07-E2':field('我太太决定陪我留下','self','lifelong',{evidence:[ref(text)],scope:{subject:'self',period:'lifelong',relation_evidence:[ref(text)]}})}));assert.equal(r.fields['FM07-E2'].state,'known');assert.equal(r.errors.length,0);
});
test('relation shorthand binds only a uniquely witnessed own-source literal',()=>{
 const text='我是个慢热的人。',f=field('慢热');f.evidence=[ref(text)];f.scope.relation_evidence=[text];const r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'ready');assert.deepEqual(r.fields['SK05-E1'].scope.relation_evidence,[ref(text)]);assert(r.protocol_normalizations.some(x=>x.rule==='bind_unique_literal_relation_shorthand_to_same_question_source'));
});
test('duplicated shorthand source remains ambiguous protocol, no guessed reference',()=>{
 const text='我是个慢热的人。',f=field('慢热');f.evidence=[ref(text)];f.scope.relation_evidence=[text];const r=G.analyze('SK05',[source('SK05',text),source('SK05',text,'u2')],proposal({'SK05-E1':f}));assert.equal(r.decision,'invalid');
});
test('invented shorthand never receives an own-source ID',()=>{
 const f=field('慢热');f.evidence=[ref('我很慢热。')];f.scope.relation_evidence=['我很开朗。'];assert.equal(G.analyze('SK05',[source('SK05','我很慢热。')],proposal({'SK05-E1':f})).decision,'invalid');
});
test('literal co-residence includes a self-reported non-divided household sharing meals',()=>{
 const text='我们都不分家，我们家庭人口二十多个，在一起吃饭。',e=[ref(text)],r=G.analyze('SK03',[source('SK03',text,'u1',{question:'小时候家里情况怎样？'})],proposal({'SK03-E1':field(text,'family','childhood',{evidence:e,scope:{subject:'family',period:'childhood',relation_evidence:e}})}));assert.equal(r.fields['SK03-E1'].state,'known');assert.equal(r.errors.length,0);
});
test('ancestral households still do not prove narrators own co-residence',()=>{
 const text='祖父说他小时候大家族不分家，在一起吃饭。',r=G.analyze('SK03',[source('SK03',text,'u1',{question:'请谈祖父的经历。'})],proposal({'SK03-E1':field(text,'family','childhood')}));assert.equal(r.decision,'ask');assert(r.semantic_rejections.length);
});
test('organization name with young does not establish narrators youth stage',()=>{
 const text='我应聘青年文艺协会，后来到协会报到。',e=[ref(text)],r=G.analyze('WK05',[source('WK05',text,'u1',{question:'您谈谈这次报到。'})],proposal({'WK05-E1':field('到协会报到','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}})}));assert.equal(r.fields['WK05-E1'].state,'ambiguous');
});
test('first work alone does not prove youth without an actual stage question',()=>{
 const text='这是我的第一份工作，我决定开一间书店。',e=[ref(text)],r=G.analyze('WK05',[source('WK05',text,'u1',{question:'您谈谈开店的事。'})],proposal({'WK05-E1':field('我决定开一间书店','self','youth',{evidence:e,scope:{subject:'self',period:'youth',relation_evidence:e}})}));assert.equal(r.fields['WK05-E1'].state,'ambiguous');
});
test('unique simplified citation restores original exact traditional source with audit',()=>{
 const text='我生於民國四十年，家人總是鼓勵我讀書。',f=field('家人总是鼓励我读书','family','childhood',{evidence:[ref('家人总是鼓励我读书。')],scope:{subject:'family',period:'childhood',relation_evidence:'same_as_evidence'}}),r=G.analyze('SK04',[source('SK04',text,'u1',{question:'家人如何教育您？'})],proposal({'SK04-E1':f}));assert.equal(r.fields['SK04-E1'].value,'家人總是鼓勵我讀書');assert.equal(r.fields['SK04-E1'].evidence[0].quote,'家人總是鼓勵我讀書。');assert.equal(r.errors.length,0);assert(r.protocol_normalizations.some(x=>x.rule==='restore_unique_script_variant_to_original_literal'));
});
test('script restoration cannot invent a claim with different semantic characters',()=>{
 const text='家人總是鼓勵我讀書。',f=field('家人总是鼓励我经商','family','childhood',{evidence:[ref('家人总是鼓励我经商。')],scope:{subject:'family',period:'childhood',relation_evidence:'same_as_evidence'}}),r=G.analyze('SK04',[source('SK04',text)],proposal({'SK04-E1':f}));assert.equal(r.decision,'invalid');
});
test('canonical collision between two different original phrases is not guessed',()=>{
 const text='我寫「乾」字，也我寫「幹」字。',f=field('干','self','lifelong',{evidence:[ref('我写「干」字')],scope:{subject:'self',period:'lifelong',relation_evidence:'same_as_evidence'}}),r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'invalid');
});
test('script anchoring keeps codepoint offsets after a non-BMP character',()=>{
 const text='𠮷字之后，我總是很謹慎。',f=field('我总是很谨慎','self','lifelong',{evidence:[ref('我总是很谨慎。')],scope:{subject:'self',period:'lifelong',relation_evidence:'same_as_evidence'}}),r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'ready');assert.equal(r.fields['SK05-E1'].value,'我總是很謹慎');assert.equal(r.fields['SK05-E1'].evidence[0].quote,'我總是很謹慎。');
});
test('a model cannot forge internal stage confirmation to bypass stage evidence',()=>{
 const text='我开店很辛苦。',f=field(text,'self','as_stated',{stage_binding:{stage:'youth',state:'known'}}),r=G.analyze('WK03',[source('WK03',text,'u1',{question:'请谈开店。'})],proposal({'WK03-E1':f}));assert.equal(r.fields['WK03-E1'].state,'ambiguous');assert.equal(r.fields['WK03-E1'].stage_binding,undefined);assert(r.protocol_normalizations.some(x=>x.rule==='discard_untrusted_engine_owned_attributes'));
});
test('model-supplied secondary statements cannot introduce unvalidated claims',()=>{
 const text='我慢热。',f=field(text,'self','lifelong',{statements:[{text:'我外向。',evidence:[ref('我外向。')],scope:{subject:'self',period:'lifelong',relation_evidence:[ref('我外向。')]}}]}),r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'ready');assert.equal(r.fields['SK05-E1'].statements,undefined);assert.equal(r.fields['SK05-E1'].value,text);
});
test('grounded required stage canonicalizes an as-stated period label',()=>{
 const text='我年轻时开店很辛苦。',r=G.analyze('WK03',[source('WK03',text,'u1',{question:'请谈开店。'})],proposal({'WK03-E1':field('开店很辛苦','self','as_stated',{evidence:[ref(text)],scope:{subject:'self',period:'as_stated',relation_evidence:[ref(text)]}})}));assert.equal(r.fields['WK03-E1'].state,'known');assert.equal(r.fields['WK03-E1'].scope.period,'youth');
});
test('a root link can be routed only to the unique declared explanation field',()=>{
 const text='我第一份工作是织布，因为家里没钱。',e=[ref(text)],a=field('织布','self','as_stated',{evidence:e,scope:{subject:'self',period:'as_stated',relation_evidence:e}}),b=field('家里没钱','self','as_stated',{evidence:e,scope:{subject:'self',period:'as_stated',relation_evidence:e}}),p=proposal({'WK01-E1':a,'WK01-E2':b});p.links=[{field_id:'WK01-E1',value:'织布'}];const r=G.analyze('WK01',[source('WK01',text)],p);assert.equal(r.decision,'ready');assert.deepEqual(r.fields['WK01-E2'].links,p.links);assert(r.protocol_normalizations.some(x=>x.rule==='route_root_links_to_unique_declared_explanation'));
});
test('conflicting root and field links remain strict protocol failure',()=>{
 const text='操心，因为家里事情都是我张罗。',e=[ref(text)],a=field('操心','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),b=field('家里事情都是我张罗','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e},links:[{field_id:'SK06-E1',value:'奔波'}]}),p=proposal({'SK06-E1':a,'SK06-E2':b});p.links=[{field_id:'SK06-E1',value:'操心'}];assert.equal(G.analyze('SK06',[source('SK06',text)],p).decision,'invalid');
});
test('root links without an actual explanation candidate cannot create one',()=>{
 const p=proposal({'SK06-E1':field('操心')});p.links=[{field_id:'SK06-E1',value:'操心'}];assert.equal(G.analyze('SK06',[source('SK06','操心')],p).decision,'invalid');
});
test('a script variant link resolves only one accepted original selected word',()=>{
 const text='我選勤儉，因為我一直省吃儉用。',e=[ref(text)],a=field('勤儉','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),b=field('我一直省吃儉用','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e},links:[{field_id:'SK06-E1',value:'勤俭'}]}),r=G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':a,'SK06-E2':b}));assert.equal(r.decision,'ready');assert.equal(r.fields['SK06-E2'].links[0].value,'勤儉');
});
test('script-colliding selected words do not justify guessing the explanation link',()=>{
 const text='我選乾、幹，因為我總在做事。',e=[ref(text)],a=field(['乾','幹'],'self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),b=field('我總在做事','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e},links:[{field_id:'SK06-E1',value:'干'}]}),r=G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':a,'SK06-E2':b}));assert.equal(r.decision,'invalid');assert(r.errors.includes('SK06-E2:unbound_explanation_link'));
});
test('selected keyword link restoration does not substitute a lexical synonym',()=>{
 const text='我選姊妹，因為我們總互相照顧。',e=[ref(text)],a=field('姊妹','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e}}),b=field('我們總互相照顧','self','lifelong',{evidence:e,scope:{subject:'self',period:'lifelong',relation_evidence:e},links:[{field_id:'SK06-E1',value:'姐妹'}]}),r=G.analyze('SK06',[source('SK06',text)],proposal({'SK06-E1':a,'SK06-E2':b}));assert.equal(r.decision,'invalid');
});
test('selected original units expand before the same literal and role guards',()=>{
 const text='我很慢热。熟了话就多。',ss=[source('SK05',text)],u=G.evidenceUnits('SK05',ss),p=proposal({'SK05-E1':{state:'known',value:'我很慢热',evidence_unit_ids:[u[0].id],scope:{subject:'self',period:'lifelong',relation_unit_ids:'same_as_evidence'}}}),r=G.analyze('SK05',ss,p);assert.equal(r.decision,'ready');assert.equal(r.fields['SK05-E1'].evidence[0].quote,'我很慢热。');assert(r.protocol_normalizations.some(x=>x.rule==='expand_selected_original_evidence_units'));
});
test('a unit cannot manufacture a value absent from the original text',()=>{
 const ss=[source('SK05','我很慢热。')],u=G.evidenceUnits('SK05',ss),r=G.analyze('SK05',ss,proposal({'SK05-E1':{state:'known',value:'我很外向',evidence_unit_ids:[u[0].id],scope:{subject:'self',period:'lifelong',relation_unit_ids:'same_as_evidence'}}}));assert.equal(r.decision,'invalid');
});
test('foreign or nonexistent unit IDs never receive fabricated evidence',()=>{
 const ss=[source('SK05','我很慢热。'),source('SK04','家里很严格。','u2')],r=G.analyze('SK05',ss,proposal({'SK05-E1':{state:'known',value:'家里很严格',evidence_unit_ids:['S2.1'],scope:{subject:'self',period:'lifelong',relation_unit_ids:'same_as_evidence'}}}));assert.equal(r.decision,'invalid');assert.equal(r.fields['SK05-E1'].state,'missing');
});
test('unit selections still cannot confuse another persons life stage with narrator',()=>{
 const text='我父亲二十岁毕业。我后来开店很辛苦。',ss=[source('WK03',text,'u1',{question:'请谈开店。'})],u=G.evidenceUnits('WK03',ss),r=G.analyze('WK03',ss,proposal({'WK03-E1':{state:'known',value:'开店很辛苦',evidence_unit_ids:[u[1].id],scope:{subject:'self',period:'youth',relation_unit_ids:u.map(x=>x.id)}}}));assert.equal(r.fields['WK03-E1'].state,'ambiguous');
});
test('current pause through a unit keeps pause priority and literal audit',()=>{
 const ss=[source('SK01','今天累了，先到这里。')],u=G.evidenceUnits('SK01',ss),p={control:{action:'pause',evidence_unit_ids:[u[0].id]},fields:{'SK01-E1':field('伪造')}},r=G.analyze('SK01',ss,p);assert.equal(r.decision,'paused');assert(r.errors.length);assert(r.protocol_normalizations.some(x=>x.rule==='expand_control_evidence_units'));
});
test('a singleton subject-array is losslessly normalized to its one explicit role',()=>{
 const text='我很慢热。',f=field(text);f.scope.subject=['self'];const r=G.analyze('SK05',[source('SK05',text)],proposal({'SK05-E1':f}));assert.equal(r.decision,'ready');assert.equal(r.fields['SK05-E1'].scope.subject,'self');assert(r.protocol_normalizations.some(x=>x.rule==='singleton_subject_array_to_scalar'));
});
test('multiple subject candidates get a precise internal type error, never guessed',()=>{
 const text='家里种田，我也帮忙。',f=field(text,'family','childhood');f.scope.subject=['self','family'];const r=G.analyze('SK03',[source('SK03',text)],proposal({'SK03-E2':f}));assert.equal(r.decision,'invalid');assert(r.errors.some(x=>x.includes('subject_must_be_one_string_not_array')));assert.equal(r.fields['SK03-E2'].state,'missing');
});
test('scene with no temporal words cannot create an ambiguous time answer',()=>{
 const text='我家在村子里，大家住土房。',e=[ref(text)],f=terminal('ambiguous',text,'self','unspecified',{clarifications:['period']}),r=G.analyze('SK01',[source('SK01',text,'u1',{question:'老家什么样？'})],proposal({'SK01-E4':field('大家住土房','self','as_stated',{evidence:e,scope:{subject:'self',period:'as_stated',relation_evidence:e}}),'SK01-E3.period':f}));assert.equal(r.fields['SK01-E3.period'].state,'missing');assert(r.rejected_candidates.some(x=>x.reason==='period_ambiguity_without_temporal_material'));assert.equal(r.target,'SK01-E1');
});
test('an actual unresolved temporal expression remains ambiguous and preserved',()=>{
 const text='那阵子家里都住土房。',f=terminal('ambiguous',text,'self','unspecified',{clarifications:['period']}),r=G.analyze('SK01',[source('SK01',text,'u1',{question:'老家什么样？'})],proposal({'SK01-E3.period':f}));assert.equal(r.fields['SK01-E3.period'].state,'ambiguous');
});
test('a short unclear answer to an actual time-target question is not discarded',()=>{
 const text='差不多吧。',f=terminal('ambiguous',text,'self','unspecified',{clarifications:['period']}),ss=[source('SK01',text,'u1',{question:'您说的这处地方的样子，是哪个时候的印象？',target_field_id:'SK01-E3.period'})],r=G.analyze('SK01',ss,proposal({'SK01-E3.period':f}),{focus:{field_id:'SK01-E3.period'}});assert.equal(r.fields['SK01-E3.period'].state,'ambiguous');
});
const report={kind:'synthetic_code_guard_regression',version:G.version,tests:results.length,passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass),results};
fs.writeFileSync(path.join(__dirname,'guard-results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,results:undefined},null,2));process.exitCode=report.failed.length?1:0;
