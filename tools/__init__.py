import sys
if sys.flags.optimize:
    raise RuntimeError('Evidence checks require assertions; do not use -O')
