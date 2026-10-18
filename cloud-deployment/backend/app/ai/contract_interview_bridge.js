'use strict';
// JSON over stdin keeps private interview material out of process arguments.
const fs = require('fs');
const path = require('path');
try {
  const engine = require(path.join(path.resolve(process.argv[2]), 'engine.js'));
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  let output;
  if (input.operation === 'payload') {
    const payload = engine.buildPayload(input.question_id, input.sources, input.context || {});
    // The frozen evaluation runner includes this catalog attribute in its
    // question contract; retain byte-for-byte semantic input parity here.
    payload.question_contract.material_type = engine.getContract(input.question_id).material_type;
    payload.source_kind = 'live_interview';
    payload.historical_question_verified = Boolean(input.sources.at(-1)?.question);
    output = {payload, model_input: engine.modelInput(payload)};
  } else if (input.operation === 'review_input') {
    output = typeof engine.reviewInput === 'function'
      ? engine.reviewInput(input.model_input, input.candidate, input.checked)
      : {...input.model_input, semantic_review: {
          unverified_candidate: input.candidate,
          code_validation_errors: [...(input.checked.errors || []),
            ...(input.checked.semantic_rejections || []).map(x => x.field_id + ':' + x.reason)],
          instruction: 'Audit all fields against own sources and contract, including omissions; no gold supplied.',
        }};
  } else if (input.operation === 'analyze') {
    const payload = input.payload;
    let proposal = input.call.output, parseAudit = null;
    if (proposal == null && input.call.parse_error && typeof engine.parseProposal === 'function') {
      parseAudit = engine.parseProposal(input.call.raw_content, {finish_reason: input.call.finish_reason});
      if (parseAudit.ok) proposal = parseAudit.proposal;
    }
    output = engine.analyze(payload.question_id, payload.sources, proposal, {
      current_question: payload.current_question, focus: payload.focus,
      previous_fields: payload.previous_fields, ask_counts: payload.ask_counts,
    });
    if (parseAudit) output.transport_parse_audit = {
      ok: parseAudit.ok, original_parse_error: parseAudit.original_parse_error,
      normalizations: parseAudit.normalizations, errors: parseAudit.errors,
    };
  } else throw new Error('unsupported_bridge_operation');
  process.stdout.write(JSON.stringify(output));
} catch (_) {
  // Errors must not echo source text, provider output or local filesystem paths.
  process.stderr.write('contract_interview_bridge_failed');
  process.exitCode = 1;
}
