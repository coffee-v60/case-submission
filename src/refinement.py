from collections import Counter
from pathlib import Path
import hashlib
import json
import re
from statistics import median
from PIL import Image, ImageOps
from src.normalization import parse_number

def recover_blank_cells(table: dict, page: dict, threshold: float) -> None:
    columns = table['columns']
    variants = page.get('alternatives', [])
    for row in table['rows']:
        boxes = [v['bbox'] for v in row['values'].values() if v.get('bbox')]
        if not boxes:
            continue
        center = median((b[1]+b[3])/2 for b in boxes)
        height = median(b[3]-b[1] for b in boxes)
        for index, column in enumerate(columns):
            cell = row['values'][column['id']]
            if cell['state'] != 'blank':
                continue
            anchor = column['x_right']
            left = (columns[index-1]['x_right']+anchor)/2 if index else anchor-height*10
            right = (columns[index+1]['x_right']+anchor)/2 if index+1<len(columns) else anchor+height
            readings = []
            for variant in variants:
                tokens = sorted([t for t in variant['tokens'] if left < (t['bbox'][0]+t['bbox'][2])/2 < right and abs((t['bbox'][1]+t['bbox'][3])/2-center)<height*.65], key=lambda t:t['bbox'][0])
                raw = ''.join(t['text'] for t in tokens)
                parsed = parse_number(raw)
                readings.append(dict(source=variant['variant'],raw=raw,state=parsed['state'],value=parsed['value'],tokens=tokens))
            valid = [r for r in readings if r['state'] in {'numeric','dash'}]
            if not valid:
                continue
            votes = Counter((r['state'],r['value']) for r in valid)
            winner, count = votes.most_common(1)[0]
            agreement = count/max(1,len(readings))
            if count < 2 or agreement <= .5:
                cell['warnings'].append('blank_cell_ocr_disagreement')
                continue
            selected = next(r for r in valid if (r['state'],r['value'])==winner)
            tokens = selected['tokens']
            box = [min(t['bbox'][0] for t in tokens),min(t['bbox'][1] for t in tokens),max(t['bbox'][2] for t in tokens),max(t['bbox'][3] for t in tokens)]
            ocr_confidence = sum(t['confidence'] for r in valid if (r['state'],r['value'])==winner for t in r['tokens'])/sum(len(r['tokens']) for r in valid if (r['state'],r['value'])==winner)
            alignment = max(0.,1-abs(box[2]-anchor)/(height*4))
            recovered = parse_number(selected['raw'],ocr_confidence,alignment,box,threshold)
            recovered['confidence'] = round(recovered['confidence']*agreement,6)
            recovered['low_confidence'] = recovered['confidence']<threshold
            recovered.update(initial_raw='',agreement=agreement,recovery=dict(method='page_ocr_consensus',readings=[{k:v for k,v in r.items() if k!='tokens'} for r in readings]))
            recovered['warnings'].append('recovered_from_page_ocr')
            cell.update(recovered)

def refine_cells(table: dict, page: dict, engine) -> None:
    if page['backend']=='native':
        return
    recover_blank_cells(table,page,engine.cfg['confidence']['low_confidence_threshold'])
    image = Image.open(page['image'])
    cache_dir = engine.root/'cells'
    cache_dir.mkdir(exist_ok=True)
    for row in table['rows']:
        for cell in row['values'].values():
            if not cell['bbox'] or cell['state'] not in {'numeric','invalid'} or '%' in cell['raw']:
                continue
            box = cell['bbox']
            alternatives=[]
            for variant in page.get('alternatives',[]):
                tokens=[t for t in variant['tokens'] if abs((t['bbox'][1]+t['bbox'][3]-box[1]-box[3])/2)<(box[3]-box[1])*.65 and abs(t['bbox'][2]-box[2])<(box[3]-box[1])*1.5 and re.search(r'\d',t['text'])]
                if tokens:
                    raw=''.join(t['text'] for t in tokens)
                    parsed=parse_number(raw)
                    if parsed['state']=='numeric':
                        alternatives.append(dict(raw=raw,value=parsed['value'],source=variant['variant']))
            disagreement=any(a['value']!=cell['value'] for a in alternatives)
            suspect=bool(re.fullmatch(r'\(?\d{7,}\)?',cell['raw'].strip()) or re.search(r'\.\d{3},\d{3}$',cell['raw'].strip()))
            if not disagreement and not suspect and cell['confidence'] >= .86:
                continue
            key=hashlib.sha256(json.dumps([page['page'],page['dpi'],box]).encode()).hexdigest()[:20]
            cache=cache_dir/f'{key}.json'
            if cache.exists() and not engine.force:
                crop_result=json.loads(cache.read_text(encoding='utf8'))
            else:
                pad=max(3,int((box[3]-box[1])*.25))
                crop=image.crop((max(0,box[0]-pad),max(0,box[1]-pad),min(image.width,box[2]+pad),min(image.height,box[3]+pad)))
                crop=ImageOps.expand(crop,border=12,fill='white')
                tokens=engine.read_image(crop,page['page'],psm=7,whitelist='0123456789.,()-')
                raw=''.join(t['text'] for t in tokens)
                crop_result=dict(raw=raw,confidence=sum(t['confidence'] for t in tokens)/max(1,len(tokens)))
                cache.write_text(json.dumps(crop_result),encoding='utf8')
            parsed=parse_number(crop_result['raw'])
            if parsed['state']=='numeric':
                alternatives.append(dict(raw=crop_result['raw'],value=parsed['value'],source='crop_psm7'))
            votes=Counter(a['value'] for a in alternatives)
            cell['ocr_alternatives']=alternatives
            if votes:
                winner,count=votes.most_common(1)[0]
                agreement=count/len(alternatives)
                cell['agreement']=agreement
                if count>=2 and agreement>.5 and winner!=cell['value']:
                    cell['initial_raw']=cell['raw']
                    chosen=next(a for a in alternatives if a['value']==winner)
                    cell['raw'],cell['value'],cell['state']=chosen['raw'],winner,'numeric'
                    cell['warnings'].append('corrected_by_independent_ocr_agreement')
                if agreement<1:
                    cell['confidence']*=agreement
                    cell['warnings'].append('ocr_variants_disagree')
                cell['low_confidence']=cell['confidence']<engine.cfg['confidence']['low_confidence_threshold']
    total_cols=[c for c in table['columns'] if 'toplam' in c['title'].lower()]
    for row in table['rows']:
        for col in total_cols:
            total=row['values'][col['id']]
            parts=[v for key,v in row['values'].items() if key!=col['id']]
            if not parts or not all(v['state']=='numeric' for v in parts):
                continue
            expected=sum(v['value'] for v in parts)
            observed=[a for a in total.get('ocr_alternatives',[]) if a['value']==expected]
            if observed and total['value']!=expected:
                total['initial_raw']=total['raw']
                total['raw'],total['value']=observed[0]['raw'],observed[0]['value']
                total['financial_selection']=dict(rule='existing_ocr_alternative_matches_component_sum',components=[v['value'] for v in parts],selected_source=observed[0]['source'],independent_validation=False)
                total['warnings'].append('ocr_alternative_selected_using_financial_constraint')
