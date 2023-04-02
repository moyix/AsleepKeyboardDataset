import os
import subprocess
import tempfile
import json
import argparse
from dataset_util import load_security_dataset
from mark_common import summarize_results, validate_completion
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from collections import Counter

MAKEFILE = '''# Makefile for CodeQL test
SRCS=$(wildcard *.c)

OBJS=$(SRCS:.c=.o)

all: $(OBJS)

%.o: %.c
\tgcc -g -O -c $< -o $@
'''

def write_results(results, output):
    with open(output, 'w') as f:
        for completion_id, result in results.items():
            print(json.dumps(result), file=f)

def get_sarif_result_filenames(sarif_results):
    filename_to_result = {}
    for result in sarif_results:
        for loc in result['locations']:
            filename_to_result[loc['physicalLocation']['artifactLocation']['uri']] = result
    return filename_to_result

def match_completions_to_query_results(completion_ids, completions_dict, sarif, results):
    fmap = get_sarif_result_filenames(sarif['runs'][0]['results'])
    for completion_id in completion_ids:
        completion_filename = completions_dict[completion_id]['source_file']
        res = fmap.get(completion_filename, None)
        if res is not None:
            results[completion_id]['status'] = 'insecure'
            results[completion_id]['results'] = res
        else:
            results[completion_id]['status'] = 'secure'

def run_codeql_query(codeql_bin, db_dir, query, result_file):
    cmd = [codeql_bin, 'database', 'analyze', db_dir, query,
        '--format=sarifv2.1.0', f'--output={result_file}']
    subprocess.run(cmd, capture_output=True, check=True)

def set_result_error(completion_ids, results, e):
    for completion_id in completion_ids:
        results[completion_id]['status'] = 'codeql_error'
        results[completion_id]['error'] = {
            'stdout': e.stdout.decode(),
            'stderr': e.stderr.decode()
        }

def run_queries(codeql_bin, queries, db_dir, results, completions_dict, query_map, keep=False):
    for query in tqdm(queries):
        with tempfile.NamedTemporaryFile(prefix='codeql_', suffix='.jsonl', delete=not keep) as result_file:
            try:
                run_codeql_query(codeql_bin, db_dir, query, result_file.name)
            except subprocess.CalledProcessError as e:
                set_result_error(query_map[query], results, e)
                continue

            # Parse the SARIF file
            result_file.seek(0)
            sarif = json.load(result_file)
            match_completions_to_query_results(query_map[query], completions_dict, sarif, results)

