'use strict';
/* Optional transport adapter. It never changes strings/values or supplies a missing field. */
function parseProposal(raw,metadata={}) {
  if(typeof raw!=='string')return {ok:false,proposal:null,errors:['raw_json_not_string'],normalizations:[]};
  try{return {ok:true,proposal:JSON.parse(raw),errors:[],normalizations:[]};}catch(originalError){
    const failed={ok:false,proposal:null,errors:['json_parse_error'],normalizations:[],original_parse_error:originalError.message};
    if(metadata.finish_reason!=='stop'||raw.length>262144)return failed;
    const text=raw.trim();if(!text.startsWith('{'))return failed;
    const stack=[];let inString=false,escaped=false,bad=false;
    for(const c of text) {
      if(inString){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')inString=false;continue;}
      if(c==='"'){inString=true;continue;}
      if(c==='{'||c==='[')stack.push(c);
      else if(c==='}'||c===']'){const wanted=c==='}'?'{':'[';if(stack.pop()!==wanted){bad=true;break;}}
    }
    // Exactly the outer root object may be open; every nested value must already be complete.
    if(bad||inString||escaped||stack.length!==1||stack[0]!=='{')return failed;
    const normalized=text+'}';
    try {
      const proposal=JSON.parse(normalized);
      return {ok:true,proposal,errors:[],original_parse_error:originalError.message,
        normalizations:[{rule:'append_only_missing_root_object_brace',original_raw:raw,normalized_raw:normalized}]};
    }catch(_){return failed;}
  }
}
module.exports={parseProposal};
