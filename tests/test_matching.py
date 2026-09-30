from src.matching import numeric_features,rank_candidates,select_period_candidates
from src.normalization import parse_number

def test_ranking_uses_financial_features():
    records=[dict(row_id='semantic_only',a_decision=.5,b_decision=.4),dict(row_id='reconciled',a_decision=.8,b_decision=.9)]
    assert rank_candidates(records,'b')[0]['row_id']=='reconciled'
    a=dict(row_id='a',evidence=[dict(period='2020',equal=True)])
    b=dict(row_id='b',evidence=[dict(period='2019',equal=True)])
    assert select_period_candidates([a,b],['2019','2020'])==[a,b]
    assert select_period_candidates([b,a],['2019','2020'])==[b,a]

def test_period_mismatch_cannot_match_equal_value():
    s=dict(values={'c':parse_number('100')})
    source=dict(columns=[dict(id='c',period='2020')])
    candidate=dict(row=s,table=dict(columns=[dict(id='c',period='2019')]))
    f=numeric_features(s,source,candidate,1)
    assert f['numeric']==0 and f['period']==0

def test_dash_is_not_a_numeric_match_to_zero():
    source=dict(values={'c':parse_number('0')})
    table=dict(columns=[dict(id='c',period='2020')])
    f=numeric_features(source,table,dict(row=dict(values={'c':parse_number('-')}),table=table),1)
    assert f['numeric']==0
