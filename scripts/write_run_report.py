"""Generate the observed-results report from JSON and pytest JUnit artifacts."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
out=root/'data/output'
r=json.loads((out/'result.json').read_text(encoding='utf8'))
v=json.loads((out/'validation.json').read_text(encoding='utf8'))
tests=ET.parse(out/'pytest.xml').getroot().find('testsuite')
tables=r['summary_tables']+r['notes'][0]['tables']
report=['# Gerçek çalıştırma raporu','',f"Üretim: `{r['processing']['timestamp_utc']}`. Bu dosya `scripts/write_run_report.py` ile gerçek JSON ve pytest çıktılarından oluşturuldu.",'',f"PDF: **{r['document']['page_count']} sayfa**, `{r['document']['document_type']}`. Dipnot {r['notes'][0]['number']}: **{r['notes'][0]['start_page']}–{r['notes'][0]['end_page']}**. Başlık güveni: **{r['notes'][0]['detection_confidence']:.6f}**.",'',f"Test: **{tests.attrib['tests']}**, başarısız: **{tests.attrib['failures']}**, hata: **{tests.attrib['errors']}**, atlanan: **{tests.attrib['skipped']}**.",'','## Tablolar','','| Tablo | Satır | Güven |','|---|---:|---:|']
for t in tables:
    report.append(f"| {t['id']} | {len(t['rows'])} | {t['confidence']:.6f} |")
report+=['','## Doğrulama','','| Grup | Başarılı | Uyarı | Başarısız |','|---|---:|---:|---:|']
for group,counts in v['summary'].items():
    report.append(f"| {group} | {counts.get('passed',0)} | {counts.get('warning',0)} | {counts.get('failed',0)} |")
report+=['','## Eşleştirmeler','','| Özet satır | Dipnot satırları | Güven | Dönem / tutar |','|---|---|---:|---|']
for rel in r['relationships']:
    evidence='; '.join(f"{e['period']}: {e['summary_value']:,} = {e['note_value']:,}" for e in rel['numeric_evidence'])
    report.append(f"| {rel['summary_row_id']} | {', '.join(rel['note_row_ids'])} | {rel['confidence']:.6f} | {evidence} |")
report+=['','## Yöntem karşılaştırması','','| Kalem | A bağlantıları | B bağlantıları | Aynı ilişki kümesi |','|---|---|---|---|']
for c in r['method_comparison']['items']:
    report.append(f"| {c['label']} | {', '.join(c['approach_a']['note_row_ids'])} | {', '.join(c['approach_b']['note_row_ids'])} | {c['same_decision']} |")
report+=['','### Sıralama farkları','','| Kalem | Aday | A sırası | B sırası |','|---|---|---:|---:|']
for c in r['method_comparison']['items']:
    for difference in c['ranking_differences']:
        report.append(f"| {c['label']} | {difference['row_id']} | {difference['a_position']} | {difference['b_position']} |")
report+=['',f"Model yürütme/önbellek bilgisi: `{json.dumps(r['processing']['ml'],ensure_ascii=False)}`.",'',f"Son komut süresi: **{r['processing']['duration_seconds']:.3f} saniye**. Süre önbellek durumuna bağlıdır; model süreleri yüklemeyi içermez. Yöntem karşılaştırması etiketli bir doğruluk ölçümü değildir.",'','## Gerçek hata ve belirsizlik örnekleri','']
for i,e in enumerate(r['error_analysis'],1):
    report += [f"### {i}. {e['record']} / {e['stage']}",'',f"Beklenen: `{json.dumps(e['expected'],ensure_ascii=False)}`.",'',f"Üretilen: `{json.dumps(e['produced'],ensure_ascii=False)}`.",'',f"Neden: {e['probable_cause']}",'',f"Öneri: {e['improvement']}",'']
report+=['## Yorum sınırları','','Uyarılar korunur. Finansal denkliğin OCR alternatifini seçmek için kullanıldığı kayıtlar `independent_of_ocr_selection: false` taşır; aynı denklik bağımsız doğrulama başarısı sayılamaz. Güven skorları kalibre edilmiş olasılık değildir.']
(out/'run_report.md').write_text('\n'.join(report)+'\n',encoding='utf8')
print(out/'run_report.md')
