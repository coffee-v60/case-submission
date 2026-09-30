"""Deterministic checks; dash and blank are never coerced to zero."""
from collections import Counter
import re
from src.normalization import parse_number, fold
from src.confidence import mean

def check(group: str, rule: str, expected, observed, confidence: float, difference=None, status=None, **context) -> dict:
    return dict(group=group,rule=rule,status=status or ('passed' if expected==observed else 'failed'),expected=expected,observed=observed,difference=difference,confidence=confidence,**context)

def statement_checks(table: dict, tolerance: float) -> list[dict]:
    checks = []
    by_id = {r['id']:r for r in table['rows']}
    for row in table['rows']:
        ids = row.get('component_ids', [])
        if not ids:
            continue
        valid = len(ids)==len(set(ids)) and all(i in by_id and i!=row['id'] for i in ids)
        checks.append(check('structural','aggregation_references',True,valid,row['confidence'],row_id=row['id']))
        if not valid:
            continue
        for col in table['columns']:
            total = row['values'][col['id']]
            parts = [by_id[i]['values'][col['id']] for i in ids]
            complete = all(c['state']=='numeric' for c in [total]+parts)
            observed = sum(c['value'] for c in parts) if complete else None
            difference = observed-total['value'] if complete else None
            checks.append(check('financial',row['aggregation_rule'],total['value'],observed,mean(c['confidence'] for c in [total]+parts),difference=difference,status=('passed' if abs(difference)<=tolerance else 'failed') if complete else 'warning',row_id=row['id'],column=col['id'],period=col['period'],component_ids=ids,component_states=[c['state'] for c in parts]))
        if row.get('reconciles_to') in by_id:
            checks.extend(compare_period_values(row,table,by_id[row['reconciles_to']],table,'distribution_matches_statement_total',tolerance))
    return checks

def compare_period_values(source: dict, source_table: dict, target: dict, target_table: dict, rule: str, tolerance: float) -> list[dict]:
    checks = []
    source_columns = {c['period']:c['id'] for c in source_table['columns'] if c['period']}
    target_columns = {c['period']:c['id'] for c in target_table['columns'] if c['period']}
    for period in sorted(source_columns.keys()|target_columns.keys(),reverse=True):
        a = source['values'].get(source_columns.get(period))
        b = target['values'].get(target_columns.get(period))
        complete = a is not None and b is not None and a['state']==b['state']=='numeric'
        difference = b['value']-a['value'] if complete else None
        checks.append(check('financial',rule,a['value'] if a else None,b['value'] if b else None,mean(c['confidence'] for c in [a,b] if c),difference=difference,status=('passed' if abs(difference)<=tolerance else 'failed') if complete else 'warning',row_id=source['id'],target_row_id=target['id'],period=period))
    return checks

