#!/usr/bin/env python3
"""Uniform whole-person development sampling. Never reads outcome scores."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import secrets

def select(data, count, seed):
    if not 5 <= count <= 10:
        raise ValueError('select 5–10 people')
    people=data['narrators']
    ids=sorted(n['id'] for n in people)
    if len(set(ids))!=len(ids) or any(n.get('split')!='development' for n in people):
        raise ValueError('unique development people only; heldout people are excluded')
    selected=set(random.Random(seed).sample(ids,count))
    out=copy.deepcopy(data)
    out['narrators']=[n for n in out['narrators'] if n['id'] in selected]
    out['cases']=[c for c in out['cases'] if c['narrator_id'] in selected]
    if {c['narrator_id'] for c in out['cases']}!=selected:
        raise ValueError('every selected person needs actual cases')
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--people',type=int,default=8)
    p.add_argument('--seed',type=int)
    a=p.parse_args()
    if a.out.exists(): raise ValueError('never replace a previously drawn batch')
    manifest=a.runtime/'manifest.json'
    if not manifest.is_file(): raise ValueError('freeze/verify candidate manifest before sampling')
    seed=a.seed if a.seed is not None else secrets.randbits(64)
    data=json.loads(a.dataset.read_text());out=select(data,a.people,seed)
    meta={'algorithm':'sorted development IDs + Python Random(seed).sample, uniform without replacement',
          'seed':seed,'people':len(out['narrators']),'cases':len(out['cases']),
          'checkpoints':sum(len(c['turns']) for c in out['cases']),
          'questions':sorted({c['question_id'] for c in out['cases']}),
          'narrator_ids':sorted(n['id'] for n in out['narrators']),
          'parent_dataset_sha256':hashlib.sha256(a.dataset.read_bytes()).hexdigest(),
          'runtime_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
          'all_selected_people_cases_and_turns':True,'scores_not_used_for_selection':True,
          'not_full55_acceptance':True,'not_an_unseen_accuracy_estimate':True}
    out.setdefault('authoring',{})['random_iteration']=meta
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    a.out.with_suffix('.selection.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(meta,ensure_ascii=False))

if __name__=='__main__':main()
