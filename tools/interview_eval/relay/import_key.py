#!/usr/bin/env python3
"""Import (or replace) the DeepSeek API key used by ds_relay.py.

Usage:
  py -3 import_key.py                 # paste the key when asked (input hidden)
  py -3 import_key.py path\\to\\key.txt # read the key from a text file

The key is stored only in deepseek_key.txt next to this script, then checked
against https://api.deepseek.com/models.
"""
import getpass
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / 'deepseek_key.txt'


def main():
    if len(sys.argv) > 1:
        key = Path(sys.argv[1]).read_text(encoding='utf-8').strip()
    else:
        key = getpass.getpass('Paste DeepSeek API key (hidden): ').strip()
    if not key.startswith('sk-') or len(key) < 20:
        sys.exit('That does not look like a DeepSeek key (expected sk-...).')
    TARGET.write_text(key + '\n', encoding='utf-8')
    print('Saved to', TARGET)
    req = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            models = json.loads(resp.read().decode('utf-8'))
        print('Key works. Models:', ', '.join(sorted(m['id'] for m in models.get('data', []))))
    except urllib.error.HTTPError as e:
        print('Key saved but the check failed: HTTP', e.code)
    except Exception as e:
        print('Key saved but could not reach api.deepseek.com:', type(e).__name__)


if __name__ == '__main__':
    main()
