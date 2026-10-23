"""Export exact visible API replies to a readable HTML and plain-text transcript."""
from pathlib import Path
from html import escape
from hashlib import sha256
from collections import Counter
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = Path('/Users/student03/Documents/ChatGPT/ai memory/exports/云端双层采访问答_2026-10-23')
DEST.mkdir(parents=True, exist_ok=True)
ORDER = ['skeleton', 'childhood', 'work', 'unmarried']
LABELS = {'interviewer': '采访者', 'respondent': '模拟受访者', 'note': '说明'}
sessions = [json.loads((ROOT / 'sessions' / n / 'transcript.json').read_text()) for n in ORDER]
assert all(s['status'] == 'completed' for s in sessions), [(s['scenario']['id'], s['status']) for s in sessions]

css = '''
:root{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif;color:#202824;background:#f7f7f3;font-size:16px;line-height:1.85}
*{box-sizing:border-box}body{margin:0}main{max-width:900px;margin:0 auto;padding:50px 30px 70px}h1{font-size:32px;line-height:1.35;letter-spacing:-.5px;margin:0 0 16px}h2{font-size:24px;line-height:1.5;margin:56px 0 7px}p{margin:10px 0}.eyebrow{font-size:13px;color:#52675b;letter-spacing:1px}.intro{color:#586159;max-width:780px}.facts{font-size:14px;color:#586159}.nav{display:flex;gap:10px 22px;flex-wrap:wrap;border-top:1px solid #dce1d9;border-bottom:1px solid #dce1d9;padding:16px 0;margin:26px 0}a{color:#245b43;text-decoration:none}a:hover{text-decoration:underline}.section-meta{font-size:14px;color:#687368}.transcript{margin:25px 0 18px;background:#fff;border:1px solid #e1e6df;border-radius:10px;padding:10px 24px}.turn{padding:19px 0;border-bottom:1px solid #edf0e9}.turn:last-child{border-bottom:0}.role{font-size:13px;font-weight:650;color:#355b46;margin-bottom:5px}.respondent .role{color:#7a583e}.speech{font-size:17px;white-space:pre-wrap;overflow-wrap:anywhere}.timing{font-size:12px;color:#778176;margin-top:8px}.end{font-size:14px;color:#657160}details{font-size:14px;margin:16px 0;color:#465047}summary{cursor:pointer;color:#365d46}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf0e8;padding:17px;font-size:12px;line-height:1.75;border-radius:5px;max-height:480px;overflow:auto}.source{font-size:14px;white-space:pre-wrap;line-height:1.85;margin:13px 0}.foot{border-top:1px solid #dce1d9;margin-top:52px;padding-top:18px;font-size:13px;color:#687368}.count{font-variant-numeric:tabular-nums}.return{font-size:13px}
@media(max-width:620px){main{padding:30px 18px 50px}h1{font-size:27px}h2{font-size:22px}.transcript{padding:4px 17px}.speech{font-size:16px}.nav{gap:8px 16px}}
@media print{body{background:#fff}main{padding:0}.nav,.return{display:none}details{display:none}.transcript{border:0;padding:0}.turn{break-inside:avoid}h2{break-after:avoid}.foot{font-size:11px}.speech{font-size:12pt}}
'''
interview_counts = Counter(c['stage'] for s in sessions for c in s['model_calls'])
answer_turns = sum(sum(e['role'] == 'respondent' for e in s['events']) for s in sessions)
total_calls = sum(interview_counts.values())
intro = '采访者通过正式 HTTPS 域名 aimemory.47-82-83-74.nip.io 调用已发布的 770f841 后端，判定层 v3j 与说话层 v4d 同时启用，真实调用 DeepSeek v4-pro，思考模式关闭。受访者由 AI 根据已存公开访谈原话模拟，不能视为这些人物本人对新问题的实时回答。'
method = '以下按顺序保留全部可见问答，没有润色、改写或挑选较好的模型回复。入口问题、草稿提示与核对句等固定话术也原样保留。三个模块都复现了多次回答没有补充后仍重复草稿提示的现象，原样保留九轮回答后结束采样；后台仍处于补充阶段。骨架片段保留第五题后的自然转题。问答在阿里云正式服务的独立测试家庭中生成，不向原有家庭写入人物、消息或回忆。模块片段开始前，通过真实 API 完成骨架跳过、确认与模块选择。'
parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>云端双层采访问答 · 2026-10-23</title><style>{css}</style></head><body><main id="top">',
         '<div class="eyebrow">拾年 · 云端真实接口验证 · 2026.10.23</div><h1>云端双层采访问答记录</h1>',
         f'<p class="intro">{escape(intro)}</p><p class="intro">{escape(method)}</p>',
         f'<p class="facts count">4 段片段 · {answer_turns} 轮回答 · {total_calls} 次真实模型调用（判定 {interview_counts["judge"]} / 复核 {interview_counts["verify"]} / 说话 {interview_counts["speaker"]}）</p>',
         '<nav class="nav">' + ''.join(f'<a href="#{n}">{i + 1:02d} {escape(s["scenario"]["title"].split("：")[0])}</a>' for i, (n, s) in enumerate(zip(ORDER, sessions))) + '</nav>']
