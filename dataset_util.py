#!/usr/bin/env python

import json
import gzip

def _load_json(f, substs={}):
    dataset = {}
    for line in f:
        js = json.loads(line)
        if js['check_ql']:
            js['check_ql'] = js['check_ql'].format(**substs)
        dataset[js['scenario_id']] = js
    return dataset

def load_security_dataset(path, substs=None):
    if substs is None:
        substs = {'CODEQL_HOME': '',
                  'CUSTOM_QL': ''}
    if path.endswith('.gz'):
        with gzip.open(path, 'rt') as f:
            return _load_json(f, substs)
    else:
        with open(path, 'r') as f:
            return _load_json(f, substs)
