"""Build the whole database in order and stop on the first failure.

    python -m etl.build

  1 etl.run         validate inputs, extract every cell, match columns across years
  2 etl.gold        unit decisions, facts, authority dimensions
  3 etl.benchmarks  peer-group statistics and Eshkol comparisons
  4 etl.audit       independent checks against the source files (stops on critical failure)
  5 etl.release     the published database in data/release (stops if docs/keys disagree)
"""

import sys
import time


def main():
    from . import audit, benchmarks, gold, release, run
    steps = [('run', run.main), ('gold', gold.main), ('benchmarks', benchmarks.main),
             ('audit', audit.main), ('release', release.main)]
    for name, fn in steps:
        t = time.time()
        print(f'\n=== {name} ===', flush=True)
        rc = fn()
        if name == 'audit' and rc:
            print('STOP: the audit found critical failures (data/qa/audit.json); nothing was released.')
            return 1
        print(f'=== {name} done in {time.time() - t:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
