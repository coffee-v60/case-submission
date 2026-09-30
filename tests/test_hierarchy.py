from src.hierarchy import assign_hierarchy, assign_statement_relationships
from src.normalization import parse_number

def row(id,label,x,value):
    return dict(id=id,normalized_label=label,bbox=[x,0,x+100,20],values={'c1':parse_number(value)})

def test_indented_children_and_leading_dash():
    rows=[row('a','Dönen Varlıklar',20,'300'),row('b','Ticari Alacaklar',40,'300'),row('c','-İlişkili Taraflar',50,'100'),row('d','-Diğer',50,'200'),row('e','TOPLAM VARLIKLAR',20,'300')]
    assign_hierarchy(rows)
    assert rows[1]['hierarchy']['parent_id']=='a'
    assert rows[2]['hierarchy']['parent_id']==rows[3]['hierarchy']['parent_id']=='b'
    assert rows[4]['row_type']=='grand_total'

def test_movement_table_not_false_parentage():
    rows=[row('a','Alımlar',20,'30'),row('b','Kapanış bakiyesi',23,'100')]
    assign_hierarchy(rows,flat=True)
    assert all(r['hierarchy']['parent_id'] is None for r in rows)
    assert rows[1]['row_type']=='total'

def test_statement_totals_and_equity_relationships():
    rows=[row('tax','Vergi Gelir / (Gideri)',20,'(30)'),row('current','Dönem Vergi Gideri',30,'(20)'),row('deferred','Ertelenmiş Vergi Geliri',30,'(10)'),row('net','DÖNEM KARI',20,'70')]
    assign_hierarchy(rows,flat=True)
    assign_statement_relationships(rows,income=True)
    assert rows[0]['component_ids']==['current','deferred']
    assert rows[1]['hierarchy']['parent_id']==rows[2]['hierarchy']['parent_id']=='tax'
    rows=[row('equity','ÖZKAYNAKLAR',20,'100'),row('parent','Ana Ortaklığa Ait Özkaynaklar',20,'80'),row('capital','Sermaye',40,'80'),row('minority','Kontrol Gücü Olmayan Paylar',20,'20'),row('total','TOPLAM KAYNAKLAR',20,'100')]
    assign_hierarchy(rows)
    assign_statement_relationships(rows)
    assert rows[0]['component_ids']==['parent','minority']
    assert rows[1]['hierarchy']['parent_id']==rows[3]['hierarchy']['parent_id']=='equity'
    assert rows[2]['hierarchy']['level']==rows[1]['hierarchy']['level']+1
    assert rows[4]['component_ids']==['equity']
