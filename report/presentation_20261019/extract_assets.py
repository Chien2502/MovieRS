"""Trích ảnh gốc từ báo cáo, giữ nguyên bytes và ghi nguồn ảnh."""
from pathlib import Path
from zipfile import ZipFile
import json
from PIL import Image
from lxml import etree

task=Path(__file__).resolve().parent
source=task.parents[1].parent/'sản phẩm/TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2_SoDo.docx'
out=task/'assets'
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','pic':'http://schemas.openxmlformats.org/drawingml/2006/picture','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
assets=[]
with ZipFile(source) as z:
 rels={r.get('Id'):r.get('Target') for r in etree.fromstring(z.read('word/_rels/document.xml.rels'))}
 doc=etree.fromstring(z.read('word/document.xml'))
 for draw in doc.xpath('//w:drawing',namespaces=ns):
  names=draw.xpath('.//pic:cNvPr/@name',namespaces=ns)
  ids=draw.xpath('.//a:blip/@r:embed',namespaces=ns)
  if not names or not ids:continue
  member='word/'+rels[ids[0]]
  name=Path(member).name
  (out/name).write_bytes(z.read(member))
  im=Image.open(out/name)
  assets.append({'file':name,'name':names[0],'size':im.size,'source':str(source),'member':member})
(task/'assets.json').write_text(json.dumps(assets,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(assets,ensure_ascii=True))
