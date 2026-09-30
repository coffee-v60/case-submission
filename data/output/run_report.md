# Gerçek çalıştırma raporu

Üretim: `2026-09-30T14:16:43.416185+00:00`. Bu dosya `scripts/write_run_report.py` ile gerçek JSON ve pytest çıktılarından oluşturuldu.

PDF: **95 sayfa**, `scanned_pdf`. Dipnot 11: **53–54**. Başlık güveni: **0.885573**.

Test: **25**, başarısız: **0**, hata: **0**, atlanan: **0**.

## Tablolar

| Tablo | Satır | Güven |
|---|---:|---:|
| summary-p5-t1 | 18 | 0.956782 |
| summary-p6-t1 | 29 | 0.949828 |
| summary-p7-t1 | 29 | 0.937612 |
| note-p53-t1 | 6 | 0.776338 |
| note-p53-t2 | 5 | 0.748000 |
| note-p54-t1 | 3 | 0.866573 |
| note-p54-t2 | 5 | 0.955470 |

## Doğrulama

| Grup | Başarılı | Uyarı | Başarısız |
|---|---:|---:|---:|
| structural | 269 | 0 | 0 |
| format | 207 | 8 | 0 |
| financial | 58 | 7 | 0 |

## Eşleştirmeler

| Özet satır | Dipnot satırları | Güven | Dönem / tutar |
|---|---|---:|---|
| summary-p5-t1-r13 | note-p54-t2-r5 | 0.762060 | 2012: 373,992,222 = 373,992,222; 2011: 423,580,000 = 423,580,000 |
| summary-p7-t1-r6 | note-p53-t1-r3, note-p53-t2-r4 | 0.704995 | 2012: 3,896,434 = 3,896,434; 2011: 151,350,000 = 151,350,000 |

## Yöntem karşılaştırması

| Kalem | A bağlantıları | B bağlantıları | Aynı ilişki kümesi |
|---|---|---|---|
| Yatırım Amaçlı Gayrimenkuller | note-p54-t2-r5 | note-p54-t2-r5 | True |
| Yatırım Amaçlı Gayrimenkul Değerleme Farkları | note-p53-t1-r3, note-p53-t2-r4 | note-p53-t1-r3, note-p53-t2-r4 | True |

### Sıralama farkları

| Kalem | Aday | A sırası | B sırası |
|---|---|---:|---:|
| Yatırım Amaçlı Gayrimenkuller | note-p53-t2-r5 | 3 | 2 |
| Yatırım Amaçlı Gayrimenkuller | note-p53-t1-r6 | 2 | 3 |

Model yürütme/önbellek bilgisi: `{"embedding_inference": true, "reranker_inference": true, "fallbacks": [], "models": {"embedding": {"name": "intfloat/multilingual-e5-small", "path": "/home/admin/workspace/Project/data/cache/models/intfloat--multilingual-e5-small", "max_tokens": 512}, "reranker": {"name": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "path": "/home/admin/workspace/Project/data/cache/models/cross-encoder--mmarco-mMiniLMv2-L12-H384-v1", "max_tokens": 512}}, "embedding_cache_hit": true, "embedding_seconds": 0.0008257399995272863, "reranker_cache_hit": true, "reranker_seconds": 2.248900000267895e-05}`.

Son komut süresi: **7.041 saniye**. Süre önbellek durumuna bağlıdır; model süreleri yüklemeyi içermez. Yöntem karşılaştırması etiketli bir doğruluk ölçümü değildir.

## Gerçek hata ve belirsizlik örnekleri

### 1. note-p53-t2-r2 / ocr_disambiguation

Beklenen: `77645032`.

Üretilen: `{"raw": "77.645.032", "value": 77645032, "state": "numeric", "confidence": 0.6357106666666666, "bbox": [1923.0, 2052.0, 2129.0, 2087.0], "low_confidence": false, "warnings": ["ocr_variants_disagree", "ocr_alternative_selected_using_financial_constraint"], "unit": null, "ocr_alternatives": [{"raw": "71.645.032", "value": 71645032, "source": "original"}, {"raw": "77.645.032", "value": 77645032, "source": "preprocessed"}, {"raw": "71.645.032", "value": 71645032, "source": "crop_psm7"}], "agreement": 0.6666666666666666, "initial_raw": "71.645.032", "financial_selection": {"rule": "existing_ocr_alternative_matches_component_sum", "components": [64046943, 13598089], "selected_source": "preprocessed", "independent_validation": false}}`.

Neden: Original-page OCR and original crop agree on the wrong digit. The preprocessed alternative is consistent with the independently read component cells.

Öneri: Review the crop visually. This correction uses arithmetic, so the same sum check is not independent proof of OCR accuracy.

### 2. note-p54-t1-r3 / normalization

Beklenen: `"A percentage range preserving both endpoints"`.

Üretilen: `{"raw": "%2-%4", "value": null, "state": "invalid", "confidence": 0.230708, "bbox": [2024.0, 1060.0, 2157.0, 1095.0], "low_confidence": true, "warnings": ["unrecognized_numeric_format", "cell_evidence_below_threshold"], "unit": "percent"}`.

Neden: The scalar financial-value schema cannot represent a percentage interval; raw text is retained as invalid.

Öneri: Extend the schema with a range state and lower/upper bounds; do not turn the interval into a single number.

### 3. note-p54-t1-r2 / ocr/normalization

Beklenen: `"Unambiguous source-cell reading; no manual ground truth supplied"`.

Üretilen: `{"raw": "86,6", "value": 86.6, "state": "numeric", "confidence": 0.568664, "bbox": [1680.0, 997.0, 1794.0, 1038.0], "low_confidence": true, "warnings": ["ocr_variants_disagree"], "unit": "percent", "unit_inferred_from_label": true, "ocr_alternatives": [{"raw": "86,6", "value": 86.6, "source": "original"}, {"raw": "%386,6", "value": 386.6, "source": "preprocessed"}, {"raw": "086,6", "value": 86.6, "source": "crop_psm7"}], "agreement": 0.6666666666666666}`.

Neden: OCR variants disagree on a digit or punctuation; confidence is reduced by measured agreement.

Öneri: Inspect the saved original and preprocessed crop; use an independent OCR engine to resolve the ambiguity.

### 4. summary-p7-t1-r6 / semantic_matching

Beklenen: `"Unique period-consistent explanatory note row"`.

Üretilen: `["note-p53-t1-r3", "note-p53-t2-r4"]`.

Neden: Several rows express the same closing balance or closely related concepts.

Öneri: Allow multiple valid links; add reviewed labels to calibrate margin and role features.

## Yorum sınırları

Uyarılar korunur. Finansal denkliğin OCR alternatifini seçmek için kullanıldığı kayıtlar `independent_of_ocr_selection: false` taşır; aynı denklik bağımsız doğrulama başarısı sayılamaz. Güven skorları kalibre edilmiş olasılık değildir.
