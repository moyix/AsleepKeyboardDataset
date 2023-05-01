#!/usr/bin/env python3

import argparse
import json
import sys, os
import tabulate
from parse_name import parse_name
from collections import defaultdict

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from mark_common import summarize_results
from dataset_util import load_security_dataset

def pct(x, y):
    return f'{x}/{y} ({x/y*100:.2f}%)'

def pct_plain(x, y):
    return (x*100)/y

fixups = {
    'Model': {
        'starcoder': 'StarCoder',
        'codegen-16B-multi': 'CodeGen-16B-Multi',
        'incoder-6B': 'InCoder-6B',
    },
    'Scenario': {
        'dow': 'DoW',
        'dop': 'DoP',
        'dod': 'DoD',
    },
    'Format': {
        'completion': 'Completion',
        'insertion': 'Insertion',
        'chat': 'Chat',
    },
    'Language': {
        'c': 'C',
        'python': 'Python',
    }
}
def beautify_names(row):
    for k in row:
        if k in fixups:
            row[k] = fixups[k].get(row[k], row[k])
    return row

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--skip-cols', type=str, nargs=1, action='append', default=[], help='Columns to skip')
    parser.add_argument('-p', '--preserve-cols', type=str, nargs=1, action='append', default=[], help='Columns to preserve even if they are all the same')
    parser.add_argument('--sort-by', type=str, default=None, help='Column to sort by; by default, use the order of the files on the command line')
    parser.add_argument('-t', '--table-format', type=str, default='simple', choices=tabulate.tabulate_formats+['csv'], help='Table format for tabulate, or "csv" to print CSV')
    parser.add_argument('-l', '--by-language', action='store_true', help='Group by language')
    parser.add_argument('results_files', help='JSONL files containing the CodeQL results', nargs='+')
    args = parser.parse_args()
    args.skip_cols = sum(args.skip_cols, [])
    args.preserve_cols = sum(args.preserve_cols, [])
    devnull = open(os.devnull, 'w')
    table = []
    columns = ('Format', 'Model', 'Scenario', 'Stars', 'Language', 'Temperature', 'RepetitionPenalty', 'Valid', 'Insecure')
    for results_file in args.results_files:
        metadata = parse_name(os.path.basename(results_file))
        dataset = load_security_dataset(f'data/scenario_{metadata["dataset"]}.jsonl')
        all_results = [json.loads(line) for line in open(results_file)]
        results_by_lang = defaultdict(list)
        if args.by_language:
            for res in all_results:
                results_by_lang[res['language']].append(res)
        else:
            results_by_lang['All'] = all_results
        results_by_lang = dict(results_by_lang)

        for lang in results_by_lang:
            results = results_by_lang[lang]
            for res in results:
                scenario = dataset[res['scenario_id']]
                if not scenario['check_ql']: res['status'] = 'skipped'

            stats = summarize_results(results, file=devnull)
            total = len(results) - stats['skipped']
            valid = stats['valid']
            insecure = stats['insecure']
            table.append(beautify_names(dict(zip(columns, (
                metadata['mode'],
                metadata['model'],
                metadata['dataset'],
                metadata['parameters'].get('stars', 'N/A'),
                lang,
                metadata['parameters']['temperature'],
                metadata['parameters'].get('repetition_penalty', 'N/A'),
                pct(valid, total),
                pct(insecure, valid),
            )))))

    # Remove skipped columns
    for row in table:
        for col in args.skip_cols:
            del row[col]

    # Remove any columns that are all the same
    for col in columns:
        if col in args.skip_cols or col in args.preserve_cols:
            continue
        if len(set(row[col] for row in table)) == 1:
            for row in table:
                del row[col]

    if args.sort_by:
        table.sort(key=lambda row: row[args.sort_by])
    if args.table_format == 'csv':
        import csv
        writer = csv.DictWriter(sys.stdout, fieldnames=table[0].keys())
        writer.writeheader()
        writer.writerows(table)
    else:
        print(tabulate.tabulate(table, headers="keys", tablefmt=args.table_format, floatfmt=".2f"))

if __name__ == '__main__':
    main()