def validate(summaries: list[dict], note: dict, relations: list[dict], cfg: dict) -> list[dict]:
    checks=[]
    start,end=cfg['summary_tables']['page_range'].values()
    checks.append(check('structural','summary_physical_pages',list(range(start,end+1)),sorted(set(t['page'] for t in summaries)),mean(t['confidence'] for t in summaries)))
    checks.append(check('structural','target_note_heading',cfg['notes']['target_note'],note['heading']['number'],note['detection_confidence']))
    tables=summaries+note['tables']
    tolerance=cfg['validation']['tolerance']
    for table in tables:
        rows=table['rows']
        checks.extend(statement_checks(table,tolerance))
        ids=[r['id'] for r in rows]
        checks.append(check('structural','unique_row_ids',len(ids),len(set(ids)),table['confidence'],table_id=table['id']))
        periods=[c['period'] for c in table['columns'] if c['period']]
        if len(periods)>1:
            checks.append(check('structural','period_order_preserved',sorted(periods,reverse=True),periods,table['confidence'],table_id=table['id'],status='passed' if periods==sorted(periods,reverse=True) else 'warning'))
        checks.append(check('structural','period_columns',True,bool(periods) or all(r.get('period') for r in rows),table['confidence'],table_id=table['id'],status='passed' if periods or all(r.get('period') for r in rows) else 'warning'))
        checks.append(check('format','currency_preserved',True,bool(table.get('unit_raw')),table['confidence'],table_id=table['id'],status='passed' if table.get('unit_raw') else 'warning'))
        for row in rows:
            checks.append(check('structural','row_page_matches_table',table['page'],row['source_page'],row['confidence'],row_id=row['id']))
            if row.get('note_reference_bbox'):
                rb,nb=row['bbox'],row['note_reference_bbox']
                overlap=max(rb[1],nb[1])<=min(rb[3],nb[3])
                checks.append(check('structural','note_reference_row_alignment',True,overlap,row['confidence'],row_id=row['id']))
            duplicates=[r['id'] for r in rows if r['id']!=row['id'] and r['bbox']==row['bbox']]
            checks.append(check('structural','duplicate_row_geometry',[],duplicates,row['confidence'],row_id=row['id']))
            for col,cell in row['values'].items():
                parsed=parse_number(cell['raw'])
                consistent=(parsed['state'],parsed['value'])==(cell['state'],cell['value'])
                checks.append(check('format','financial_value_state',True,consistent,cell['confidence'],row_id=row['id'],column=col,status='warning' if cell['state']=='invalid' else 'passed' if consistent else 'failed'))
                if cell.get('agreement',1)<1:
                    checks.append(check('format','ocr_numeric_agreement',1,cell['agreement'],cell['confidence'],status='warning',row_id=row['id'],column=col))
            children=[r for r in rows if r['hierarchy']['parent_id']==row['id']]
            if children and not row.get('component_ids'):
                for col,cell in row['values'].items():
                    parts=[r['values'][col] for r in children]
                    if cell['state']=='numeric' and all(p['state']=='numeric' for p in parts):
                        total=sum(p['value'] for p in parts)
                        diff=total-cell['value']
                        checks.append(check('financial','hierarchy_subtotal',cell['value'],total,mean([cell['confidence']]+[p['confidence'] for p in parts]),difference=diff,status='passed' if abs(diff)<=tolerance else 'failed',row_id=row['id'],column=col,component_ids=[r['id'] for r in children]))
                    elif cell['state']=='numeric':
                        checks.append(check('financial','hierarchy_subtotal',cell['value'],None,cell['confidence'],status='warning',row_id=row['id'],column=col,reason='Non-numeric component; dash/blank not treated as zero'))
            total_columns=[c for c in table['columns'] if 'toplam' in fold(c['title'])]
            for col in total_columns:
                total_cell=row['values'][col['id']]
                parts=[v for k,v in row['values'].items() if k!=col['id']]
                if total_cell['state']=='numeric' and parts and all(v['state']=='numeric' for v in parts):
                    observed=sum(v['value'] for v in parts)
                    diff=observed-total_cell['value']
                    checks.append(check('financial','note_components_sum_to_total',total_cell['value'],observed,mean(v['confidence'] for v in parts+[total_cell]),difference=diff,status='passed' if abs(diff)<=tolerance else 'failed',row_id=row['id'],components=[v['value'] for v in parts],period=row.get('period'),independent_of_ocr_selection=not bool(total_cell.get('financial_selection'))))
        # Unlabelled bottom numeric row is a candidate total, verified arithmetically.
        if table['kind']=='note' and rows and rows[-1]['normalized_label']=='[unlabelled total]':
            for col,cell in rows[-1]['values'].items():
                parts=[r['values'][col] for r in rows[:-1]]
                if parts and all(v['state']=='numeric' for v in parts+[cell]):
                    observed=sum(v['value'] for v in parts)
                    diff=observed-cell['value']
                    checks.append(check('financial','note_detail_sum',cell['value'],observed,table['confidence'],difference=diff,status='passed' if abs(diff)<=tolerance else 'failed',row_id=rows[-1]['id'],column=col))
                    if abs(diff)<=tolerance:
                        rows[-1]['row_type']='total'
        # Closing = opening + signed movements, without treating missing values as zero.
        opening=next((r for r in rows if 'acilis' in fold(r['normalized_label'])),None)
        closing=next((r for r in rows if 'kapanis' in fold(r['normalized_label'])),None)
        if opening and closing:
            detail=rows[rows.index(opening):rows.index(closing)]
            for col,cell in closing['values'].items():
                parts=[r['values'][col] for r in detail]
                if cell['state']=='numeric' and all(v['state']=='numeric' for v in parts):
                    observed=sum(v['value'] for v in parts)
                    diff=observed-cell['value']
                    checks.append(check('financial','note_movement_rollforward',cell['value'],observed,table['confidence'],difference=diff,status='passed' if abs(diff)<=tolerance else 'failed',row_id=closing['id'],column=col))
    for relation in relations:
        source=next(r for t in summaries for r in t['rows'] if r['id']==relation['summary_row_id'])
        checks.append(check('structural','relationship_note_reference',True,relation['note_number'] in source['note_reference'],source['confidence'],row_id=source['id']))
        note_ids={r['id'] for t in note['tables'] for r in t['rows']}
        checks.append(check('structural','relationship_within_note_section',True,all(row_id in note_ids for row_id in relation['note_row_ids']),relation['confidence'],row_id=source['id']))
        for evidence in relation['numeric_evidence']:
            checks.append(check('financial','summary_note_reconciliation',evidence['summary_value'],evidence['note_value'],relation['confidence'],difference=evidence['difference'],status='passed' if evidence['equal'] else 'failed',row_id=relation['summary_row_id'],period=evidence['period']))
        checks.append(check('structural','relationship_period_coverage',relation['period_evidence']['source'],relation['period_evidence']['covered'],relation['confidence'],status='passed' if set(relation['period_evidence']['source'])==set(relation['period_evidence']['covered']) else 'warning',row_id=relation['summary_row_id']))
    balance=[t for t in summaries if 'bilanco' in fold(t['title'])]
    if len(balance)>=2:
        a=next((r for r in reversed(balance[0]['rows']) if r['row_type']=='grand_total'),None)
        b=next((r for r in reversed(balance[1]['rows']) if r['row_type']=='grand_total'),None)
        if a and b:
            checks.extend(compare_period_values(a,balance[0],b,balance[1],'assets_equal_liabilities_and_equity',tolerance))
    parent_profits=[(r,t) for t in summaries for r in t['rows'] if r.get('financial_role')=='parent_profit']
    balance_profits=[(r,t) for t in balance for r in t['rows'] if r.get('financial_role')=='balance_parent_profit']
    for source,source_table in parent_profits:
        for target,target_table in balance_profits:
            checks.extend(compare_period_values(source,source_table,target,target_table,'parent_profit_matches_balance_sheet',tolerance))
    return checks

