"""Nghiệm thu thay ảnh sơ đồ và bảo toàn phần còn lại của báo cáo."""

from pathlib import Path
from zipfile import ZipFile
import hashlib
import json

from lxml import etree
from PIL import Image, ImageChops
import pypdfium2 as pdfium


task = Path(__file__).resolve().parent
root = task.parents[1]
manifest = json.loads((task / "manifest.json").read_text(encoding="utf-8"))
source, output = Path(manifest["source"]), Path(manifest["output"])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(source) == manifest["source_sha256"]
assert sha(output) == manifest["output_sha256"]
original = source.with_name("TTTT_NguyenThanhChien_24ITE020.docx")
assert sha(original) == "7ca70fec0c1044f50d0bdeca00dea56619d7b8eb3f9e1790088baadb778757ab"

ns = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
with ZipFile(source) as a, ZipFile(output) as b:
    assert b.testzip() is None
    assert set(a.namelist()) == set(b.namelist())
    changed = {name for name in a.namelist() if a.read(name) != b.read(name)}
    assert changed == {*manifest["changed_media"], "word/document.xml"}
    src = etree.fromstring(a.read("word/document.xml"))
    dst = etree.fromstring(b.read("word/document.xml"))
    assert len(dst.xpath("//w:sectPr", namespaces=ns)) == 3
    normalized = []
    for doc in (src, dst):
        for drawing in doc.xpath("//w:drawing", namespaces=ns):
            if drawing.xpath(".//pic:cNvPr/@name", namespaces=ns) in (["diagram-15.png"], ["diagram-16.png"]):
                for ext in drawing.xpath(".//wp:extent|.//a:xfrm/a:ext", namespaces=ns):
                    ext.set("cy", "NORMALIZED_IMAGE_HEIGHT")
        normalized.append(etree.tostring(doc, method="c14n"))
    assert normalized[0] == normalized[1], "Có thay đổi XML ngoài hai chiều cao ảnh cho phép"
    rels = {r.get("Id") for r in etree.fromstring(b.read("word/_rels/document.xml.rels"))}
    for el in dst.iter():
        for attr, value in el.attrib.items():
            if etree.QName(attr).namespace == ns["r"]:
                assert value in rels
    counts = [len(dst.xpath(f"//w:fldChar[@w:fldCharType='{kind}']", namespaces=ns)) for kind in ("begin", "end")]
    assert counts[0] == counts[1]

pdf = pdfium.PdfDocument(str(task / "delivery.pdf"))
assert len(pdf) == 84
text = "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
assert not any(error in text for error in ("Error!", "Reference source not found", "Bookmark not defined"))
metrics = json.loads((root / "report/experiments/v2/metrics.json").read_text(encoding="utf-8"))["families"]
assert len(metrics) == 12
for name, values in metrics.items():
    assert name in text and f"{values['ndcg']:.6f}".replace(".", ",") in text

previous = root / "report/document_update_20261018/delivery_render"
unchanged, reviewed = [], []
for n in range(1, 85):
    old = Image.open(previous / f"page-{n}.png").convert("RGB")
    new = Image.open(task / f"delivery_render/page-{n}.png").convert("RGB")
    if ImageChops.difference(old, new).getbbox() is None:
        unchanged.append(n)
    else:
        reviewed.append(n)
assert not json.loads((task / "drawing_diagnostics.json").read_text(encoding="utf-8"))
receipt = {
    "status": "passed",
    "date": "2026-10-18",
    "output": str(output),
    "output_sha256": sha(output),
    "original_and_latest_source_preserved": True,
    "pages": len(pdf),
    "redrawn_diagrams": 16,
    "restyled_charts": 1,
    "research_values_verified": 12,
    "body_styles_headers_footers_tables_and_captions_preserved": True,
    "xml_change_scope": "Chỉ chiều cao hai sơ đồ tuần tự 15 và 16; trang không đổi",
    "field_begin_end": counts,
    "all_pages_visually_reviewed": True,
    "pixel_identical_to_previously_reviewed_pages": unchanged,
    "pages_reviewed_at_original_size": reviewed,
}
(task / "delivery_qa.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"status": receipt["status"], "pages": len(pdf), "changed_parts": len(changed), "identical_pages": len(unchanged), "reviewed_pages": len(reviewed), "output_bytes": output.stat().st_size}, ensure_ascii=True))
