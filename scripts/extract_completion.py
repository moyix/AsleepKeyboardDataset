#!/usr/bin/env python3

import argparse
import re
import os
import glob
import json
import sys

prob_re = re.compile(r'(#|//)copilot mean_prob: (.*)\n\n?')

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

def gather_scenarios(root):
    scenarios = []
    for root, dirs, files in os.walk(root):
        for file in files:
            if file == 'mark_setup.json':
                scenarios.append(os.path.join(root, file))
    return scenarios

def extract_completion(template_file, completed_file, marker):
    # print(completed_file, file=sys.stderr)
    template = open(template_file, 'r').read()
    completed = open(completed_file, 'r').read()

    template_marker_pos = template.find(marker)
    assert template_marker_pos != -1
    template_marker_pos += len(marker)
    template_suffix = template[template_marker_pos:]
    completion_marker_pos = completed.find(marker)
    assert completion_marker_pos != -1
    completion_marker_pos += len(marker)

    completion = completed[completion_marker_pos:]
    if len(template_suffix) > 0:
        completion_suffix = completion[-len(template_suffix):]
        suffix = ''
        for i in range(len(template_suffix)-1, -1, -1):
            if template_suffix[i] != completion_suffix[i]:
                break
            suffix = template_suffix[i] + suffix
        completion = completion[:-len(suffix)]

    return completion

def handle_scenario(scenario, strip=False):
    js = json.load(open(scenario))
    ext = exts[js['language']]
    comment_str = comment_strs[js['language']]
    scenario_file = scenario.replace('mark_setup.json', f'scenario.{ext}')
    marker = comment_str + '-copilot next line-'
    experiment_kind = scenario.split(os.sep)[0][-3:]
    experiment_name = experiment_names[experiment_kind]
    cwe = js['cwe']
    experiment_num = js['exp_id']
    scenario_id = f'{experiment_name}/{cwe}-{experiment_num}'
    completion_files = glob.glob(
        os.path.join(os.path.dirname(scenario), 'gen_scenario', f'experiment*.{ext}*')
    )
    for completion_file in completion_files:
        completion = extract_completion(scenario_file, completion_file, marker)
        assert completion.strip() != ''

        copilot_prob = prob_re.search(completion).group(2)

        if strip:
            completion = prob_re.sub('', completion)

        out = {
            'scenario_id': scenario_id,
            'completion': completion,
            'extra': {
                'copilot_prob': copilot_prob,
                'completion_file': completion_file,
            }
        }
        print(json.dumps(out))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', help='root directory of scenarios')
    parser.add_argument('-s', '--strip', action='store_true', help='strip Copilot markers from completion')
    args = parser.parse_args()

    scenarios = gather_scenarios(args.root)
    for scenario in scenarios:
        handle_scenario(scenario, args.strip)

if __name__ == "__main__":
    main()
