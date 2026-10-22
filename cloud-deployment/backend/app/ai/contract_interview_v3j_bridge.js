'use strict';
// Persistent JSON-lines bridge to the v3j runtime's engine.js for one judgment run.
// One request per stdin line {"id","op","args"}; one reply per stdout line. JSON over
// stdin keeps private interview material out of process arguments. Operations match
// tools/interview_eval/engine_bridge.js (contracts, evidence_units, analyze) so the
// judgment layer sees exactly the engine results it was evaluated with.
const path = require('path');
const readline = require('readline');
let g;
try {
  g = require(path.join(path.resolve(process.argv[2]), 'engine.js'));
} catch (_) {
  // Errors must not echo source text, provider output or local filesystem paths.
  process.stderr.write('contract_interview_v3j_bridge_failed');
  process.exit(1);
}

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

function analyze({payload, proposal}) {
  // The v3j assembly always hands the engine a proposal it built itself
  // (never raw provider text), so no transport parse recovery applies here.
  let r;
  try {
    r = g.analyze(payload.question_id, payload.sources, proposal, {
      current_question: payload.current_question, focus: payload.focus,
      previous_fields: payload.previous_fields, ask_counts: payload.ask_counts});
  } catch (e) { r = {decision: 'invalid', errors: ['engine_exception:' + e.message], fields: {}}; }
  return r;
}

const ops = {
  contracts: () => contracts(),
  evidence_units: ({question_id, sources}) => g.evidenceUnits(question_id, sources),
  analyze,
};

const rl = readline.createInterface({input: process.stdin});
rl.on('line', line => {
  let msg;
  try { msg = JSON.parse(line); } catch (_) { process.stdout.write(JSON.stringify({id: null, error: 'bad_request'}) + '\n'); return; }
  let reply;
  try {
    if (!Object.prototype.hasOwnProperty.call(ops, msg.op)) throw new Error('unsupported_bridge_operation');
    reply = {id: msg.id, result: ops[msg.op](msg.args || {})};
  } catch (_) { reply = {id: msg.id, error: 'bridge_operation_failed'}; }
  process.stdout.write(JSON.stringify(reply) + '\n');
});
