"""Export annotated page previews using the exact cached OCR coordinate frame."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from PIL import Image, ImageDraw, ImageFont

root=Path(__file__).resolve().parents[1]
result=json.loads((root/'data/output/result.json').read_text(encoding='utf8'))
cache=Path(result['processing']['cache_root'])
out=root/'data/output/previews'
out.mkdir(exist_ok=True)
tables=result['summary_tables']+[t for n in result['notes'] for t in n['tables']]
for number in sorted(set(t['page'] for t in tables)):
    page=json.loads((cache/f'ocr/p{number:03d}-300.json').read_text(encoding='utf8'))
    source=Path(page['image'])
    if page['selected']=='preprocessed':
        candidate=source.with_name(source.name.replace('original','preprocessed'))
        if candidate.exists():
            source=candidate
    im=Image.open(source).convert('RGB')
    draw=ImageDraw.Draw(im)
    font=ImageFont.load_default(size=22)
    for table in tables:
        if table['page']!=number:
            continue
        for row in table['rows']:
            box=row['bbox']
            draw.rectangle(box,outline='#237a3d',width=3)
            draw.text((max(0,box[0]-120),box[1]),row['id'].split('-')[-1],fill='#237a3d',font=font)
            for cell in row['values'].values():
                if cell['bbox']:
                    draw.rectangle(cell['bbox'],outline='#d14328' if cell['low_confidence'] else '#2364aa',width=3)
    im.thumbnail((1400,2000))
    im.save(out/f'page-{number:03d}.png')
print(f'Saved previews in {out}')