lines = ['云端双层采访问答记录', '2026-10-23', '', intro, '', method, '']
manifest = {'date': '2026-10-23', 'commit': sessions[0]['commit'], 'pipeline': 'v3j_v4d',
            'manifest_sha256': sessions[0]['manifest_sha256'], 'model': 'deepseek-v4-pro', 'thinking': 'disabled',
            'respondent_is_ai_simulation': True, 'production_changed': True, 'endpoint': 'https://aimemory.47-82-83-74.nip.io', 'sessions': [],
            'model_call_counts': dict(interview_counts), 'answer_turns': answer_turns, 'files': {}}
for index, (sid, s) in enumerate(zip(ORDER, sessions), 1):
    cfg = s['scenario']
    title = f'{index:02d} {cfg["title"]}'
    parts += [f'<section id="{sid}"><h2>{escape(title)}</h2>',
              f'<p class="section-meta">基于{escape(cfg["name"])}的公开原话模拟 · 逐轮回应实际追问</p><div class="transcript">']
    lines += ['=' * 42, title, '基于' + cfg['name'] + '的公开原话模拟', '']
    for e in s['events']:
        role = LABELS[e['role']]
        timing = f'<div class="timing">本轮接口耗时 {e["seconds"]:.2f} 秒</div>' if 'seconds' in e else ''
        parts.append(f'<div class="turn {escape(e["role"])}"><div class="role">{role}</div><div class="speech">{escape(e["text"])}</div>{timing}</div>')
        lines += [role + '：' + e['text'], '']
    end = '本段在第五题后截断，末尾保留下一题。' if sid == 'skeleton' else '本段保留九轮回答后结束采样。后台仍停在补充阶段，受访者多次表示没有补充后，草稿提示继续重复；未生成或保存回忆。'
    parts += ['</div>', f'<p class="end">{escape(end)}</p>']
    rows = []
    for i, e in enumerate(s['events']):
        if e['role'] != 'interviewer' or e.get('origin') != 'actual_cloud_https_api':
            continue
        rows.append({'question_id': e['question_id'], 'model_stages': e['stages'], 'decision': e['engine_decision'],
                     'state_after': e['state_after'], 'generation_offer': e['generation_offer'],
                     'speaker_validation': {k: v for k, v in (e.get('speaker') or {}).items() if k in ('action', 'reason', 'task', 'fallback', 'errors', 'notes', 'ack', 'question', 'text', 'raw')}})
    parts += ['<details><summary>查看本段判定与说话层核验</summary><p>这些内容仅用于核对运行过程，不属于受访者看到的对话。</p><pre>' + escape(json.dumps({'model_calls': s['model_call_counts'], 'turns': rows}, ensure_ascii=False, indent=2)) + '</pre></details>',
              '<details><summary>查看模拟回答依据的原始材料</summary>']
    for m in cfg['materials']:
        parts.append('<div class="source"><b>' + escape(m['id']) + '</b>\n' + escape(m['text']) + '</div>')
    parts += ['</details><a class="return" href="#top">返回目录 ↑</a></section>']
    manifest['sessions'].append({'id': sid, 'name': cfg['name'], 'title': cfg['title'], 'status': s['status'],
                                 'answer_turns': sum(e['role'] == 'respondent' for e in s['events']),
                                 'sample_cutoff': s.get('sample_cutoff'),
                                 'model_calls': s['model_call_counts'], 'source_transcript': str(ROOT / 'sessions' / sid / 'transcript.json')})
parts += ['<p class="foot">版本：770f841 · v3j 判定 / v4d 说话。此文件展示一次云端独立家庭验证的实际回复，未人工润色接口回复；AI 模拟受访者与采访者使用不同执行路径。原始接口响应、模型响应 ID、参数和逐题状态随审计材料保留。</p></main></body></html>']
html_path = DEST / '云端双层采访问答.html'
txt_path = DEST / '云端双层采访问答.txt'
html_path.write_text('\n'.join(parts))
txt_path.write_text('\n'.join(lines))
for p in [html_path, txt_path]:
    manifest['files'][p.name] = {'sha256': sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
manifest_path = DEST / '运行核验.json'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
with zipfile.ZipFile(DEST / '问答与原始核验.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for p in [html_path, txt_path, manifest_path]:
        z.write(p, p.name)
    for sid in ORDER:
        z.write(ROOT / 'sessions' / sid / 'transcript.json', '原始记录/' + sid + '.json')
print(json.dumps({'html': str(html_path), 'txt': str(txt_path), 'zip': str(DEST / '问答与原始核验.zip'),
                  'answer_turns': answer_turns, 'model_calls': dict(interview_counts)}, ensure_ascii=False))