def summarize(checks: list[dict]) -> dict:
    return {group:dict(Counter(c['status'] for c in checks if c['group']==group)) for group in ['structural','format','financial']}

def error_analysis(tables: list[dict],checks: list[dict],relations: list[dict]) -> list[dict]:
    examples=[]
    for c in checks:
        if c['status']=='failed':
            examples.append(dict(record=c.get('row_id',c.get('table_id')),expected=c['expected'],produced=c['observed'],stage=c['group']+'_validation',probable_cause='OCR digit error or inferred hierarchy/column assignment; inspect cached image and token boxes.',improvement='Re-read the cell crop and verify row membership; do not force the expected sum.',evidence=c))
    cells=sorted([(v['confidence'],r['id'],k,v) for t in tables for r in t['rows'] for k,v in r['values'].items() if v.get('warnings') and v['state']!='blank'],key=lambda x:(not bool(x[3].get('financial_selection')),x[0]))
    seen=set()
    for confidence,row_id,col,cell in cells:
        if row_id in seen:
            continue
        seen.add(row_id)
        example=dict(record=row_id,column=col,expected='Unambiguous source-cell reading; no manual ground truth supplied',produced=cell,stage='ocr/normalization',probable_cause='OCR variants disagree on a digit or punctuation; confidence is reduced by measured agreement.',improvement='Inspect the saved original and preprocessed crop; use an independent OCR engine to resolve the ambiguity.',confidence=confidence)
        if cell.get('financial_selection'):
            example.update(expected=sum(cell['financial_selection']['components']),stage='ocr_disambiguation',probable_cause='Original-page OCR and original crop agree on the wrong digit. The preprocessed alternative is consistent with the independently read component cells.',improvement='Review the crop visually. This correction uses arithmetic, so the same sum check is not independent proof of OCR accuracy.')
        elif re.fullmatch(r'%[\d,]+-%[\d,]+',cell['raw']):
            example.update(expected='A percentage range preserving both endpoints',stage='normalization',probable_cause='The scalar financial-value schema cannot represent a percentage interval; raw text is retained as invalid.',improvement='Extend the schema with a range state and lower/upper bounds; do not turn the interval into a single number.')
        examples.append(example)
        if len(seen)>=3:
            break
    for rel in relations:
        if rel['warnings']:
            examples.append(dict(record=rel['summary_row_id'],expected='Unique period-consistent explanatory note row',produced=rel['note_row_ids'],stage='semantic_matching',probable_cause='Several rows express the same closing balance or closely related concepts.',improvement='Allow multiple valid links; add reviewed labels to calibrate margin and role features.',confidence=rel['confidence'],warnings=rel['warnings']))
    if len(examples)<3:
        for t in sorted(tables,key=lambda t:t['confidence'])[:3-len(examples)]:
            examples.append(dict(record=t['id'],expected='Reviewed header and row boundaries',produced=t['confidence'],stage='table_extraction',probable_cause='Lowest measured table confidence; not evidence of a known error.',improvement='Review headers against page image.'))
    return examples
