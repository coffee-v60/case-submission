from pathlib import Path
import hashlib
import pymupdf

def inspect_pdf(path: str) -> dict:
    pages = []
    with pymupdf.open(path) as doc:
        for page in doc:
            words = page.get_text('words')
            area = sum(max(0, w[2]-w[0]) * max(0, w[3]-w[1]) for w in words)
            chars = len(page.get_text().strip())
            pages.append(dict(page=page.number+1, character_count=chars, text_coverage=min(1., area / page.rect.get_area()), native_usable=chars >= 80 and len(words) >= 15))
    usable = sum(p['native_usable'] for p in pages)
    return dict(source_file=str(Path(path).resolve()), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), page_count=len(pages), has_text_layer=any(p['character_count'] for p in pages), document_type='digital_pdf' if usable == len(pages) else 'scanned_pdf' if not usable else 'mixed_pdf', pages=pages)

def render_page(pdf: str, page: int, dpi: int, folder: Path, force: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'p{page:03d}-{dpi}-original.png'
    if force or not path.exists():
        with pymupdf.open(pdf) as doc:
            doc[page-1].get_pixmap(dpi=dpi, alpha=False).save(path)
    return path
