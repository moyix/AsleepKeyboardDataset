#!/usr/bin/env python3

import argparse
import json
import sys, os
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from mark_common import summarize_results
from dataset_util import load_security_dataset

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset_file', help='JSONL file containing the dataset')
    parser.add_argument('results_file', help='JSONL file containing the completions')
    args = parser.parse_args()

    dataset = load_security_dataset(args.dataset_file)
    results = [json.loads(line) for line in open(args.results_file)]

    for res in results:
        scenario = dataset[res['scenario_id']]
        if not scenario['check_ql']: res['status'] = 'skipped'

    summarize_results(results)

if __name__ == '__main__':
    main()

