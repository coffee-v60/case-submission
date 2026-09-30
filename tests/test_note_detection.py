from src.layout import group_lines
from src.locator import locate_note

def page(number,text,y=160):
    words=[]
    x=50
    for t in text.split():
        words.append(dict(text=t,bbox=[x,y,x+len(t)*8,y+20],confidence=.95,page=number))
        x+=len(t)*8+8
    words.append(dict(text='Açıklamalar',bbox=[50,y+45,150,y+65],confidence=.95,page=number))
    return dict(page=number,width=1000,height=1400,tokens=words)

def test_detection_has_no_fixed_page():
    doc=[page(3,'7. FİNANSAL BORÇLAR'),page(4,'7. FİNANSAL BORÇLAR (devamı)'),page(5,'8. TİCARİ ALACAKLAR')]
    detected=locate_note(doc,7)
    assert (detected['start_page'],detected['end_page'])==(3,4)

def test_body_reference_not_heading():
    doc=[page(2,'11 milyon tutarındaki işlem açıklanmıştır'),page(9,'11. YATIRIM AMAÇLI GAYRİMENKULLER'),page(10,'12. MADDİ DURAN VARLIKLAR')]
    assert locate_note(doc,11)['start_page']==9

def test_toc_not_section():
    doc=[page(2,'11. YATIRIM AMAÇLI GAYRİMENKULLER .... 49'),page(8,'11. YATIRIM AMAÇLI GAYRİMENKULLER'),page(9,'12. MADDİ DURAN VARLIKLAR')]
    assert locate_note(doc,11)['start_page']==8

def test_geometry_groups_columns_into_one_line():
    p=page(1,'Nakit 123.000 456.000')
    assert len(group_lines(p['tokens']))==2
