#!/usr/bin/env python

import sys
import json
import os

exts = {
    'c': 'c',
    'python': 'py',
    'verilog': 'v',
}
comment_strs = {
    'c': '//',
    'python': '#',
    'verilog': '//',
}
experiment_names = {
    'dow': 'DoW',
    'dop': 'DoP',
    'dod': 'DoD',
}
root = sys.argv[1]

def gather_scenarios(root):
    scenarios = []
    for root, dirs, files in os.walk(root):
        for file in files:
            if file == 'mark_setup.json':
                scenarios.append(os.path.join(root, file))
    return scenarios

def create_scenario_json(mark_setup):
    js = json.load(open(mark_setup))
    ext = exts[js['language']]
    comment_str = comment_strs[js['language']]
    scenario_file = mark_setup.replace('mark_setup.json', f'scenario.{ext}')
    with open(scenario_file, 'r') as f:
        scenario_code = f.read()
    parts = scenario_code.split(comment_str + '-copilot next line-')
    if len(parts) != 2:
        raise Exception('No marker ("-copilot next line-") found in scenario file')
    prompt, suffix = parts
    experiment_kind = mark_setup.split(os.sep)[0][-3:]
    experiment_name = experiment_names[experiment_kind]
    experiment_detail = mark_setup.split(os.sep)[2]
    cwe = js['cwe']
    experiment_num = js['exp_id']
    scenario_id = f'{experiment_name}/{cwe}-{experiment_num}'
    out = {
        'scenario_id': scenario_id,
        'detail': experiment_detail,
        'prompt': prompt,
        'suffix': suffix,
        'language': js['language'],
        'check_ql': js.get('check_ql'),
        'cwe_rank': js.get('cwe_rank'),
        # TODO: ask Hammond what these are for
        'suppress_at_lines': js.get('suppress_at_lines', True),
        'discard_after_close_parenthesis': js.get('discard_after_close_parenthesis', False),
    }
    return out

if __name__ == '__main__':
    scenarios = gather_scenarios(root)
    for scenario in scenarios:
        print(json.dumps(create_scenario_json(scenario)))
