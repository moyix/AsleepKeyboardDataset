#!/usr/bin/env python3

import tempfile
import subprocess
import sys, os

def validate_c(source):
    # Try to build the program in a temp directory
    with tempfile.TemporaryDirectory() as gen_dir:
        fname = os.path.join(gen_dir, 'scenario.c')
        with open(fname,'w') as f:
            f.write(source)
        try:
            subprocess.run(
                ['gcc', '-g', '-O', '-c', fname, '-o', fname + '.o'],
                capture_output=True,
                check=True,
            )
            return (True, None)
        except subprocess.CalledProcessError as e:
            return (False,
            {
                'stdout': e.stdout.decode(),
                'stderr': e.stderr.decode()
            })

def validate_python(source):
    with tempfile.TemporaryDirectory() as gen_dir:
        fname = os.path.join(gen_dir, 'scenario.py')
        with open(fname,'w') as f:
            f.write(source)
        try:
            subprocess.run(
                ['python', '-m', 'py_compile', fname],
                capture_output=True,
                check=True,
            )
            return (True, None)
        except subprocess.CalledProcessError as e:
            return (False, {
                'stdout': e.stdout.decode(),
                'stderr': e.stderr.decode()
            })

def validate_completion(source, lang):
    if lang == 'c':
        return validate_c(source)
    elif lang == 'python':
        return validate_python(source)
    else:
        raise Exception('Unknown language')

def summarize_results(results, file=sys.stdout):
    # Write the results
    stats = {'secure': 0, 'insecure': 0, 'skipped': 0, 'valid': 0, 'invalid': 0, 'pending': 0, 'codeql_error': 0}
    for result in results:
        stats[result['status']] += 1
    if stats['valid'] == 0:
        # Outside of validate-only mode this will be zero, so compute it
        # here based on the other stats.
        stats['valid'] = stats['secure'] + stats['insecure']
    print(f'Secure:       {stats["secure"]:4d}', file=file)
    print(f'Insecure:     {stats["insecure"]:4d}', file=file)
    print(f'Skipped:      {stats["skipped"]:4d}', file=file)
    print(f'Invalid:      {stats["invalid"]:4d}', file=file)
    print(f'CodeQL error: {stats["codeql_error"]:4d}', file=file)
    print(f'Valid:        {stats["valid"]:4d}', file=file)
    print(f'Pending:      {stats["pending"]:4d}', file=file)
    print(f'Total:        {len(results):4d}', file=file)
    # Print a line like "269 insecure, 722 secure, 47 invalid (27.1% valid but insecure)"
    insecure = stats['insecure']
    secure = stats['secure']
    invalid = stats['invalid']
    valid = stats['valid']
    if valid > 0:
        insecure_percent = 100 * insecure / valid
        print(f'{insecure} insecure, {secure} secure, {invalid} invalid ({insecure_percent:.1f}% valid but insecure)', file=file)
    return stats
