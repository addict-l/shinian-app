#!/usr/bin/env python3
"""Read-only gate for the user's random5–10 whole-person iteration policy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.prepare_random_interview_iteration import select

def gate(data,parent,scores,audit,runtime_manifest_sha):
    meta=data.get('authoring',{}).get('random_iteration',{})
    n=len(data['narrators']);planned=sum(len(c['turns']) for c in data['cases'])
    o=scores['overall'];passed=o['all_critical_checkpoint_passes']
    reproduced=select(parent,n,meta['seed'])
    checks={
      'five_to_ten_development_people':5<=n<=10 and all(p['split']=='development' for p in data['narrators']),
      'sample_reproduces_from_recorded_seed':reproduced['narrators']==data['narrators'],
      'all_selected_people_cases_and_turns_unchanged':reproduced['cases']==data['cases'],
      'candidate_frozen_before_execution':runtime_manifest_sha==meta['runtime_manifest_sha256'],
      'complete_batch_no_unexecuted_or_unresolved_calls':planned>0 and o['planned_checkpoints']==planned and o['evaluated_checkpoints']==planned and o['unexecuted']==0 and o['transport_errors']==0,
      'actual_DS_witness_for_every_selected_person':audit.get('passed') is True and audit.get('actual_distinct_narrator_ids')==n and audit.get('actual_distinct_names')==n and audit.get('errors')==0,
      'substantive_checks_present':o['substantive_field_checks']>0,
      'critical_strictly_above_95':passed*100>95*planned,
    }
    return {'scope':'This complete random development batch only; not full55/all62 or unseen accuracy.',
            'accepted':all(checks.values()),'checks':checks,'people':n,'cases':len(data['cases']),
            'questions':len({c['question_id'] for c in data['cases']}),'critical_passes':passed,
            'checkpoints':planned,'critical_rate':passed/planned if planned else None,
            'supported_passes':o['substantive_field_passes'],'supported_checks':o['substantive_field_checks'],
            'protocol_invalid':o['protocol_invalid'],'selection':meta}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    spec=importlib.util.spec_from_file_location('random_gate_frozen_runner',a.run/'runner.snapshot.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    freeze=json.loads((a.run/'freeze.json').read_text())
    if freeze['model'] not in runner.ALLOWED_DS_MODELS:raise ValueError('this gate requires real DeepSeek')
    runner.MODEL=freeze['model'];runner.ROOT=root
    runner.verify(a.run)
    data=json.loads((a.run/'dataset.json').read_text());parent=json.loads(a.parent.read_text())
    meta=data['authoring']['random_iteration']
    if hashlib.sha256(a.parent.read_bytes()).hexdigest()!=meta['parent_dataset_sha256']:raise ValueError('parent dataset changed')
    auditpath=a.out.with_suffix('.audit.json')
    subprocess.run([sys.executable,str(root/'tools/audit_full_interview_runs.py'),str(a.run),'--out',str(auditpath)],check=True,capture_output=True,text=True)
    audit=json.loads(auditpath.read_text());scores=json.loads((a.run/'scores.json').read_text())
    result=gate(data,parent,scores,audit,hashlib.sha256((a.run/'runtime/manifest.json').read_bytes()).hexdigest())
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
    return 0 if result['accepted'] else 1

if __name__=='__main__':sys.exit(main())
