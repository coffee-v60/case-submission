from statistics import median
from src.normalization import fold

def assign_hierarchy(rows: list[dict], flat: bool = False) -> None:
    if not rows:
        return
    base = min(r['bbox'][0] for r in rows)
    height = median(r['bbox'][3]-r['bbox'][1] for r in rows)
    stack = []
    previous = None
    for row in rows:
        label = row['normalized_label']
        f = fold(label)
        level = max(0, round((row['bbox'][0]-base)/max(height*.8, 1)))
        has_numbers = any(v['state']=='numeric' for v in row['values'].values())
        upper = label.isupper()
        if flat:
            row['hierarchy'] = dict(level=0,parent_id=None,evidence=['flat_table_layout'])
            row['row_type'] = 'total' if label=='[unlabelled total]' or 'kapanis' in f or 'net defter' in f else 'subtotal' if upper and has_numbers else 'section' if not has_numbers else 'line_item'
            continue
        if f.startswith('toplam') or f == 'total':
            row_type = 'grand_total' if upper else 'total'
            level = 0
        elif not has_numbers:
            row_type = 'section'
        elif level == 0 or upper:
            row_type = 'subtotal'
        else:
            row_type = 'line_item'
        parent = None
        if label.startswith(('-', '~')) and previous:
            if not previous['normalized_label'].startswith(('-', '~')):
                parent = previous['id']
                level = previous['hierarchy']['level']+1
            else:
                parent = previous['hierarchy']['parent_id']
                level = previous['hierarchy']['level']
        else:
            while stack and stack[-1]['hierarchy']['level'] >= level:
                stack.pop()
            if stack:
                parent = stack[-1]['id']
        row['row_type'] = row_type
        row['hierarchy'] = dict(level=level, parent_id=parent, evidence=['indentation','leading_marker','capitalization','numeric_presence'])
        if row_type in {'section','subtotal'}:
            stack.append(row)
        previous = row

def assign_statement_relationships(rows: list[dict], income: bool = False) -> None:
    by_id = {r['id']:r for r in rows}
    roles = {}
    for row in rows:
        label = fold(row['normalized_label'])
        role = None
        if 'dagilim' not in label:
            if income and label.startswith('brut kar'):
                role = 'gross_profit'
            elif income and label.startswith('faaliyet kar'):
                role = 'operating_profit'
            elif income and label.startswith('vergi oncesi'):
                role = 'pretax_profit'
            elif income and label.startswith('donem kar'):
                role = 'net_profit'
            elif income and label.startswith('vergi gelir'):
                role = 'income_tax'
            elif income and label.startswith('diger kapsamli'):
                role = 'other_comprehensive_income'
            elif income and label.startswith('toplam kapsamli'):
                role = 'comprehensive_income'
            elif label == 'ozkaynaklar':
                role = 'equity'
            elif label.startswith('ana ortakliga ait ozkaynak'):
                role = 'parent_equity'
            elif label.startswith('net donem kar'):
                role = 'balance_parent_profit'
        if role:
            row['financial_role'] = role
            roles[role] = row

    def aggregate(total, components, rule, parent=True):
        if not total or not components:
            return
        total['component_ids'] = [r['id'] for r in components]
        total['aggregation_rule'] = rule
        if total['row_type'] not in {'total','grand_total'}:
            total['row_type'] = 'subtotal'
        if parent:
            for child in components:
                child['hierarchy']['parent_id'] = total['id']
                child['hierarchy']['evidence'] = ['statement_role','row_order']

    if income:
        previous = None
        for role, rule in [('gross_profit','gross_profit_sum'),('operating_profit','operating_profit_sum'),('pretax_profit','pretax_profit_sum')]:
            total = roles.get(role)
            if total:
                start = rows.index(previous)+1 if previous else 0
                parts = ([previous] if previous else [])+rows[start:rows.index(total)]
                aggregate(total,[r for r in parts if r['row_type']!='section'],rule)
                previous = total
        tax, net = roles.get('income_tax'), roles.get('net_profit')
        if tax and net and rows.index(tax)<rows.index(net):
            aggregate(tax,rows[rows.index(tax)+1:rows.index(net)],'income_tax_sum')
        if net and tax and roles.get('pretax_profit'):
            aggregate(net,[roles['pretax_profit'],tax],'net_profit_sum')
        other, comprehensive = roles.get('other_comprehensive_income'), roles.get('comprehensive_income')
        if other and comprehensive and rows.index(other)<rows.index(comprehensive):
            aggregate(other,rows[rows.index(other)+1:rows.index(comprehensive)],'other_comprehensive_income_sum')
        if comprehensive and net and other:
            aggregate(comprehensive,[net,other],'comprehensive_income_sum')
            comprehensive['row_type'] = 'grand_total'
        for index, section in enumerate(rows):
            label = fold(section['normalized_label'])
            if 'dagilim' not in label:
                continue
            target = comprehensive if 'kapsamli' in label else net
            parts = []
            for child in rows[index+1:]:
                if child['normalized_label']=='[unlabelled total]':
                    aggregate(child,parts,'distribution_sum',parent=False)
                    if target:
                        child['reconciles_to'] = target['id']
                    break
                if child['row_type']!='line_item':
                    break
                parts.append(child)
                child['hierarchy']['parent_id'] = section['id']
                child['hierarchy']['evidence'] = ['distribution_section']
                if target:
                    child['distribution_of'] = target['id']
                    if 'ana ortaklik' in fold(child['normalized_label']) and target is net:
                        child['financial_role'] = 'parent_profit'
    else:
        equity, parent = roles.get('equity'), roles.get('parent_equity')
        if equity and parent:
            minority = next((r for r in rows[rows.index(parent)+1:] if 'kontrol gucu olmayan' in fold(r['normalized_label'])),None)
            if minority:
                aggregate(equity,[parent,minority],'equity_sum')
                minority['row_type'] = 'line_item'
        for total in [r for r in rows if r['row_type']=='grand_total']:
            parts = [r for r in rows[:rows.index(total)] if r['row_type']=='subtotal' and r['hierarchy']['parent_id'] is None]
            aggregate(total,parts,'balance_total_sum')

    def level(row, seen):
        parent = row['hierarchy']['parent_id']
        if parent is None or parent not in by_id:
            return 0
        if parent in seen:
            raise ValueError('Cyclic statement hierarchy')
        return 1+level(by_id[parent],seen|{parent})
    for row in rows:
        row['hierarchy']['level'] = level(row,{row['id']})
