"""Geometry-based lines and numeric column inference (no fixed pixel columns)."""
import re
from statistics import median
from src.normalization import parse_number

def group_lines(tokens: list[dict]) -> list[dict]:
    groups = []
    for token in sorted(tokens, key=lambda t: ((t['bbox'][1]+t['bbox'][3])/2, t['bbox'][0])):
        b = token['bbox']
        cy, h = (b[1]+b[3])/2, b[3]-b[1]
        nearby = [g for g in groups[-4:] if abs(g['cy']-cy) <= .48*max(h,g['height'])]
        if nearby:
            group = min(nearby, key=lambda g: abs(g['cy']-cy))
            group['tokens'].append(token)
            group['cy'] = median((t['bbox'][1]+t['bbox'][3])/2 for t in group['tokens'])
            group['height'] = median(t['bbox'][3]-t['bbox'][1] for t in group['tokens'])
        else:
            groups.append(dict(tokens=[token], cy=cy, height=h))
    for g in groups:
        g['tokens'].sort(key=lambda t: t['bbox'][0])
        g['text'] = ' '.join(t['text'] for t in g['tokens'])
        g['bbox'] = union_bbox(g['tokens'])
    return sorted(groups, key=lambda g: g['cy'])

def union_bbox(tokens: list[dict]) -> list[float] | None:
    if not tokens:
        return None
    return [min(t['bbox'][0] for t in tokens), min(t['bbox'][1] for t in tokens), max(t['bbox'][2] for t in tokens), max(t['bbox'][3] for t in tokens)]

def numeric_token(text: str) -> bool:
    return parse_number(text)['state'] in {'numeric', 'dash'}

def infer_columns(lines: list[dict], width: float) -> list[float]:
    points = []
    h = median(g['height'] for g in lines) if lines else 1
    for g in lines:
        for token in g['tokens']:
            s = token['text']
            if (numeric_token(s) or s.startswith('%')) and ('.' in s or '(' in s or '%' in s or len(s.strip('-')) >= 4) and token['bbox'][0] > width*.35:
                points.append(token['bbox'][2])
    clusters = []
    for x in sorted(points):
        if clusters and abs(x-median(clusters[-1])) < h*1.7:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [median(c) for c in clusters if len(c) >= 2]

def heading_number(text: str) -> tuple[int, str] | None:
    match = re.match(r'^\s*(?:(?:NOT|D[İIıi]PNOT)\s*)?(\d{1,2})\s*[.)\-:—–]*\s*[—–-]?\s+([A-Za-zÇĞİÖŞÜçğıöşü].+)$', text, re.I)
    if not match:
        return None
    return int(match[1]), match[2]
