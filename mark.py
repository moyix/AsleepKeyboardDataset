import os
import subprocess
import tempfile
import json
import argparse
from collections import Counter
from dataset_util import load_security_dataset
from mark_common import summarize_results, validate_completion
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

def run_codeql_python(source, query, codeql_bin):
    with tempfile.TemporaryDirectory() as gen_dir, \
         tempfile.TemporaryDirectory() as db_dir, \
         tempfile.NamedTemporaryFile() as results_file:

        # Generate the source file
        fname = os.path.join(gen_dir, 'scenario.py')
        with open(fname,'w') as f:
            f.write(source)

        # Generate the database
        cmd = [codeql_bin, 'database', 'create', db_dir, '--language=python',
               '--overwrite', f'--source-root={gen_dir}']
        subprocess.run(cmd, capture_output=True, check=True)

        # Run the query
        cmd = [codeql_bin, 'database', 'analyze', db_dir, query,
               '--format=sarifv2.1.0', f'--output={results_file.name}']
        subprocess.run(cmd, capture_output=True, check=True)

        # Parse the results
        results_file.seek(0)
        results = json.load(results_file)
        return results

MAKEFILE = '''# Makefile for CodeQL test
SRCS=$(wildcard *.c)

OBJS=$(SRCS:.c=.o)

all: $(OBJS)

%.o: %.c
\tgcc -g -O -c $< -o $@
'''

def run_codeql_c(source, query, codeql_bin):
    with tempfile.TemporaryDirectory() as gen_dir, \
         tempfile.TemporaryDirectory() as db_dir, \
         tempfile.NamedTemporaryFile() as results_file:

        # Generate the source file
        fname = os.path.join(gen_dir, 'scenario.c')
        with open(fname,'w') as f:
            f.write(source)

        # Write the Makefile
        with open(os.path.join(gen_dir, 'Makefile'), 'w') as f:
            f.write(MAKEFILE)

        # Generate the database
        cmd = [codeql_bin, 'database', 'create', db_dir, '--language=cpp',
               '--command=make -B',
               '--overwrite', f'--source-root={gen_dir}']
        subprocess.run(cmd, capture_output=True, check=True)

        # Run the query
        cmd = [codeql_bin, 'database', 'analyze', db_dir, query,
               '--format=sarifv2.1.0', f'--output={results_file.name}']
        subprocess.run(cmd, capture_output=True, check=True)

        # Parse the results
        results_file.seek(0)
        results = json.load(results_file)
        return results

def run_codeql(source, lang, query, paths):
    codeql_bin = os.path.join(paths['CODEQL_HOME'], 'codeql', 'codeql')
    if lang == 'python':
        return run_codeql_python(source, query, codeql_bin)
    elif lang == 'c':
        return run_codeql_c(source, query, codeql_bin)
    else:
        raise Exception('Unknown language')

def check_completion(dataset, completion, paths, completion_id_num, validate_only=False):
    result = {}
    scenario_id = completion['scenario_id']
    result['scenario_id'] = scenario_id
    completion_id = f'{scenario_id}-{completion_id_num}'
    result['completion_id'] = completion_id

    result['extra'] = completion.get('extra', None)
    result['error'] = None

    scenario = dataset[scenario_id]
    source = scenario['prompt'] + completion['completion'] + scenario['suffix']
    lang = scenario['language']
    result['source'] = source
    result['language'] = lang
    result['scenario_detail'] = scenario['detail']

    # Check that the completion is valid
    valid, error = validate_completion(source, lang)
    if not valid:
        result['status'] = 'invalid'
        result['error'] = error
        return result
    elif validate_only:
        result['status'] = 'valid'
        return result

    # Run CodeQL on the completion
    if scenario['check_ql'] is not None:
        try:
            results = run_codeql(source, lang, scenario['check_ql'], paths)
        except subprocess.CalledProcessError as e:
            result['status'] = 'codeql_error'
            result['error'] = {
                'stdout': e.stdout.decode(),
                'stderr': e.stderr.decode()
            }
            return result
        result['results'] = results
        secure = len(results['runs'][0]['results']) == 0
        result['status'] = 'secure' if secure else 'insecure'
    else:
        result['status'] = 'skipped'
    return result

def main():
    CODEQL_HOME = os.environ.get('CODEQL_HOME') or 'codeql-home'
    parser = argparse.ArgumentParser(description='Evaluate security of LLM generated code')
    parser.add_argument('-d', '--dataset', help='Dataset of scenarios to use', required=True)
    parser.add_argument('-o', '--output', help='Output file', default=None, required=False)
    parser.add_argument('-c', '--custom_ql', help='Path to custom CodeQL queries', default='custom_ql', required=False)
    parser.add_argument('-H', '--codeql_home', help='Path to CodeQL home', default=CODEQL_HOME, required=False)
    parser.add_argument('-j', '--jobs', help='Number of parallel jobs', default=4, type=int, required=False)
    parser.add_argument('-v', '--validate_only', help='Only validate completions', action='store_true', required=False)
    parser.add_argument('-q', '--quiet', help='Disable progress bar', action='store_true', required=False)
    parser.add_argument('completions', help='Completions to evaluate')
    args = parser.parse_args()

    if args.output is None:
        args.output = args.completions + '_results.jsonl'
    if not os.path.isdir(args.custom_ql):
        parser.error('Custom QL directory does not exist: ' + args.custom_ql)
    if not os.path.isdir(args.codeql_home):
        parser.error('CodeQL home directory does not exist: ' + args.codeql_home)

    # Resolve paths
    args.custom_ql = os.path.abspath(args.custom_ql)
    args.codeql_home = os.path.abspath(args.codeql_home)

    paths = {'CODEQL_HOME': args.codeql_home, 'CUSTOM_QL': args.custom_ql}
    dataset = load_security_dataset(args.dataset, paths)

    with open(args.completions, 'r') as completions_file:
        completions = [json.loads(line) for line in completions_file]

    completion_ids = Counter()

    futures = []
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        for completion in completions:
            scenario_id = completion['scenario_id']
            future = executor.submit(
                check_completion, dataset, completion, paths, completion_ids[scenario_id], args.validate_only
            )
            futures.append(future)
            completion_ids[scenario_id] += 1
        results = []
        with open(args.output, 'w') as output_file:
            for future in tqdm(as_completed(futures), total=len(futures), disable=args.quiet):
                result = future.result()
                output_file.write(json.dumps(result) + '\n')
                results.append(result)
        summarize_results(results)

if __name__=="__main__":
    main()
