#!/usr/bin/env python3
"""Build or check the v3j judgment + v4d speaking-layer runtime bundle.

  python3 scripts/build_interview_v3j_runtime.py           # (re)write app/ai/interview_runtime_v3j_v4d
  python3 scripts/build_interview_v3j_runtime.py --check   # verify the bundle against the tested originals

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


def digest(data):
    return sha256(data).hexdigest()


def render(files):
    manifest = {
        'version': 'interview-v3j-v4d-20261022',
        'pipeline': 'v3j_v4d',
        'judgment': 'v3j',
        'speaker': 'v4d',
        'catalog_version': json.loads(files['contracts.json'])['version'],
        'sources': SOURCES,
        'files': {name: digest(files[name]) for name in sorted(files)},
    }
    return (json.dumps(manifest, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def expected_files():
    files = {name: (ROOT / source).read_bytes() for name, source in SOURCES.items()}
    files['provider-settings.json'] = (json.dumps(PROVIDER_SETTINGS, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    files['README.md'] = README.encode('utf-8')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files = expected_files()
    manifest = render(files)
    if args.check:
        present = {p.name for p in TARGET.iterdir()}
        problems = sorted(present ^ (set(files) | {'manifest.json'}))
        problems += [name for name, data in files.items() if (TARGET / name).exists() and (TARGET / name).read_bytes() != data]
        if (TARGET / 'manifest.json').read_bytes() != manifest:
            problems.append('manifest.json')
        if problems:
            print('runtime differs from tested originals: ' + ', '.join(problems))
            return 1
    else:
        TARGET.mkdir(exist_ok=True)
        for name, data in files.items():
            (TARGET / name).write_bytes(data)
        (TARGET / 'manifest.json').write_bytes(manifest)
    print(digest(manifest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
