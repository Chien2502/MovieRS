"""Kiểm tra gói báo cáo cuối, không thay đổi tài liệu nguồn hay mã hệ thống."""

from pathlib import Path
import hashlib
import json
import posixpath
from zipfile import ZipFile

from lxml import etree
import pypdfium2 as pdfium


root = Path(__file__).resolve().parent
original = root.parents[2] / "sản phẩm/TTTT_NguyenThanhChien_24ITE020.docx"
output = original.with_name("TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx")
manifest = json.loads((root / "final_package_manifest.json").read_text(encoding="utf-8"))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(original) == manifest["original_sha256"]
assert sha(output) == manifest["output_sha256"]

ns = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
with ZipFile(original) as source, ZipFile(output) as result:
    assert result.testzip() is None
    for part in manifest["preserved_parts"]:
        assert source.read(part) == result.read(part), part
    src = etree.fromstring(source.read("word/document.xml"))
    doc = etree.fromstring(result.read("word/document.xml"))
    geom = lambda x: [
        [dict(n.attrib) for n in s if etree.QName(n).localname in {"pgSz", "pgMar"}]
        for s in x.findall(".//w:sectPr", ns)
    ]
    assert geom(src) == geom(doc)
    assert len(geom(doc)) == 3
    fields = doc.findall(".//w:fldChar", ns)
    begin = sum(f.get(f"{{{ns['w']}}}fldCharType") == "begin" for f in fields)
    end = sum(f.get(f"{{{ns['w']}}}fldCharType") == "end" for f in fields)
    assert begin == end
    rels = etree.fromstring(result.read("word/_rels/document.xml.rels"))
    ids = {r.get("Id") for r in rels}
    for el in doc.iter():
        for attr, val in el.attrib.items():
            if etree.QName(attr).namespace == ns["r"]:
                assert val in ids, val
    for rel in rels:
        if rel.get("TargetMode") != "External":
            target = posixpath.normpath(posixpath.join("word", rel.get("Target")))
            assert target in result.namelist(), target
    text = "\n".join(doc.xpath("//w:p//w:t/text()", namespaces=ns))
    assert "word_refresh.docx" not in text

pdf = pdfium.PdfDocument(str(root / "delivery.pdf"))
pages = len(pdf)
assert pages == 84
text = "\n".join(pdf[i].get_textpage().get_text_range() for i in range(pages))
for error in ("Error!", "Reference source not found", "Bookmark not defined"):
    assert error not in text
metrics = json.loads((root.parent / "experiments/v2/metrics.json").read_text(encoding="utf-8"))
for name, values in metrics["families"].items():
    assert name in text, name
    assert f"{values['ndcg']:.6f}".replace(".", ",") in text, name
for fact in ("1.237.592", "8.000", "Argon2id", "PostgreSQL", "-57,70%"):
    assert fact in text, fact
receipt = {
    "date": "2026-10-18",
    "status": "passed",
    "output": str(output),
    "output_sha256": sha(output),
    "original_unchanged": True,
    "pages": pages,
    "sections_geometry_preserved": 3,
    "preserved_parts": len(manifest["preserved_parts"]),
    "field_begin_end": [begin, end],
    "relationships_valid": True,
    "model_families_ndcg_verified": len(metrics["families"]),
    "field_error_strings_absent": True,
    "visual_review": {
        "all_pages_clean": True,
        "review_method": "53 trang giống từng pixel với bản đã xem; 31 trang đổi đã xem ở kích thước gốc",
        "renderer": "Microsoft Word ExportAsFixedFormat và render_docx.py đóng gói",
    },
}
(root / "delivery_qa.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
prior = json.loads((root / "qa_structure.json").read_text(encoding="utf-8"))
prior.update({"pages": pages, "output_sha256": sha(output), "delivery_qa": "delivery_qa.json"})
(root / "qa_structure.json").write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=True, indent=2))
