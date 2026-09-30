import pymupdf
from src.pdf import inspect_pdf

def test_text_layer_detected_per_page(tmp_path):
    path=tmp_path/'mixed.pdf'
    doc=pymupdf.open()
    p=doc.new_page()
    p.insert_text((30,50),'This is a digital report with enough words and characters to test native text extraction on this page. This is another line.')
    doc.new_page()
    doc.save(path)
    doc.close()
    result=inspect_pdf(str(path))
    assert result['page_count']==2
    assert result['has_text_layer'] is True
    assert result['pages'][0]['text_coverage']>0
    assert result['pages'][1]['text_coverage']==0
