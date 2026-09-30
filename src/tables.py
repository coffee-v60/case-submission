import re
from statistics import median
from src.layout import group_lines, infer_columns, union_bbox, numeric_token
from src.normalization import parse_number, normalize_text, extract_years, fold
from src.confidence import mean, score, flag
from src.hierarchy import assign_hierarchy, assign_statement_relationships

def extract_table(page: dict, threshold: float, kind: str = 'summary', region: tuple[float,float] = (0.,1.), table_index: int = 1, context: str = '') -> dict | None:
    lines = [g for g in group_lines(page['tokens']) if region[0]*page['height'] <= g['cy'] < region[1]*page['height']]
    if not lines:
        return None
    anchors = infer_columns(lines, page['width'])
    if not anchors:
        return None
    h = median(g['height'] for g in lines)
    year_lines = [g for g in lines if len([t for t in g['tokens'] if re.fullmatch(r'(19|20)\d{2}', t['text']) and t['bbox'][0] > page['width']*.45]) >= 2]
    header = year_lines[0] if year_lines else None
    if kind == 'summary' and header:
        year_tokens = [t for t in header['tokens'] if re.fullmatch(r'(19|20)\d{2}',t['text']) and t['bbox'][0] > page['width']*.45]
        anchors = [min(anchors, key=lambda x:abs(x-t['bbox'][2])) for t in year_tokens]
        anchors = sorted(set(anchors))
    elif len(anchors)>6:
        return None
    first_numeric = next((g for g in lines if sum((numeric_token(t['text']) or t['text'].startswith('%')) and ('.' in t['text'] or '(' in t['text'] or '%' in t['text']) for t in g['tokens']) >= 2), None)
    if first_numeric is None:
        return None
    start_y = header['bbox'][3] if header else first_numeric['bbox'][1]-h
    if kind == 'note' and not header:
        preceding = [g for g in lines if first_numeric['bbox'][1]-h*3 < g['cy'] < first_numeric['bbox'][1] and any(t['bbox'][0]<page['width']*.4 for t in g['tokens'])]
        if preceding:
            start_y = preceding[-1]['bbox'][1]-1
    body = [g for g in lines if g['cy'] > start_y and g['cy'] < page['height']*.9]
    column_headers = []
    for j, anchor in enumerate(anchors):
        nearby = []
        for g in lines:
            if g['cy'] <= start_y and g['cy'] >= start_y-h*8:
                if any(t['bbox'][0]<page['width']*.4 for t in g['tokens']) and len(g['text'])>90:
                    continue
                nearby.extend(t for t in g['tokens'] if abs(t['bbox'][2]-anchor) < h*6)
        text = ' '.join(t['text'] for t in nearby)
        years = extract_years(text)
        column_headers.append(dict(id=f'c{j+1}', title=text, period=years[-1] if years else None, x_right=anchor))
    # Leftmost value start and note-reference cluster separate label from numeric columns.
    starts = [t['bbox'][0] for g in body for t in g['tokens'] if numeric_token(t['text']) and abs(t['bbox'][2]-anchors[0]) < h*2 and len(t['text'])>=4]
    value_left = median(starts)-h*1.8 if starts else anchors[0]-h*7
    ref_xs = [t['bbox'][0] for g in body for t in g['tokens'] if re.fullmatch(r'\d{1,2}(?:[,;]\d{1,2})*',t['text']) and page['width']*.35 < t['bbox'][0] < value_left]
    ref_x = median(ref_xs) if kind=='summary' and ref_xs else None
    label_right = ref_x-h if ref_x else value_left
    boundaries = [(anchors[i]+anchors[i+1])/2 for i in range(len(anchors)-1)]
    rows = []
    table_id = f'{kind}-p{page["page"]}-t{table_index}'
    pending = None
    for g in body:
        if any(s in fold(g['text']) for s in ['ekteki dipnotlar', 'tum tutarlar']):
            continue
        label_tokens = [t for t in g['tokens'] if t['bbox'][0] < label_right]
        value_tokens = [t for t in g['tokens'] if t['bbox'][0] >= value_left]
        if not label_tokens and not value_tokens:
            continue
        label = normalize_text(' '.join(t['text'] for t in label_tokens)).strip(' .|:')
        if label and not any(c.isalpha() for c in label):
            continue
        if len(label)>135:  # narrative paragraph, not a financial row
            continue
        cells = {}
        extras = []
        for j,col in enumerate(column_headers):
            ts = [t for t in value_tokens if (j==0 or t['bbox'][2]>boundaries[j-1]) and (j==len(anchors)-1 or t['bbox'][2]<=boundaries[j])]
            ts = [t for t in ts if re.search(r'\d|[-–—()]', t['text'])]
            numerics = [t for t in ts if parse_number(t['text'])['state']=='numeric']
            if numerics and any(parse_number(t['text'])['state']=='dash' for t in ts):
                extras.append('dash_glyph_next_to_number_ignored')
                ts = numerics
            raw = ''.join(t['text'] for t in ts)
            alignment = max(0.,1-abs(max(t['bbox'][2] for t in ts)-anchors[j])/(h*4)) if ts else 0.
            cells[col['id']] = parse_number(raw, mean(t['confidence'] for t in ts) if ts else page['confidence'], alignment, union_bbox(ts), threshold)
        has_value = any(v['state'] in {'numeric','dash','invalid'} for v in cells.values())
        # Join wrapped labels only when the next line carries values and indentation agrees.
        if pending:
            if has_value and not fold(pending['label']).endswith(('dagilimi','varliklar','yukumlulukler')) and g['cy']-pending['cy'] < h*2.5 and abs(g['bbox'][0]-pending['bbox'][0]) < h*2:
                label = pending['label']+' '+label
                label_tokens = pending['tokens']+label_tokens
            else:
                rows.append(pending['row'])
            pending = None
        ref_tokens = [t for t in g['tokens'] if ref_x and abs(t['bbox'][0]-ref_x)<h*2 and t['bbox'][0]<value_left]
        refs = [int(s) for t in ref_tokens for s in re.findall(r'\b\d{1,2}\b',t['text'])]
        row_conf = score(dict(cells=mean(v['confidence'] for v in cells.values()), coverage=mean(v['state']!='blank' for v in cells.values()), geometry=mean(max(0.,1-abs(t['bbox'][1]-g['bbox'][1])/max(h,1)) for t in g['tokens']), label=mean(t['confidence'] for t in label_tokens), reference=float(not ref_tokens or bool(refs))), dict(cells=.4,coverage=.15,geometry=.15,label=.2,reference=.1))
        row = dict(id='', raw_label=' '.join(t['text'] for t in label_tokens), normalized_label=label or '[unlabelled total]', note_reference=sorted(set(refs)), note_reference_bbox=union_bbox(ref_tokens), bbox=union_bbox(label_tokens or g['tokens']), values=cells, confidence=row_conf, warnings=extras, source_page=page['page'])
        if '(%)' in label:
            for cell in cells.values():
                if cell.get('unit') is None:
                    cell['unit']='percent'
                    cell['unit_inferred_from_label']=True
        flag(row,threshold,'row_geometry_or_recognition_uncertain')
        if not has_value and label and not label.isupper():
            pending = dict(row=row,label=label,cy=g['cy'],bbox=g['bbox'],tokens=label_tokens)
        elif label or any(v['state']=='numeric' for v in cells.values()):
            rows.append(row)
    if pending:
        rows.append(pending['row'])
    if not rows:
        return None
    for i,row in enumerate(rows):
        row['id'] = f'{table_id}-r{i+1}'
    if kind == 'note':
        observed_years = [y for row in rows for y in extract_years(row['normalized_label'])]
        dominant_year = max(set(observed_years), key=observed_years.count) if observed_years else None
        for row in rows:
            years = extract_years(row['normalized_label'])
            row['period'] = years[-1] if years else dominant_year
    income = any('gelir tablosu' in fold(g['text']) for g in lines)
    assign_hierarchy(rows,flat=kind=='note' or income)
    if kind=='summary':
        assign_statement_relationships(rows,income=income)
    titles = [g['text'] for g in lines if g['cy'] < start_y and any(w in fold(g['text']) for w in ['bilanco','tablosu'])]
    title = ' '.join(titles) if titles else context or ' '.join(g['text'] for g in lines[:2])
    unit_lines = [g['text'] for g in group_lines(page['tokens']) if 'lira' in fold(g['text']) and 'tutar' in fold(g['text'])]
    table_conf = score(dict(rows=mean(r['confidence'] for r in rows), periods=mean(c['period'] is not None for c in column_headers), headers=float(header is not None), consistency=mean(mean(v['state']!='invalid' for v in r['values'].values()) for r in rows)),dict(rows=.5,periods=.2,headers=.15,consistency=.15))
    table_periods=list(dict.fromkeys(c['period'] for c in column_headers if c['period'])) or list(dict.fromkeys(r.get('period') for r in rows if r.get('period')))
    percent_table=all(all(v.get('unit')=='percent' for v in r['values'].values()) for r in rows)
    return flag(dict(id=table_id, page=page['page'], title=title, kind=kind, columns=column_headers, periods=table_periods, currency='TRY' if unit_lines and not percent_table else None, unit_raw='%' if percent_table else ' '.join(unit_lines) or None, confidence=table_conf, rows=rows, region=list(region)),threshold,'header_or_layout_uncertain')

