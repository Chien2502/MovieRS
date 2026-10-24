"""Đối chiếu nội dung PPTX và sao chép bản cuối đã nghiệm thu."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from PIL import Image,ImageChops
import hashlib,json,shutil

task=Path(__file__).resolve().parent
root=task.parents[1]
pptx=task/'output/MovieRS_ThuyetTrinh_NguyenThanhChien_v2.pptx'
receipt=json.loads((task/'build/validation-v2.json').read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(pptx)==receipt['finalSha256']
assert receipt['packageIntegrity']['status']=='pass'
assert receipt['nativeChartValidation']['passed']
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
with ZipFile(pptx) as z:
 assert z.testzip() is None
 slide_parts=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml') and '/_rels/' not in n]
 assert len(slide_parts)==22
 texts=[]
 for i in range(1,23):
  doc=etree.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
  texts.append('\n'.join(doc.xpath('//a:t/text()',namespaces=ns)))
  notes=etree.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))
  assert 'Nguồn:' in ''.join(notes.xpath('//a:t/text()',namespaces=ns))
 assert all(s in texts[0] for s in ['Nguyễn Thanh Chiến','24ITE020','24GITe','Trần Uyên Trang'])
 assert all(s in texts[1] for s in ['Tổng quan','Đối tượng nghiên cứu','Công nghệ sử dụng','Phân tích thiết kế','Sản phẩm'])
 assert 'Ảnh V1' in texts[14]
 assert '−57,70%' in texts[16]
 chart_parts=[n for n in z.namelist() if n.endswith('.xml') and '/charts/chart' in n and '/_rels/' not in n]
 assert len(chart_parts)==1
 chart=etree.fromstring(z.read(chart_parts[0]))
 cats=chart.xpath('//c:ser/c:cat//c:pt/c:v/text()',namespaces=ns)
 vals=[float(v) for v in chart.xpath('//c:ser/c:val//c:pt/c:v/text()',namespaces=ns)]
 metrics=json.loads((root/'report/experiments/v2/metrics.json').read_text(encoding='utf-8'))['families']
 assert len(cats)==len(vals)==len(metrics)==12
 assert all(abs(v-round(metrics[c]['ndcg'],6))<1e-12 for c,v in zip(cats,vals))
 for i in [18,20]:
  doc=etree.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
  assert doc.xpath('//a:tbl',namespaces=ns)

different=[]
for i in range(1,23):
 name=f'slide-{i:02}.png'
 new=Image.open(task/'build/powerpoint_final'/name).convert('RGB')
 prev=Image.open(task/'build/powerpoint_preview'/name).convert('RGB')
 assert new.size==(1280,720)
 if ImageChops.difference(new,prev).getbbox():different.append(i)
assert different==[14],different
destination=root.parent/'sản phẩm/MovieRS_ThuyetTrinh_NguyenThanhChien_24ITE020.pptx'
if destination.exists() and sha(destination)!=sha(pptx):
 destination=destination.with_stem(destination.stem+'_20261019')
 assert not destination.exists() or sha(destination)==sha(pptx)
shutil.copyfile(pptx,destination)
assert sha(destination)==sha(pptx)
qa={'date':'2026-10-19','status':'passed','output':str(destination),'sha256':sha(destination),'slides':22,'native_charts':1,'native_tables':2,'chart_values_verified':12,'speaker_notes_with_sources':22,'powerpoint_export_inspected_all_slides':True,'latest_changed_slide_reinspected':14,'runtime_or_database_changes':False}
(task/'delivery_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(qa,ensure_ascii=True))
