#!/usr/bin/env python3
"""Build or check the v3j judgment + v4d (or v5f) speaking-layer runtime bundles.

  python3 scripts/build_interview_v3j_runtime.py                       # (re)write app/ai/interview_runtime_v3j_v4d
  python3 scripts/build_interview_v3j_runtime.py --check               # verify the bundle against the tested originals
  python3 scripts/build_interview_v3j_runtime.py --bundle v5f [--check] # app/ai/interview_runtime_v3j_v5f

The v5f bundle (INTERVIEW_PIPELINE=v3j_v5f) has the same judgment files and adds the v5f speaking layer of
docs/prototypes/full-interview-v5: its speaker prompt and configuration (with the deepen block, signal scope and the
wording guards), the deepen prompt and the 23 story-question labels (story-questions.json, checked at startup
against the catalog).

Every runtime file is a byte-for-byte copy of the offline-tested original in
docs/prototypes (judgment layer v3j, speaking layer v4d) or of the identical
OpenCC provenance record of the current runtime; only provider-settings.json,
README.md and manifest.json are written here. The printed manifest SHA-256 is
the value for INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256. Needs the full repository
(docs/prototypes is not part of the deployed backend).
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
TARGET = BACKEND / 'app/ai/interview_runtime_v3j_v4d'
V3J = 'docs/prototypes/full-interview-v3j/'
V4 = 'docs/prototypes/full-interview-v4/'
V5 = 'docs/prototypes/full-interview-v5/'
SOURCES = {
    'OpenCC-LICENSE.txt': V3J + 'OpenCC-LICENSE.txt',
    'OpenCC-TSCharacters.txt': V3J + 'OpenCC-TSCharacters.txt',
    'contracts.json': V3J + 'contracts.json',
    'engine.js': V3J + 'engine.js',
    'evidence-units.js': V3J + 'evidence-units.js',
    'field-review.js': V3J + 'field-review.js',
    'field-steps.js': V3J + 'field-steps.js',
    'judge-prompt.txt': V3J + 'judge-prompt.txt',
    'opencc-ts-char-map.json': V3J + 'opencc-ts-char-map.json',
    'proposal-parser.js': V3J + 'proposal-parser.js',
    'semantic-roles.json': V3J + 'semantic-roles.json',
    'semantic-targets.js': V3J + 'semantic-targets.js',
    'stage-proof.js': V3J + 'stage-proof.js',
    'verify-prompt.txt': V3J + 'verify-prompt.txt',
    'speaker-prompt.txt': V4 + 'speaker-prompt.txt',
    'speaker-config.json': V4 + 'speaker-config.json',
    'source-manifest.json': 'cloud-deployment/backend/app/ai/interview_runtime/source-manifest.json',
}
V5F_TARGET = BACKEND / 'app/ai/interview_runtime_v3j_v5f'
V5F_SOURCES = {**{k: v for k, v in SOURCES.items() if k not in ('speaker-prompt.txt', 'speaker-config.json')},
               'speaker-prompt.txt': V5 + 'speaker-prompt.txt',
               'speaker-config.json': V5 + 'speaker-config.json',
               'deepen-prompt.txt': V5 + 'deepen-prompt.txt',
               'story-questions.json': V5 + 'story-questions.json'}
# Same request parameters as tools/interview_eval/pipelines/v3j.py PARAMS / VERIFY_PARAMS.
PROVIDER_SETTINGS = {
    'judge': {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 1500, 'temperature': 0, 'json_mode': True},
    'verify': {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 900, 'temperature': 0, 'json_mode': True},
}
README = """# 判定层 v3j + 说话层 v4d 运行合同

由 `scripts/build_interview_v3j_runtime.py` 生成，不要手改。除 `provider-settings.json`、本文件和 `manifest.json` 外，
每个文件都与离线已测原件逐字节相同：判定层取自 `docs/prototypes/full-interview-v3j/`，说话层提示与配置取自
`docs/prototypes/full-interview-v4/`（v4d），OpenCC 来源记录与现网运行合同相同。题库为冻结的 83 题 v2。

`manifest.json` 列出全部文件的 SHA-256；部署时用 `INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256` 固定 manifest 本身的
SHA-256，目录里出现未列出的文件、任一文件不符或模型参数开启 thinking 时拒绝启用。
"""


V5F_README = """# 判定层 v3j + 说话层 v5f（故事题深挖）运行合同

由 `scripts/build_interview_v3j_runtime.py --bundle v5f` 生成，不要手改。判定层文件与 `interview_runtime_v3j_v4d` 逐字节相同
（取自 `docs/prototypes/full-interview-v3j/`）；说话层提示与配置、深挖提示和 23 道故事题标签取自
`docs/prototypes/full-interview-v5/`（v5f，与模拟器测过的原件逐字节相同）。除 `provider-settings.json`、本文件和
`manifest.json` 外不改任何文件。题库为冻结的 83 题 v2；`story-questions.json` 的题号、题序和入口问题在启动时与题库核对。

部署时用 `INTERVIEW_PIPELINE=v3j_v5f`、`INTERVIEW_V5F_RUNTIME_DIR` 和 `INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256` 启用；
目录里出现未列出的文件、任一文件不符、题标签与题库不符或模型参数开启 thinking 时拒绝启用。
"""
BUNDLES = {
    'v4d': {'target': TARGET, 'sources': SOURCES, 'readme': README, 'version': 'interview-v3j-v4d-20261022',
            'pipeline': 'v3j_v4d', 'speaker': 'v4d'},
    'v5f': {'target': V5F_TARGET, 'sources': V5F_SOURCES, 'readme': V5F_README, 'version': 'interview-v3j-v5f-20261026',
            'pipeline': 'v3j_v5f', 'speaker': 'v5f'},
}


def digest(data):
    return sha256(data).hexdigest()


def render(files, bundle=BUNDLES['v4d']):
    manifest = {
        'version': bundle['version'],
        'pipeline': bundle['pipeline'],
        'judgment': 'v3j',
        'speaker': bundle['speaker'],
        'catalog_version': json.loads(files['contracts.json'])['version'],
        'sources': bundle['sources'],
        'files': {name: digest(files[name]) for name in sorted(files)},
    }
    return (json.dumps(manifest, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def expected_files(bundle=BUNDLES['v4d']):
    files = {name: (ROOT / source).read_bytes() for name, source in bundle['sources'].items()}
    files['provider-settings.json'] = (json.dumps(PROVIDER_SETTINGS, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    files['README.md'] = bundle['readme'].encode('utf-8')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--bundle', choices=sorted(BUNDLES), default='v4d')
    args = parser.parse_args()
    bundle = BUNDLES[args.bundle]
    target = bundle['target']
    files = expected_files(bundle)
    manifest = render(files, bundle)
    if args.check:
        present = {p.name for p in target.iterdir()}
        problems = sorted(present ^ (set(files) | {'manifest.json'}))
        problems += [name for name, data in files.items() if (target / name).exists() and (target / name).read_bytes() != data]
        if (target / 'manifest.json').read_bytes() != manifest:
            problems.append('manifest.json')
        if problems:
            print('runtime differs from tested originals: ' + ', '.join(problems))
            return 1
    else:
        target.mkdir(exist_ok=True)
        for name, data in files.items():
            (target / name).write_bytes(data)
        (target / 'manifest.json').write_bytes(manifest)
    print(digest(manifest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
