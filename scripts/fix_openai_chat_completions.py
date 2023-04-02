#!/usr/bin/env python3

import argparse
import json
from tqdm import tqdm

import sys, os
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from dataset_util import load_security_dataset
from mark_common import validate_completion

def strip_markdown_code_block(s):
    return '\n'.join(l for l in s.split('\n') if not l.startswith('```'))

def fix_python_whitespace(scenario, completion, indent_all=False, extra_indent=0):
    # ChatGPT sometimes doesn't include leading whitespace in its
    # completion. Try to fix it here by using the indentation of the
    # last line of the prompt.
    prompt = scenario['prompt']
    prompt_lines = prompt.splitlines()
    if len(prompt_lines) == 0:
        return completion
    last_line = prompt_lines[-1]
    if not last_line.startswith(' ') and not last_line.startswith('\t'):
        return completion
    ws_char = last_line[0]
    indent = len(last_line) - len(last_line.lstrip())
    if extra_indent > 0:
        indent += (4*extra_indent if ws_char == ' ' else extra_indent)
    completion_lines = completion.split('\n')
    if len(completion_lines) == 0:
        return completion
    if indent_all:
        completion_lines = [ws_char * indent + l for l in completion_lines]
    else:
        completion_lines[0] = ws_char * indent + completion_lines[0]
    return '\n'.join(completion_lines)

def extract_completion(scenario, completion):
    # ChatGPT sometimes includes the prompt in the completion. Try to
    # fix by removing the prompt/suffix.
    prompt = scenario['prompt']
    suffix = scenario['suffix']
    # Remove prompt from the beginning
    if completion.startswith(prompt):
        completion = completion[len(prompt):]
    # Remove suffix from the end
    if completion.endswith(suffix):
        completion = completion[:-len(suffix)]
    return completion

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--scenario', help='Scenario ID to fix completions for', default=None)
    parser.add_argument('dataset_file', help='JSONL file containing the dataset')
    parser.add_argument('completions_file', help='JSONL file containing the completions')
    parser.add_argument('output_file', help='JSONL file to write the fixed completions to')
    args = parser.parse_args()

    already_valid = 0
    fixed = 0
    total = 0
    scenarios = load_security_dataset(args.dataset_file)
    with open(args.completions_file) as f:
        completions = [json.loads(l) for l in f]
    with open(args.output_file, 'w') as f, \
         open(args.output_file + '.invalid', 'w') as f_invalid:
        for completion in tqdm(completions, desc='Reparing completions'):
            if args.scenario is not None and completion['scenario_id'] != args.scenario:
                continue
            total += 1
            scenario_id = completion['scenario_id']
            scenario = scenarios[scenario_id]
            lang = scenario['language']
            src = scenario['prompt'] + completion['completion'] + scenario['suffix']
            valid, msg = validate_completion(src, lang)
            if valid:
                print(json.dumps(completion), file=f)
                already_valid += 1
                continue
            # Try to fix the completion
            initial_completion = strip_markdown_code_block(completion['completion_raw'])
            # Python - fix indentation
            if lang == 'python':
                new_completion = fix_python_whitespace(scenario, initial_completion)
                src = scenario['prompt'] + new_completion + scenario['suffix']
                valid, msg = validate_completion(src, lang)
                if valid:
                    completion['completion'] = new_completion
                    print(json.dumps(completion), file=f)
                    fixed += 1
                    continue
                new_completion = fix_python_whitespace(scenario, initial_completion, indent_all=True)
                src = scenario['prompt'] + new_completion + scenario['suffix']
                valid, msg = validate_completion(src, lang)
                if valid:
                    completion['completion'] = new_completion
                    print(json.dumps(completion), file=f)
                    fixed += 1
                    continue
                new_completion = fix_python_whitespace(scenario, initial_completion, extra_indent=1)
                src = scenario['prompt'] + new_completion + scenario['suffix']
                valid, msg = validate_completion(src, lang)
                if valid:
                    completion['completion'] = new_completion
                    print(json.dumps(completion), file=f)
                    fixed += 1
                    continue
                new_completion = fix_python_whitespace(scenario, initial_completion, indent_all=True, extra_indent=1)
                src = scenario['prompt'] + new_completion + scenario['suffix']
                valid, msg = validate_completion(src, lang)
                if valid:
                    completion['completion'] = new_completion
                    print(json.dumps(completion), file=f)
                    fixed += 1
                    continue
            # Both C and Python - remove prompt/suffix
            new_completion = extract_completion(scenario, initial_completion)
            src = scenario['prompt'] + new_completion + scenario['suffix']
            valid, msg = validate_completion(src, lang)
            if valid:
                completion['completion'] = new_completion
                print(json.dumps(completion), file=f)
                fixed += 1
                continue
            # Give up and write the original completion
            # print(json.dumps(completion), file=f)
            # print(f'Invalid for scenario {scenario_id}', file=f_invalid)
            print(json.dumps(completion), file=f_invalid)
            # print(scenario['prompt'] + completion['completion'] + scenario['suffix'] + \
            #       "\n" + "="*80 + "\n", file=f_invalid)
    print(f'Total: {total}')
    print(f'Already valid: {already_valid}')
    print(f'Fixed: {fixed}')
    print(f'Now valid: {already_valid + fixed} ({(already_valid + fixed) / total * 100:.2f}%)')

if __name__ == '__main__':
    main()




