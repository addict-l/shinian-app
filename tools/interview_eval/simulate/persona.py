"""Persona material for the elder simulator: only the person's own published words from the 55-person test set.

- Source: excerpts.jsonl (development people). Provenance rules from provenance-warning.json are applied:
  excerpts whose speaker is not the catalog narrator (VAC-402/403 = 林恆富's wife) are excluded; excerpts with
  mixed editorial text or multi-question PDF headers are used only in their manually clipped form (the clip the
  test set's own case files carry), never whole.
- Per question, the simulator "remembers" the excerpts the test set maps to that question (excerpt ids only --
  never any expected field, follow-up label or system state) plus lexically related excerpts, up to a cap.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.environ.get('SHINIAN_EVAL_HOME', ROOT / '.runtime/interview-eval'))
TESTSET = Path(os.environ.get('SHINIAN_TESTSET_DIR', WORK / 'testset'))
DATASET = Path(os.environ.get('SHINIAN_EVAL_RUNS', WORK / 'runs')) / 'datasets/full45.json'
CONTRACTS = ROOT / 'docs/prototypes/full-interview-v3j/contracts.json'
CHAR_MAP = json.loads((ROOT / 'docs/prototypes/full-interview-v3j/opencc-ts-char-map.json').read_text(encoding='utf-8'))

EXCLUDE_SOURCES = {('N-3b7bd23f91', 'VAC-402'), ('N-3b7bd23f91', 'VAC-403')}  # speaker is the narrator's wife
CLIP_ONLY = {'WEB-changshana2-E006', 'WEB-yangjiang-E001', 'WEB-yangjiang-E002',
             'CASA-fe7c1686-Q01', 'CASA-82d14eeb-Q01', 'CASA-47fee5f0-Q01', 'CASA-c8625984-Q01',
             'CASA-c5a5031a-Q01', 'CASA-f522cea6-Q01', 'CASA-8e9398ae-Q01', 'CASA-df0eb596-Q01', 'CASA-e561eaa8-Q01'}
MATERIAL_CAP = 1000      # characters of remembered material per question
EXCERPT_CAP = 420        # a single non-mapped excerpt is cut to this many characters
SMALL_PERSON = 1000      # people with at most this much material remember all of it for every question


def simp(text):
    return ''.join(CHAR_MAP.get(c, c) for c in str(text or ''))


FUNC = set('的您你我他她它们么样怎里候得了是有在或及与本这那对把被就都也还又很最什哪谁吗呢吧啊着过来去上下中为以于从和跟会能要想说一个些其所之')


def bigrams(text):
    t = re.sub(r'[^一-鿿]', '', simp(text))
    return {t[i:i + 2] for i in range(len(t) - 1) if t[i] not in FUNC and t[i + 1] not in FUNC}


STOP = bigrams('时间小时以后以前后来当时现在觉得自己生里')
MIN_SCORE = 2.0


class Personas:
    def __init__(self):
        self.contracts = json.loads(CONTRACTS.read_text(encoding='utf-8'))
        self.Q = {q['id']: q for q in self.contracts['questions']}
        data = json.loads(DATASET.read_text(encoding='utf-8'))
        self.names = {n['id']: n['name'] for n in data['narrators']}
        rows = [json.loads(line) for line in (TESTSET / 'excerpts.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        clipped = {}
        self.mapped = defaultdict(lambda: defaultdict(list))  # nid -> qid -> [excerpt ids]   (mapping only)
        for case in data['cases']:
            for turn in case['turns']:
                s = turn['source']
                eid = s.get('source_excerpt_id') or s['id']
                clipped.setdefault(eid, s['text'])
                if eid not in self.mapped[case['narrator_id']][case['question_id']]:
                    self.mapped[case['narrator_id']][case['question_id']].append(eid)
        self.excerpts = defaultdict(list)  # nid -> [{id, question, text, mapped_clip}]
        for r in rows:
            if (r['narrator_id'], r['source_id']) in EXCLUDE_SOURCES:
                continue
            text = r['text']
            if r['id'] in CLIP_ONLY:
                if r['id'] not in clipped:
                    continue
                text = clipped[r['id']]
            self.excerpts[r['narrator_id']].append({'id': r['id'], 'question': r.get('interviewer_question') or '',
                                                     'text': text.strip()})
        self.order = {nid: {e['id']: k for k, e in enumerate(ex)} for nid, ex in self.excerpts.items()}

    def people(self):
        return sorted(self.excerpts)

    def total_chars(self, nid):
        return sum(len(e['text']) for e in self.excerpts[nid])

    def mapped_questions(self, nid):
        return [q for q in self.contracts['default_order'] if self.mapped[nid].get(q)]

    def query_terms(self, qid):
        q = self.Q[qid]
        parts = [q['main_question'], q.get('title') or '']
        parts += [f['label'] for f in q['elements'] if f['requirement'] != 'optional']
        return bigrams(' '.join(parts)) - STOP

    def material(self, nid, qid):
        """The excerpts the simulated person can draw on for this question (list of {id, question, text})."""
        ex = self.excerpts[nid]
        if self.total_chars(nid) <= SMALL_PERSON:
            return [dict(e) for e in ex]
        by_id = {e['id']: e for e in ex}
        chosen, used = [], 0
        for eid in self.mapped[nid].get(qid, []):
            if eid in by_id and eid not in [c['id'] for c in chosen]:
                e = dict(by_id[eid])
                chosen.append(e)
                used += len(e['text'])
        terms = self.query_terms(qid)
        scored = []
        for e in ex:
            if e['id'] in [c['id'] for c in chosen]:
                continue
            qb, tb = bigrams(e['question']) - STOP, bigrams(e['text'][:600]) - STOP
            score = 2.0 * len(terms & qb) + len(terms & tb) / math.sqrt(max(1, len(tb)) / 20)
            scored.append((score, self.order[nid][e['id']], e))
        scored.sort(key=lambda x: (-x[0], x[1]))
        for score, _, e in scored:
            if used >= MATERIAL_CAP or score < MIN_SCORE:
                break
            e = dict(e)
            room = max(120, min(EXCERPT_CAP, MATERIAL_CAP - used))
            if len(e['text']) > room:
                e['text'] = e['text'][:room] + '……'
            chosen.append(e)
            used += len(e['text'])
        if not chosen:  # nothing related at all: the opening excerpt (who the person is)
            e = dict(ex[0])
            e['text'] = e['text'][:EXCERPT_CAP]
            chosen.append(e)
        chosen.sort(key=lambda e: self.order[nid][e['id']])
        return chosen

    @staticmethod
    def render(material):
        lines = []
        for e in material:
            q = (e['question'] or '').strip()
            lines.append(('【当时被问】' + q + '\n' if q else '') + '【你讲的】' + e['text'])
        return '\n'.join(lines)
