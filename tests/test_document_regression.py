import json
from pathlib import Path
import pytest
from src.schema import Result

@pytest.fixture(scope='module')
def result():
    path=Path('data/output/result.json')
    if not path.exists():
        pytest.skip('Run main.py first to generate real-document regression artifacts')
    return json.loads(path.read_text(encoding='utf8'))

@pytest.mark.regression
def test_source_document_delivery(result):
    Result.model_validate(result)
    assert result['document']['page_count']==95
    assert result['document']['document_type']=='scanned_pdf'
    assert [t['page'] for t in result['summary_tables']]==[5,6,7]
    assert result['notes'][0]['start_page'] in [53,54]

    values=[[v['value'] for v in r['values'].values()] for t in result['summary_tables'] for r in t['rows'] if 11 in r['note_reference']]
    assert [373992222,423580000] in values
    assert [3896434,151350000] in values

    checks=result['validation']
    assert any(c['rule']=='note_components_sum_to_total' and c.get('components')==[177730044,196262178] and c['observed']==373992222 and c['status']=='passed' for c in checks)
    assert any(c['rule']=='summary_note_reconciliation' and c['observed']==373992222 and c['status']=='passed' for c in checks)

    assert result['processing']['ml']['embedding_inference']
    assert result['processing']['ml']['reranker_inference']
    for relationship in result['relationships']:
        assert set(relationship['period_evidence']['source'])==set(relationship['period_evidence']['covered'])

    assert len(result['error_analysis'])>=3
    rows={r['id']:r for t in result['summary_tables'] for r in t['rows']}
    assert rows['summary-p6-t1-r5']['values']['c2']['state']=='dash'
    assert rows['summary-p6-t1-r20']['hierarchy']['parent_id']=='summary-p6-t1-r19'
    assert rows['summary-p7-t1-r15']['hierarchy']['parent_id']=='summary-p7-t1-r14'
    for rule in ['gross_profit_sum','income_tax_sum','net_profit_sum','comprehensive_income_sum','parent_profit_matches_balance_sheet']:
        found=[c for c in checks if c['rule']==rule]
        assert len(found)==2 and all(c['status']=='passed' for c in found)
    for comparison in result['method_comparison']['items']:
        for approach in ['approach_a','approach_b']:
            assert comparison[approach]['note_row_ids']
            assert comparison[approach]['covered_periods']==['2011','2012']
