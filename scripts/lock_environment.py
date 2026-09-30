"""Record only the installed dependency closure of this project's requirements."""
from importlib.metadata import distribution
from pathlib import Path
import hashlib
import json
import platform
import yaml
from packaging.requirements import Requirement

root=Path(__file__).resolve().parents[1]
pending=[Requirement(s).name for s in (root/'requirements.txt').read_text().splitlines() if s and not s.startswith('#')]
resolved={}
while pending:
    name=pending.pop()
    dist=distribution(name)
    canonical=dist.metadata['Name']
    if canonical in resolved:
        continue
    resolved[canonical]=dist.version
    for s in dist.requires or []:
        req=Requirement(s)
        if req.marker is None or req.marker.evaluate({'extra':''}):
            pending.append(req.name)
(root/'requirements.lock.txt').write_text(f'# {platform.system()} / Python {platform.python_version()}\n--extra-index-url https://download.pytorch.org/whl/cpu\n'+'\n'.join(f'{k}=={v}' for k,v in sorted(resolved.items(),key=lambda kv:kv[0].lower()))+'\n',encoding='utf8')

def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            hasher.update(block)
    return hasher.hexdigest()
assets=[]
for model in (root/'data/cache/models').iterdir():
    commits=set()
    for p in (model/'.cache/huggingface/download').rglob('*.metadata'):
        lines=p.read_text().splitlines()
        if lines:
            commits.add(lines[0])
    files=[]
    for p in sorted(model.rglob('*')):
        if p.is_file() and '.cache' not in p.parts:
            files.append(dict(file=str(p.relative_to(model)),size=p.stat().st_size,sha256=digest(p)))
    assets.append(dict(model=model.name,revisions=sorted(commits),files=files))
cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf8'))
for p in (root/cfg['ocr']['tessdata']).glob('*.traineddata'):
    assets.append(dict(asset=p.name,size=p.stat().st_size,sha256=digest(p)))
(root/'data/output/assets-manifest.json').write_text(json.dumps(assets,indent=2),encoding='utf8')
print(f'Locked {len(resolved)} packages; recorded {len(assets)} asset groups.')
