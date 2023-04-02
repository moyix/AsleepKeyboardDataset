#!/usr/bin/env python3

import argparse
import shutil
import json
import sys, os
import tempfile
import subprocess

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from dataset_util import load_security_dataset
from mark_common import validate_completion

def get_editor():
    editor = os.environ.get('VISUAL')
    if editor: return editor
    editor = os.environ.get('EDITOR')
    if editor: return editor
    # Check if "editor" is in PATH
    if shutil.which('editor'): return 'editor'
    return 'vim'

def edit_completion(scenario, completion):
    c = '/' if scenario['language'] == 'c' else '#'
    START_MARKER = f"{c}{c}{c}{c}---- Do not edit above this line; it is only for reference ----{c}{c}{c}{c}\n"
    END_MARKER = f"{c}{c}{c}{c}---- Do not edit below this line; it is only for reference ----{c}{c}{c}{c}\n"
    ext = '.c' if scenario['language'] == 'c' else '.py'
    with tempfile.NamedTemporaryFile(mode='r+', suffix=ext) as f:
        print(f"{c}{c} Editing completion for scenario {scenario['scenario_id']}\n", file=f)
        print(scenario['prompt'], file=f)
        f.write(START_MARKER)
        print(completion, file=f)
        f.write(END_MARKER)
        print(scenario['suffix'], file=f)
        f.flush()
        editor = get_editor()
        # Run editor and wait for it to exit
        subprocess.run([editor, f.name])
        # Read the edited file
        f.seek(0)
        edited = f.read()
        # Remove the prompt and suffix
        edited = edited.split(START_MARKER)[1].split(END_MARKER)[0]
        return edited

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset_file', help='JSONL file containing the dataset')
    parser.add_argument('completions_file', help='JSONL file containing the completions')
    parser.add_argument('output_file', help='JSONL file to write the fixed completions to')
    args = parser.parse_args()

    dataset = load_security_dataset(args.dataset_file)
    completions = [json.loads(line) for line in open(args.completions_file)]

    fixed = 0
    total = 0
    with open(args.output_file, 'w') as f:
        for completion in completions:
            scenario = dataset[completion['scenario_id']]
            completion['completion'] = edit_completion(scenario, completion['completion'])
            src = scenario['prompt'] + completion['completion'] + scenario['suffix']
            lang = scenario['language']
            valid, msg = validate_completion(src, lang)
            if valid:
                fixed += 1
            else:
                print(f'Error: {msg}', file=sys.stderr)
            total += 1
            print(json.dumps(completion), file=f)
    print(f'Fixed {fixed}/{total} completions')

if __name__ == '__main__':
    main()
