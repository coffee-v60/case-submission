import re
from src.layout import group_lines, heading_number
from src.confidence import mean, score
from src.normalization import fold

def heading_candidates(page: dict) -> list[dict]:
    lines = group_lines(page['tokens'])
    hits = []
    baseline = mean(g['height'] for g in lines)
    for idx, line in enumerate(lines):
        parsed = heading_number(line['text'])
        if not parsed:
            continue
        number, title = parsed
        letters = [c for c in title if c.isalpha()]
        uppercase = sum(c.isupper() for c in letters)/max(1,len(letters))
        toc = bool(re.search(r'\.{3,}|\s\d{1,2}\s*$', title)) or 'icindekiler' in fold(' '.join(g['text'] for g in lines[:8]))
        semantic = any(w in fold(title) for w in ['varlik','borc','finans','gelir','gider','sermaye','yatirim','gayrimenkul','risk','vergi','nakit','islem','alacak','karsilik','bilgi','hisse','stok','fayda','faaliyet'])
        context = idx+1 < len(lines) and len(lines[idx+1]['text']) > 15
        features = dict(number=1., uppercase=uppercase, length=float(5 <= len(title) <= 120), position=max(0.,1-line['cy']/page['height']), size=min(1.,line['height']/max(1,baseline)), context=float(context), semantic=float(semantic))
        confidence = score(features, dict(number=.2, uppercase=.25, length=.1, position=.1, size=.1, context=.1, semantic=.15)) * (0.25 if toc else 1.)
        if uppercase < .65:
            confidence *= .45
        hits.append(dict(number=number, title=title, page=page['page'], y=line['bbox'][1]/page['height'], bottom=line['bbox'][3]/page['height'], confidence=confidence, features=features, toc=toc, raw=line['text']))
    return hits

def locate_note(pages: list[dict], target: int) -> dict:
    headings = [h for page in pages for h in heading_candidates(page)]
    matches = [h for h in headings if h['number']==target and h['confidence'] >= .65 and not h['toc']]
    if not matches:
        raise ValueError(f'No reliable heading found for note {target}. Inspect OCR cache.')
    matches.sort(key=lambda h:(h['page'],h['y']))
    first = matches[0]
    following = [h for h in headings if h['number'] > target and h['confidence'] >= .65 and (h['page'],h['y']) > (first['page'],first['y'])]
    following.sort(key=lambda h:(h['page'],h['y']))
    boundary = following[0] if following else None
    next_page_header = boundary and boundary['page'] > first['page'] and boundary['y'] < .3
    end_page = boundary['page']-int(bool(next_page_header)) if boundary else max(p['page'] for p in pages)
    return dict(number=target, title=first['title'], start_page=first['page'], end_page=end_page, start_y=first['y'], end_y=1. if next_page_header or not boundary else boundary['y'], detection_confidence=first['confidence'], heading=first, next_heading=boundary, all_target_headings=matches, warnings=[] if boundary else ['next_note_boundary_not_found'])
