#!/usr/bin/env python3

import sys
import re
import os
import json

# Take a name like:
#   completions_dow_code-cushman-001_completion_t0.1_fixed.jsonl
# and return:
#   {
#       'kind': 'completions', # or 'results'
#       'dataset': 'dow', # or 'dod' or 'dop'
#       'model': 'code-cushman-001',
#       'mode': 'completion', # or 'insertion'
#       'parameters': {
#           'temperature': 0.1,
#       },
#       'fixed': True,
#   }

NAME_REGEX = re.compile(r'(?P<kind>completions|results)_(?P<dataset>dow|dod|dop)_(?P<model>[\w.-]+)_(?P<mode>completion|insertion|chat)((_t(?P<t>[0-9.]+))?(_r(?P<r>[0-9.]+))?(_stars(?P<stars>(\d+|\d+-\d+|\d+\+)))?)*(_(?P<fixed>fixed))?.jsonl')

def parse_name(filename):
    match = NAME_REGEX.match(filename)
    if not match:
        raise ValueError("Invalid filename format")

    groups = match.groupdict()

    params = {}
    known_params = {
        't': ('temperature', float),
        'r': ('repetition_penalty', float),
        'stars': ('stars', str),
    }
    for key, (param_name, param_type) in known_params.items():
        if groups[key] is not None:
            params[param_name] = param_type(groups[key])

    return {
        'kind': groups['kind'],
        'dataset': groups['dataset'],
        'model': groups['model'],
        'mode': groups['mode'],
        'parameters': params,
        'fixed': groups['fixed'] is not None,
    }

def main():
    for name in sys.argv[1:]:
        bn = os.path.basename(name)
        try:
            parsed = parse_name(bn)
            print(json.dumps(parsed))
        except ValueError as e:
            print(f'{name}: {e}', file=sys.stderr)

if __name__ == '__main__':
    main()