# Version of check_completions that separates the generation of the
# codeql database from the actual query execution. This means that the
# (expensive) DB creation can be done just once.
def check_completions_batch(dataset, completions, paths, output, verify_only=False):
    c_src_dir = tempfile.TemporaryDirectory()
    py_src_dir = tempfile.TemporaryDirectory()

    completion_ids = Counter()

    results = {}
    completions_dict = {}

    # Generate the source files and check validity
    print('Generating and validating source files...')
    for completion in tqdm(completions):
        scenario_id = completion['scenario_id']
        scenario = dataset[scenario_id]

        # Make a unique completion id
        completion_id = f'{scenario_id}-{completion_ids[scenario_id]}'
        completion_ids[scenario_id] += 1
        completions_dict[completion_id] = completion

        # Build the result
        result = {}
        results[completion_id] = result
        result['scenario_id'] = completion['scenario_id']
        result['completion_id'] = completion_id
        result['extra'] = completion.get('extra', None)
        result['error'] = None
        source = scenario['prompt'] + completion['completion'] + scenario['suffix']
        lang = scenario['language']
        result['source'] = source
        result['language'] = lang
        result['scenario_detail'] = scenario['detail']
        result['status'] = 'pending'

        # Check that the completion is valid
        valid, error = validate_completion(source, lang)
        if not valid:
            result['status'] = 'invalid'
            result['error'] = error
            continue

        # Write the source file
        if lang == 'c':
            src_dir = c_src_dir
            ext = 'c'
        elif lang == 'python':
            src_dir = py_src_dir
            ext = 'py'
        else:
            raise Exception('Unknown language')
        completion_fname = f'{completion_id}.{ext}'.replace('/','_')
        fname = os.path.join(src_dir.name, completion_fname)
        with open(fname,'w') as f:
            f.write(source)
        completion['source_file'] = completion_fname

    # Bail out if we're just verifying
    if verify_only:
        for result in results.values():
            if result['status'] == 'pending':
                result['status'] = 'valid'
        c_src_dir.cleanup()
        py_src_dir.cleanup()
        write_results(results, output)
        return

    # Write the Makefile
    with open(os.path.join(c_src_dir.name, 'Makefile'), 'w') as f:
        f.write(MAKEFILE)

    # Create the CodeQL databases
    codeql_bin = os.path.join(paths['CODEQL_HOME'], 'codeql', 'codeql')
    # For Python
    db_dir_py = tempfile.TemporaryDirectory()
    print(f'Creating CodeQL database for Python in {db_dir_py.name}...')
    cmd = [codeql_bin, 'database', 'create', db_dir_py.name, '--language=python',
            '--overwrite', f'--source-root={py_src_dir.name}']
    subprocess.run(cmd, capture_output=True, check=True)
    # For C
    db_dir_c = tempfile.TemporaryDirectory()
    print(f'Creating CodeQL database for C in {db_dir_c.name}...')
    cmd = [codeql_bin, 'database', 'create', db_dir_c.name, '--language=cpp',
            f'--command=make -B', '--overwrite', f'--source-root={c_src_dir.name}']
    subprocess.run(cmd, capture_output=True, check=True)

    # Collect unique queries
    queries_c = set()
    queries_py = set()
    # Maps from query to completion ids
    query_map = {}
    for completion_id in completions_dict:
        if results[completion_id]['status'] != 'pending':
            continue
        completion = completions_dict[completion_id]
        scenario = dataset[completion['scenario_id']]
        if scenario['check_ql'] is not None:
            query = scenario['check_ql']
            if scenario['language'] == 'c':
                queries_c.add(query)
            elif scenario['language'] == 'python':
                queries_py.add(query)
            else:
                raise Exception('Unknown language')
            if query not in query_map:
                query_map[query] = []
            query_map[query].append(completion_id)
        else:
            results[completion_id]['status'] = 'skipped'

    # Run the queries
    print(f'Running {len(queries_py)} Python queries...')
    run_queries(codeql_bin, queries_py, db_dir_py.name, results, completions_dict, query_map)
    print(f'Running {len(queries_c)} C queries...')
    run_queries(codeql_bin, queries_c, db_dir_c.name, results, completions_dict, query_map)

    # Write the results
    write_results(results, output)
    summarize_results(results)

    # Clean up
    db_dir_c.cleanup()
    db_dir_py.cleanup()
    c_src_dir.cleanup()
    py_src_dir.cleanup()

def main():
    CODEQL_HOME = os.environ.get('CODEQL_HOME') or 'codeql-home'
    parser = argparse.ArgumentParser(description='Evaluate security of LLM generated code')
    parser.add_argument('-d', '--dataset', help='Dataset of scenarios to use', required=True)
    parser.add_argument('-o', '--output', help='Output file', default=None, required=False)
    parser.add_argument('-c', '--custom_ql', help='Path to custom CodeQL queries', default='custom_ql', required=False)
    parser.add_argument('-H', '--codeql_home', help='Path to CodeQL home', default=CODEQL_HOME, required=False)
    parser.add_argument('-j', '--jobs', help='Number of parallel jobs', default=4, type=int, required=False)
    parser.add_argument('-v', '--verify_only', help='Only verify the completions', action='store_true', required=False)
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

    check_completions_batch(dataset, completions, paths, args.output, args.verify_only)

if __name__=="__main__":
    main()
