import argparse
import json
import platform
import time
import unittest
from pathlib import Path
from .evidence import ROOT,manifest,fingerprint


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
    def ids(s):
        for item in s:
            if isinstance(item,unittest.TestSuite):yield from ids(item)
            else:yield item.id()
    names=list(ids(suite));began=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(suite)
    value={'passed':result.wasSuccessful() and result.testsRun>0 and not result.skipped,
           'tests':result.testsRun,'test_ids':names,'failures':len(result.failures),'errors':len(result.errors),
           'skipped':len(result.skipped),'platform':platform.system(),'python':platform.python_version(),
           'seconds':time.monotonic()-began,'source':manifest(),'source_sha256':fingerprint(manifest())}
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k not in ('source','test_ids')}))
    raise SystemExit(0 if value['passed'] else 1)


if __name__=='__main__':main()
