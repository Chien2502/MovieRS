"""Nhập cached fields của Word, giữ các package part gốc ngoài document.xml."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree
import hashlib,json,posixpath

task=Path(__file__).resolve().parent
output=task.parents[1].parent/'sản phẩm/TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx'
with ZipFile(output) as z:base={n:z.read(n) for n in z.namelist()}
with ZipFile(task/'word_refresh.docx') as z:word={n:z.read(n) for n in z.namelist()}
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
rels_a=etree.fromstring(base['word/_rels/document.xml.rels'])
rels_b={r.get('Id'):r for r in etree.fromstring(word['word/_rels/document.xml.rels'])}
root=etree.fromstring(word['word/document.xml'])
def member(target):return posixpath.normpath('word/'+target)
def digest(data):return hashlib.sha256(data).hexdigest()
for e in root.iter():
    for attr,value in list(e.attrib.items()):
        if not attr.startswith('{'+R+'}'):continue
        rel=rels_b[value];kind=rel.get('Type');target=rel.get('Target')
        if kind.endswith('/hyperlink') and 'word_refresh.docx' in target and e.get('{'+W+'}anchor'):
            del e.attrib[attr];continue
        choices=[]
        for original in rels_a:
            if original.get('Type')!=kind:continue
            if kind.endswith('/image'):
                a=base.get(member(original.get('Target')));b=word.get(member(target))
                if a is not None and b is not None and digest(a)==digest(b):choices.append(original)
            elif original.get('Target')==target:choices.append(original)
        if not choices:raise ValueError('Không ánh xạ được relationship '+value+' '+kind+' '+target)
        e.set(attr,choices[0].get('Id'))
base['word/document.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(output,'w',ZIP_DEFLATED) as z:
    for n,data in base.items():z.writestr(n,data)
manifest=json.loads((task/'build_manifest.json').read_text(encoding='utf-8'))
source=Path('D:/Users/BT/N3_K1/ThucTapThucTe/sản phẩm/TTTT_NguyenThanhChien_24ITE020.docx')
with ZipFile(source) as z:
    assert all(base[n]==z.read(n) for n in manifest['preserved_parts'])
manifest['field_refresh']='Word update; imported document.xml with relationship IDs rebased to preserved package'
manifest['preserve_only_parts_verified']=len(manifest['preserved_parts'])
manifest['output_sha256']=digest(output.read_bytes())
(task/'final_package_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'preserved_parts':len(manifest['preserved_parts']),'output':str(output)},ensure_ascii=False))
