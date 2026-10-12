"""Generate a local test project from current product settings and local targets.

Generated projects default to /tmp; test targets and fixture paths stay outside
the product project. Optional legacy tests are copied, never edited in place.
"""
from pathlib import Path
import copy
import json
import os
import argparse
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="Generate a separate verification project; the App target stays unchanged.")
parser.add_argument('--output', type=Path, default=Path('/tmp/shinian-betterui-checks'))
parser.add_argument('--isolated-api', action='store_true', help='Enable the disposable API at localhost:17655; never production writes')
parser.add_argument('--legacy-tests', type=Path, help="Optional existing AIMemoirsTests source directory")
parser.add_argument('--legacy-preview', type=Path, help="Optional fixture required by the existing tests")
args = parser.parse_args()
OUTPUT = args.output.resolve() / 'AIMemoirs.xcodeproj'
if OUTPUT.parent == ROOT or ROOT in OUTPUT.parent.parents:
    parser.error('Validation output must be outside the product directory')
APP = '7195EDE12E03E93E008FCA27'
TEST_IDS = ['7195EDF62E03E940008FCA27', '7195EE002E03E940008FCA27']


def serialize(value, level=0):
    tab = '\t' * level
    if isinstance(value, dict):
        return '{\n' + ''.join('\t' * (level + 1) + json.dumps(key) + ' = ' +
                               serialize(item, level + 1) + ';\n'
                               for key, item in value.items()) + tab + '}'
    if isinstance(value, list):
        return '(\n' + ''.join('\t' * (level + 1) + serialize(item, level + 1) +
                               ',\n' for item in value) + tab + ')'
    return json.dumps(value, ensure_ascii=False)


def generate():
    source = ROOT / 'AIMemoirs.xcodeproj'
    project = json.loads(subprocess.run(
        ['plutil', '-convert', 'json', '-o', '-', str(source / 'project.pbxproj')],
        capture_output=True, text=True, check=True).stdout)
    extra = json.loads((ROOT / 'scripts/validation-targets.json').read_text())
    objects = project['objects']
    assert not (extra.keys() & objects.keys()), 'Product already contains local test objects'
    objects.update(copy.deepcopy(extra))
    project_object = objects[project['rootObject']]
    project_object['targets'].extend(TEST_IDS)
    for target in TEST_IDS:
        project_object['attributes']['TargetAttributes'][target] = {
            'CreatedOnToolsVersion': '16.1', 'TestTargetID': APP}
    root_group = objects[project_object['mainGroup']]
    products = objects[project_object['productRefGroup']]
    parent = OUTPUT.parent
    for target in TEST_IDS:
        obj = objects[target]
        products['children'].append(obj['productReference'])
        for group in obj['fileSystemSynchronizedGroups']:
            root_group['children'].append(group)
            name = obj['name']
            destination = parent / name
            destination.mkdir(parents=True, exist_ok=True)
            for staged in destination.glob('*.swift'):
                staged.unlink()
            if name == 'AIMemoirsTests' and args.legacy_tests:
                for file in args.legacy_tests.glob('*.swift'):
                    shutil.copy2(file, destination / file.name)
                if args.legacy_preview:
                    (destination / 'JournalPreviewAPI.swift').write_text('@testable import AIMemoirs\n' + args.legacy_preview.read_text())
            for file in (ROOT / 'Tests' / name).glob('*.swift'):
                shutil.copy2(file, destination / file.name)
            objects[group]['path'] = os.path.relpath(destination, parent)
    objects['7195EDE42E03E93E008FCA27']['path'] = os.path.relpath(ROOT / 'AIMemoirs', parent)
    for obj in objects.values():
        if obj['isa'] != 'XCBuildConfiguration':
            continue
        settings = obj['buildSettings']
        if 'DEVELOPMENT_TEAM' in settings:
            settings['DEVELOPMENT_TEAM'] = os.environ.get('SHINIAN_DEVELOPMENT_TEAM', '')
        if 'INFOPLIST_FILE' in settings:
            settings['INFOPLIST_FILE'] = os.path.relpath(ROOT / 'Config/Info.plist', parent)
        if 'DEVELOPMENT_ASSET_PATHS' in settings:
            preview = os.path.relpath(ROOT / 'AIMemoirs/Preview Content', parent)
            settings['DEVELOPMENT_ASSET_PATHS'] = '"' + preview + '"'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'project.pbxproj').write_text('// !$*UTF8*$!\n' + serialize(project) + '\n')
    scheme = ET.parse(source / 'xcshareddata/xcschemes/AIMemoirs.xcscheme')
    testables = scheme.getroot().find('TestAction/Testables')
    assert testables is not None
    testables.clear()
    for target in TEST_IDS:
        name = objects[target]['name']
        item = ET.SubElement(testables, 'TestableReference', skipped='NO', parallelizable='NO')
        ET.SubElement(item, 'BuildableReference', BuildableIdentifier='primary',
                      BlueprintIdentifier=target, BuildableName=name + '.xctest',
                      BlueprintName=name, ReferencedContainer='container:AIMemoirs.xcodeproj')
    ET.indent(scheme, space='  ')
    destination = OUTPUT / 'xcshareddata/xcschemes/AIMemoirs.xcscheme'
    destination.parent.mkdir(parents=True, exist_ok=True)
    scheme.write(destination, encoding='UTF-8', xml_declaration=True)
    if args.isolated_api:
        env = ET.SubElement(scheme.getroot().find('LaunchAction'), 'EnvironmentVariables')
        for key, value in [('AI_MEMORIES_API_URL', 'http://localhost:17655'), ('BETTERUI_ISOLATED_TEST', '1')]:
            ET.SubElement(env, 'EnvironmentVariable', key=key, value=value, isEnabled='YES')
        scheme.write(destination.with_name('AIMemoirs-Isolated.xcscheme'), encoding='UTF-8', xml_declaration=True)
    print(OUTPUT)


if __name__ == '__main__':
    generate()
