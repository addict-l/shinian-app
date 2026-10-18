'use strict';
// Bounded current-stage proof. Labels and unrelated time phrases are not proof.
const NOW=/(现在|目前|如今|最近|近来|近期|当前|当下|这阵子|眼下|这些天|这几年)/g;
const PAST=/(小时候|年轻时|青年时|童年|以前|过去|曾经|从前|当年|当时|那年|那时候)/g;
const FUTURE=/(将来|未来|等[^，,。！？；;\n]{0,16}(?:以后|之后|后)|^(?:我|我们)?(?:以后|将来|未来))/g;
const lastIndex=(pattern,text)=>Math.max(-1,...[...text.matchAll(new RegExp(pattern.source,pattern.flags))].map(m=>m.index));
const canonical=t=>t.replace(/以后|之后/g,'后');
function current(obj,sources,normalize=x=>x) {
  const values=(Array.isArray(obj.value)?obj.value:[obj.value]).filter(v=>typeof v==='string').map(normalize);
  const refs=obj.evidence||[],relations=obj.scope.relation_evidence||[];
  const states=[],reasons=[];
  for(const s of sources) {
    const own=refs.filter(r=>r.source_id===s.id);if(!own.length)continue;
    const text=normalize(s.text),question=normalize(s.question||'');
    const questionPlans=[...question.matchAll(/([^，,。！？?；;\n]{1,12}(?:以后|之后|后)).{0,6}(?:打算|计划|准备|想|希望)/g)].map(m=>canonical(m[1].trim()));
    const competingQuestion=lastIndex(PAST,question)>=0||questionPlans.length>0||/(将来|未来|[，,。！？?；;]\s*(?:你|您)?以后)/.test(question);
    const questionNow=!competingQuestion&&(/现在|目前|如今|最近|近期|当下|当前|日常|每天|平时/.test(question));
    const proof=normalize(relations.filter(r=>r.source_id===s.id).map(r=>r.quote).join(' '));
    const ranges=[];
    for(const r of own) {
      const quote=normalize(r.quote);let start=text.indexOf(quote);
      while(start>=0){ranges.push([start,start+quote.length]);start=text.indexOf(quote,start+Math.max(1,quote.length));}
    }
    let phase=questionNow?'now':'unknown',origin=null,start=0;
    for(const m of text.matchAll(/[，,。！？!?；;\n]+|$/g)) {
      const end=m.index,clause=text.slice(start,end),offset=start;start=end+m[0].length;
      if(!clause.trim())continue;
      const n=lastIndex(NOW,clause),p=lastIndex(PAST,clause),f=lastIndex(FUTURE,clause);
      const lead=clause.trim().replace(/^(?:(?:我|我们|本人|也|还|就|一直|最近|现在|目前|如今|当下|当前)\s*)+/,'');
      const intent=/^(?:打算|计划|想要|想去|希望|(?:有时间|有空).{0,4}(?:可能|也许)?会|准备(?:去|开始|学|练|每天|每周|明年|下个月|以后|将来))/.test(lead);
      const planned=questionPlans.some(anchor=>canonical(clause).includes(anchor));
      let next=null;
      if(intent)next='future';
      else if(n>=0&&n>=p&&n>=f)next='now';
      else if(f>=0||planned)next='future';
      else if(p>=0)next='past';
      if(next){phase=next;origin=clause;}
      const selected=ranges.some(([a,b])=>offset<b&&end>a)&&values.some(v=>clause.includes(v)||v.includes(clause.trim()));
      if(!selected)continue;
      if(phase!=='now') {states.push(false);reasons.push(phase+'_selected_clause');continue;}
      // Full source context may disprove a claim, but a positive time anchor
      // must itself be cited or supplied by an unambiguous actual question.
      const grounded=questionNow||Boolean(origin&&lastIndex(NOW,proof)>=0);
      states.push(grounded);
      if(!grounded)reasons.push('current_time_anchor_not_cited');
    }
  }
  if(!states.length)reasons.push('no_selected_clause_identified');
  return {anchored:states.length>0&&states.every(Boolean),reasons:[...new Set(reasons)],selected_clause_count:states.length};
}
module.exports={current};
