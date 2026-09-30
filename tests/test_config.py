import pytest
import yaml
from src.config import load_config,PageRange

def test_page_range():
    assert PageRange(start=5,end=7).end==7
    for start,end in [(7,5),(0,4),(-1,2)]:
        with pytest.raises(ValueError):
            PageRange(start=start,end=end)

def test_cli_overrides_and_discovery(tmp_path):
    pdf=tmp_path/'source.pdf'
    pdf.touch()
    config=yaml.safe_load(open('config.yaml',encoding='utf8'))
    path=tmp_path/'config.yaml'
    path.write_text(yaml.safe_dump(config),encoding='utf8')
    cfg=load_config(str(path),pages='2-4',note=8)
    assert cfg['document']['input_path']==str(pdf)
    assert cfg['summary_tables']['page_range']==dict(start=2,end=4)
    assert cfg['notes']['target_note']==8

def test_explicit_missing_pdf_not_silently_replaced(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config('config.yaml',pdf=str(tmp_path/'missing.pdf'))
