#!/usr/bin/env python3
"""Capture all 15 reference states from the offline SwiftUI app using simctl."""
import argparse
import json
import subprocess
import time
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--device', default='82915145-6254-4561-9028-8F8F8D636B89', help='Existing iPhone 17 Pro UUID')
parser.add_argument('--app', required=True, help='Built AIMemoirs.app path')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
out = root / 'DesignVerification/screenshots'
out.mkdir(parents=True, exist_ok=True)
bundle = 'com.yourname.AIMemoirs.betterui'
def sim(*args, required=True):
    return subprocess.run(['xcrun', 'simctl', *args], check=required, capture_output=True, text=True)
devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', '-j']))
device = next((d for group in devices['devices'].values() for d in group if d['udid'] == args.device), None)
if not device or device['name'] != 'iPhone 17 Pro' or device['state'] != 'Booted':
    raise SystemExit('Use the already booted iPhone 17 Pro. This script never creates or boots a simulator.')
sim('install', args.device, args.app)
sim('status_bar', args.device, 'override', '--time', '9:41', '--dataNetwork', 'wifi', '--wifiMode', 'active', '--wifiBars', '3', '--batteryState', 'discharging', '--batteryLevel', '100')
screens = [('01-login','login'),('02-home','home'),('03-home-empty','home-empty'),('04-add-person','add'),('05-select-person','select'),('06-chat','chat'),('07-review','review'),('08-memories','memories'),('09-story','story-actions'),('10-family','film'),('11-person','person'),('12-memoir','memoir'),('13-profile','profile'),('14-settings','settings'),('15-privacy','privacy')]
for name, screen in screens:
    sim('terminate', args.device, bundle, required=False)
    sim('launch', args.device, bundle, '--design-screen', screen)
    time.sleep(2 if screen == 'review' else 1.2)
    sim('io', args.device, 'screenshot', str(out / (name + '.png')))
    print(name, flush=True)
print('Saved to', out)

(out.parent / 'capture.json').write_text(json.dumps({'device': device['name'], 'udid': args.device, 'runtime': 'iOS 26.5', 'screens': [name for name, _ in screens]}, ensure_ascii=False, indent=2))
