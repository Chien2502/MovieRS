"""Hoàn tất phiên bản thư viện, chú thích và biểu đồ sau vòng kiểm tra."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree
import re,json,hashlib
from reportlab.graphics.shapes import Drawing,String
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium

task=Path(__file__).resolve().parent;root=task.parents[1]
output=root.parent/'sản phẩm/TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx'
font='C:/Windows/Fonts/times.ttf';pdfmetrics.registerFont(TTFont('TimesVN',font))
metrics=json.loads((root/'report/experiments/v2/metrics.json').read_text(encoding='utf-8'))['families']
ranked=sorted(metrics,key=lambda n:metrics[n]['ndcg'])
dr=Drawing(600,340);chart=HorizontalBarChart();chart.x=180;chart.y=40;chart.width=360;chart.height=260
chart.data=[[metrics[n]['ndcg'] for n in ranked]];chart.categoryAxis.categoryNames=ranked
chart.categoryAxis.labels.fontName='TimesVN';chart.categoryAxis.labels.fontSize=12
chart.valueAxis.valueMin=0;chart.valueAxis.valueMax=.32;chart.valueAxis.valueStep=.08
chart.valueAxis.labels.fontName='TimesVN';chart.valueAxis.labels.fontSize=11
chart.bars[0].fillColor=HexColor('#526879');chart.barWidth=14
dr.add(chart);dr.add(String(180,320,'NDCG@10 trên cùng 900 user và giao thức V2',fontName='TimesVN',fontSize=15))
dr.add(String(180,13,'Nguồn metrics.json  MostPopular 0,280358  AdaptiveHybrid 0,118589',fontName='TimesVN',fontSize=10))
chart_path=task/'assets/ranking-comparison.png';old=hashlib.sha256(chart_path.read_bytes()).hexdigest()
pdfpath=task/'assets/ranking-comparison.pdf';renderPDF.drawToFile(dr,str(pdfpath));pdf=pdfium.PdfDocument(pdfpath)
pdf[0].render(scale=3).to_pil().save(chart_path);new=chart_path.read_bytes()
lock=(root/'mobile_app/pubspec.lock').read_text()
versions={}
for name in ['http','shared_preferences','cached_network_image','flutter_rating_bar','cupertino_icons','flutter_lints']:
    m=re.search(r'^  '+name+r':\n(.*?)(?=^  \w|^sdks:)',lock,re.M|re.S)
    versions[name]=re.search(r'    version: "([^"]+)"',m[1])[1]
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ns={'w':W,'a':'http://schemas.openxmlformats.org/drawingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
for file in [output,task/'word_refresh.docx']:
    with ZipFile(file) as z:parts={n:z.read(n) for n in z.namelist()}
    changed_members=[]
    for n,data in list(parts.items()):
        if n.startswith('word/media/') and hashlib.sha256(data).hexdigest()==old:parts[n]=new;changed_members.append(n)
    rels=etree.fromstring(parts['word/_rels/document.xml.rels'])
    image_ids={e.get('Id') for e in rels if 'word/'+e.get('Target','') in changed_members}
    doc=etree.fromstring(parts['word/document.xml'])
    for drawing in doc.xpath('//w:drawing',namespaces=ns):
        if not any(e.get('{'+R+'}embed') in image_ids for e in drawing.xpath('.//a:blip',namespaces=ns)):continue
        for ext in drawing.xpath('.//wp:extent|.//a:xfrm/a:ext',namespaces=ns):
            ext.set('cy',str(round(int(ext.get('cx'))*340/600)))
    for p in doc.xpath('//w:p',namespaces=ns):
        text=''.join(p.xpath('.//w:t/text()',namespaces=ns))
        if 'Trang chủ (2)' in text and p.xpath('.//w:instrText[contains(.,"SEQ")]',namespaces=ns):
            for t in p.xpath('.//w:t',namespaces=ns):
                if t.text==' của nguyên mẫu trước refactor':t.text=' V1'
    for table in doc.xpath('./w:body/w:tbl',namespaces=ns):
        for row in table.xpath('./w:tr',namespaces=ns):
            cells=row.xpath('./w:tc',namespaces=ns)
            if len(cells)<2:continue
            name=''.join(cells[0].xpath('.//w:t/text()',namespaces=ns))
            if name in versions:
                ts=cells[1].xpath('.//w:t',namespaces=ns);ts[0].text=versions[name]
                for t in ts[1:]:t.text=''
            if name=='Framework' and len(cells)==4 and ''.join(cells[1].xpath('.//w:t/text()',namespaces=ns))=='Flutter':
                ts=cells[2].xpath('.//w:t',namespaces=ns);ts[0].text='3.38.7 stable; đối chiếu 18/10/2026'
                for t in ts[1:]:t.text=''
            if name=='Ngôn ngữ' and len(cells)==4 and ''.join(cells[1].xpath('.//w:t/text()',namespaces=ns))=='Dart':
                ts=cells[2].xpath('.//w:t',namespaces=ns);ts[0].text='SDK 3.10.7; pubspec ^3.10.7'
                for t in ts[1:]:t.text=''
    # Sửa khoảng trắng ở các số liệu diễn giải, giữ nguyên ID, hash và công thức.
    fixes={'budget2 GiB':'budget 2 GiB','cả12 family':'cả 12 family','ngoài925':'ngoài 925','Seed42':'Seed 42','seed42/43/44':'seed 42/43/44','MostPopular64.134':'MostPopular 64.134','hybrid16,08':'hybrid 16,08','kiểm tra20':'kiểm tra 20','ngày16/10':'ngày 16/10','và100 source hashes':'và 100 source hashes','catalog62.423':'catalog 62.423','Khoảng75,29':'Khoảng 75,29','khoảng7,30':'khoảng 7,30','RMSE0,955751':'RMSE 0,955751','NDCG0,027047':'NDCG 0,027047','NDCG0,280358':'NDCG 0,280358','thành0':'thành 0','đọc200':'đọc 200','auth401':'auth 401','reload403':'reload 403','joblib nén mức3':'joblib nén mức 3'}
    for t in doc.xpath('//w:t',namespaces=ns):
        if t.text:
            for a,b in fixes.items():t.text=t.text.replace(a,b)
    parts['word/document.xml']=etree.tostring(doc,xml_declaration=True,encoding='UTF-8',standalone=True)
    with ZipFile(file,'w',ZIP_DEFLATED) as z:
        for n,data in parts.items():z.writestr(n,data)
print('Đã đối chiếu version Flutter/pubspec.lock, rút caption20 và cân lại kích thước biểu đồ')
