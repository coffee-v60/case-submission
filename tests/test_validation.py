from src.schema import Result
from src.normalization import parse_number
from src.ocr import OCREngine
import pytest

def test_nested_schema_rejects_out_of_range_cell_confidence():
    cell=parse_number('123')
    cell['confidence']=1.01
    row=dict(id='r',raw_label='Nakit',normalized_label='Nakit',note_reference=[],hierarchy=dict(level=0,parent_id=None),row_type='line_item',values={'c':cell},confidence=.8,low_confidence=False,warnings=[])
    table=dict(id='t',title='Bilanço',page=1,columns=[dict(id='c',title='2020',period='2020')],periods=['2020'],confidence=.8,low_confidence=False,rows=[row])
    with pytest.raises(ValueError):
        Result(document={},processing={},summary_tables=[table],notes=[],relationships=[],validation=[],method_comparison={},error_analysis=[])

def test_native_document_does_not_require_ocr_assets(tmp_path):
    cfg=dict(document=dict(input_path='native.pdf'),cache_dir=str(tmp_path),rendering={},ocr=dict(tessdata=str(tmp_path/'missing'),languages=['tur','eng']))
    inspection=dict(sha256='1234567890',pages=[dict(native_usable=True)])
    engine=OCREngine(cfg,inspection)
    assert engine.languages=='tur+eng'
    inspection['pages'][0]['native_usable']=False
    with pytest.raises(RuntimeError,match='setup_assets.py'):
        OCREngine(cfg,inspection)

def test_cached_image_path_is_relocated(tmp_path):
    import json
    cfg=dict(document=dict(input_path='native.pdf'),cache_dir=str(tmp_path),rendering=dict(dpi=300,scan_dpi=160),ocr=dict(tessdata=str(tmp_path/'missing'),languages=['eng']))
    engine=OCREngine(cfg,dict(sha256='1234567890',pages=[dict(native_usable=True)]))
    image=engine.root/'pages'/'p001-300-original.png'
    image.parent.mkdir()
    image.touch()
    (engine.folder/'p001-300.json').write_text(json.dumps(dict(confidence=.9,image='C:/old/project/page.png')))
    assert engine.page(1,True)['image']==str(image)

def test_blank_recovery_requires_agreement_and_preserves_zero():
    from src.refinement import recover_blank_cells
    table=dict(columns=[dict(id='a',x_right=100),dict(id='b',x_right=200)],rows=[dict(values=dict(a=parse_number('100',bbox=[60,20,100,40]),b=parse_number('')))])
    page=dict(alternatives=[dict(variant=name,tokens=[dict(text='-',bbox=[190,30,200,33],confidence=.9)]) for name in ['original','preprocessed']])
    recover_blank_cells(table,page,.6)
    cell=table['rows'][0]['values']['b']
    assert cell['state']=='dash' and cell['value'] is None and cell['initial_raw']==''
    for variant in page['alternatives']:
        variant['tokens'][0]['text']='0'
    table['rows'][0]['values']['b']=parse_number('')
    recover_blank_cells(table,page,.6)
    assert table['rows'][0]['values']['b']['value']==0
    table['rows'][0]['values']['b']=parse_number('')
    page['alternatives'][1]['tokens']=[]
    recover_blank_cells(table,page,.6)
    assert table['rows'][0]['values']['b']['state']=='blank'

def test_financial_checks_detect_wrong_totals_and_match_periods():
    from src.validation import statement_checks,compare_period_values
    parts=[dict(id='sales',confidence=.9,values={'a':parse_number('100')}),dict(id='cost',confidence=.9,values={'a':parse_number('(40)')})]
    total=dict(id='gross',confidence=.9,component_ids=['sales','cost'],aggregation_rule='gross_profit_sum',values={'a':parse_number('61')})
    table=dict(columns=[dict(id='a',period='2020')],rows=parts+[total])
    checks=statement_checks(table,0)
    assert next(c for c in checks if c['group']=='financial')['status']=='failed'
    parts[1]['values']['a']=parse_number('-')
    assert next(c for c in statement_checks(table,0) if c['group']=='financial')['status']=='warning'
    source=dict(id='s',values=dict(a=parse_number('10'),b=parse_number('20')))
    target=dict(id='t',values=dict(a=parse_number('20'),b=parse_number('10')))
    t1=dict(columns=[dict(id='a',period='2020'),dict(id='b',period='2019')])
    t2=dict(columns=[dict(id='a',period='2019'),dict(id='b',period='2020')])
    assert all(c['status']=='passed' for c in compare_period_values(source,t1,target,t2,'test',0))
