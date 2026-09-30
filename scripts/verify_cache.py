"""Run the CLI again and assert stable extraction/matching with actual cache hits."""
from pathlib import Path
import json
import os
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
path=root/'data/output/result.json'
before=json.loads(path.read_text(encoding='utf8'))
env=dict(os.environ,HF_HUB_OFFLINE='1',PYTHONUTF8='1')
with (root/'data/output/cache-run.log').open('w',encoding='utf8') as log:
    subprocess.run([sys.executable,'main.py','--config','config.yaml'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
after=json.loads(path.read_text(encoding='utf8'))
checks={key:before[key]==after[key] for key in ['summary_tables','notes','relationships']}
checks['method_rankings']=before['method_comparison']['items']==after['method_comparison']['items']
checks['embedding_cache_hit']=after['processing']['ml'].get('embedding_cache_hit',False)
checks['reranker_cache_hit']=after['processing']['ml'].get('reranker_cache_hit',False)
(root/'data/output/cache_verification.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
print(checks)
assert all(checks.values()),'Cache verification failed'