def extract_note_tables(page: dict, note: dict, threshold: float) -> list[dict]:
    top = note['start_y'] if page['page']==note['start_page'] else 0.12
    bottom = note['end_y'] if page['page']==note['end_page'] else .9
    lines = [g for g in group_lines(page['tokens']) if top*page['height'] <= g['cy'] < bottom*page['height']]
    if not lines:
        return []
    h = median(g['height'] for g in lines)
    financial = [g for g in lines if sum((numeric_token(t['text']) or t['text'].startswith('%')) and ('.' in t['text'] or '(' in t['text'] or '%' in t['text'] or len(t['text'])>4) and t['bbox'][0]>page['width']*.4 for t in g['tokens'])>=2]
    blocks = []
    for g in financial:
        if not blocks or g['cy']-blocks[-1][-1]['cy'] > h*4.5:
            blocks.append([g])
        else:
            blocks[-1].append(g)
    tables = []
    for i,block in enumerate(blocks,1):
        lo = max(top,(block[0]['bbox'][1]-h*9)/page['height'])
        hi = min(bottom,(block[-1]['bbox'][3]+h*.6)/page['height'])
        table = extract_table(page,threshold,'note',(lo,hi),i,note['title'])
        if table:
            table['note_number'] = note['number']
            tables.append(table)
    return tables
