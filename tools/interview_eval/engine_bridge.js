'use strict';
// Persistent JSON-lines bridge to one interview runtime's engine.js.
// One request per line on stdin: {"id":..,"op":..,"args":{..}}; one reply per line.
const path = require('path');
const readline = require('readline');
const runtime = path.resolve(process.argv[2]);
const g = require(path.join(runtime, 'engine.js'));

function contracts() {
  const protocol = g.getContract().output_protocol || {};
  return {
    fields: g.fields, questions: g.baseQuestion,
    evidence_unit_protocol: protocol.evidence_units || null,
    model_source_fields: protocol.model_source_fields || null,
    model_input_projection: protocol.model_input_projection || null,
    review_mode: protocol.review_mode || null, workflow: protocol.workflow || null,
    field_verification: protocol.field_verification || null,
    model_field_contract_keys: protocol.model_field_contract_keys || null,
    question_contracts: Object.fromEntries(Object.keys(g.baseQuestion).map(id => {
      const q = g.getContract(id);
      return [id, {premise: q.premise, success: q.success, notes: q.notes, material_type: q.material_type}];
    })),
  };
}

function analyze({payload, proposal, raw}) {
  let parseAudit = null, r;
  if (proposal == null && raw && raw.parse_error && typeof g.parseProposal === 'function') {
    parseAudit = g.parseProposal(raw.raw_content, {finish_reason: raw.finish_reason});
    if (parseAudit.ok) proposal = parseAudit.proposal;
  }
  try {
    r = g.analyze(payload.question_id, payload.sources, proposal, {
      current_question: payload.current_question, focus: payload.focus,
      previous_fields: payload.previous_fields, ask_counts: payload.ask_counts});
  } catch (e) { r = {decision: 'invalid', errors: ['engine_exception:' + e.message], fields: {}}; }
  if (parseAudit) r.transport_parse_audit = {ok: parseAudit.ok, original_parse_error: parseAudit.original_parse_error,
    normalizations: parseAudit.normalizations, errors: parseAudit.errors};
  return r;
}

const ops = {
  contracts: () => contracts(),
  evidence_units: ({question_id, sources}) => g.evidenceUnits(question_id, sources),
  model_input: ({payload}) => g.modelInput(payload),
  analyze,
  review_input: ({payload, candidate, checked}) => typeof g.reviewInput === 'function' ? g.reviewInput(payload, candidate, checked) : {
    ...payload, semantic_review: {unverified_candidate: candidate,
      code_validation_errors: [...(checked.errors || []), ...(checked.semantic_rejections || []).map(x => x.field_id + ':' + x.reason)],
      instruction: 'Audit all fields against own sources and contract, including omissions; no gold supplied.'}},
  repair_context: ({payload, result}) => g.repairContext(payload, result),
  get_contract: ({question_id}) => g.getContract(question_id),
  call: ({fn, args}) => g[fn](...args),
};

const rl = readline.createInterface({input: process.stdin});
rl.on('line', line => {
  let msg;
  try { msg = JSON.parse(line); } catch (e) { process.stdout.write(JSON.stringify({id: null, error: 'bad_json'}) + '\n'); return; }
  let reply;
  try { reply = {id: msg.id, result: ops[msg.op](msg.args || {})}; }
  catch (e) { reply = {id: msg.id, error: String(e && e.stack || e).slice(0, 2000)}; }
  process.stdout.write(JSON.stringify(reply) + '\n');
});
