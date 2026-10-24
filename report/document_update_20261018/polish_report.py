"""Sửa quan hệ sơ đồ và cột bảng sau kiểm tra bản render."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree
from PIL import Image,ImageDraw,ImageFont
import hashlib,math

task=Path(__file__).resolve().parent;assets=task/'assets'
output=task.parents[1].parent/'sản phẩm/TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx'
font='C:/Windows/Fonts/times.ttf'
def box(draw,rect,text,size=42):
    draw.rounded_rectangle(rect,radius=10,outline='#333333',width=3,fill='white')
    f=ImageFont.truetype(font,size);lines=text.split('\n');y=(rect[1]+rect[3]-len(lines)*size*1.2)/2
    for line in lines:draw.text(((rect[0]+rect[2]-draw.textlength(line,font=f))/2,y),line,font=f,fill='black');y+=size*1.2
def arrow(draw,a,b):
    draw.line([a,b],fill='#333333',width=4);ang=math.atan2(b[1]-a[1],b[0]-a[0]);l=18
    draw.polygon([b,(b[0]-l*math.cos(ang-.5),b[1]-l*math.sin(ang-.5)),(b[0]-l*math.cos(ang+.5),b[1]-l*math.sin(ang+.5))],fill='#333333')
new={}
im=Image.new('RGB',(1600,1600),'white');d=ImageDraw.Draw(im)
for y,text in [(180,'Người dùng\nFlutter'),(680,'Người nghiên cứu\nvà vận hành'),(1180,'Worker hệ thống\nCLI ngoài API')]:box(d,(30,y,430,y+230),text,40)
for y,text in [(100,'Tài khoản, phiên và ownership'),(400,'Catalog, tìm kiếm và khuyến nghị'),(700,'Sao, favorite và player mô phỏng'),(1000,'Audit, benchmark, CI và giải thích'),(1300,'Worker, gate, reload và rollback')]:box(d,(650,y,1560,y+180),text)
for a,b in [(295,190),(295,490),(295,790),(795,1090),(880,1350),(1295,1390)]:arrow(d,(430,a),(650,b))
new[1]=im
im=Image.new('RGB',(1600,1600),'white');d=ImageDraw.Draw(im)
for r,t in [((30,40,750,430),'ApiService Flutter\n_request, bearer, idempotency\nphiên, lỗi và progress'),((850,40,1570,430),'FastAPI routes + security\nauth, ownership, validation\nđiều phối nghiệp vụ'),((30,600,750,1000),'RecommenderService\nsnapshot + cache\nscore bundle và genre rerank'),((850,600,1570,1000),'PostgresRepository\nuser, session, feedback, favorite\nprogress và ledger transaction'),((30,1160,750,1550),'RankingModel\nfit, score_items, save / load\nsupports_rating_prediction'),((850,1160,1570,1550),'ServingWorker\nvalidation gate và bundle\npointer atomic và rollback')]:box(d,r,t)
for a,b in [((750,220),(850,220)),((850,350),(750,650)),((1210,430),(1210,600)),((750,800),(850,800)),((400,1000),(400,1160)),((850,1350),(750,1350))]:arrow(d,a,b)
new[2]=im
im=Image.new('RGB',(1600,1600),'white');d=ImageDraw.Draw(im)
for r,t in [((30,40,650,360),'app_users\nPK user_id\nusername, hash, genres'),((950,40,1570,360),'movies\nPK movie_id\ntitle, genres, metadata'),((30,560,650,880),'sessions\nPK token_hash\nFK user_id, expires_at'),((950,560,1570,880),'feedback\nPK user_id + movie_id\nhai FK, rating, source'),((30,1080,650,1400),'idempotency_keys\nPK user_id + key_hash\nFK user_id, payload_hash'),((950,1080,1570,1400),'favorites / watch_progress\nPK user_id + movie_id\nhai FK tới user và movie')]:box(d,r,t,41)
arrow(d,(340,360),(340,560))
# Đường thẳng ngoài cột, không vẽ quan hệ giả giữa các bảng con.
d.line([(150,360),(150,450),(5,450),(5,1240)],fill='#333333',width=4);arrow(d,(5,1240),(30,1240))
arrow(d,(650,240),(950,650))
d.line([(650,280),(800,460),(800,1240)],fill='#333333',width=4);arrow(d,(800,1240),(950,1240))
arrow(d,(1260,360),(1260,560))
d.line([(1470,360),(1590,450),(1590,1240)],fill='#333333',width=4);arrow(d,(1590,1240),(1570,1240))
d.text((60,1470),'Mũi tên từ bảng cha tới bảng con quan hệ 1 nhiều; schema_version độc lập.',font=ImageFont.truetype(font,34),fill='black')
new[3]=im
def hashb(b):return hashlib.sha256(b).hexdigest()
replacement={}
for n,im in new.items():
    path=assets/f'diagram-{n}.png';old=hashb(path.read_bytes());im.save(path);replacement[old]=path.read_bytes()
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';ns={'w':W}
for file in [output,task/'word_refresh.docx']:
    with ZipFile(file) as z:parts={n:z.read(n) for n in z.namelist()}
    for n,data in list(parts.items()):
        if n.startswith('word/media/') and hashb(data) in replacement:parts[n]=replacement[hashb(data)]
    root=etree.fromstring(parts['word/document.xml']);tables=root.xpath('./w:body/w:tbl',namespaces=ns)
    # Bảng có cột số thứ tự đủ rộng để 10–16 không bị tách chữ số.
    for idx,widths in [(1,[1,3.1,7.8,4.1]),(2,[1,3.5,2.4,9.1]),(3,[1,1.9,6.5,6.6])]:
        table=tables[idx]
        for col,width in zip(table.xpath('./w:tblGrid/w:gridCol',namespaces=ns),widths):col.set('{'+W+'}w',str(round(width*567)))
        for ri,row in enumerate(table.xpath('./w:tr',namespaces=ns)):
            for ci,(cell,width) in enumerate(zip(row.xpath('./w:tc',namespaces=ns),widths)):
                tcw=cell.find('w:tcPr/w:tcW',namespaces=ns);tcw.set('{'+W+'}w',str(round(width*567)))
                if ri==0 and (ci==0 or (idx==3 and ci==1)):
                    texts=cell.xpath('.//w:t',namespaces=ns);texts[0].text='#' if ci==0 else 'HTTP'
                    for t in texts[1:]:t.text=''
    for p in root.xpath('./w:body/w:p',namespaces=ns):
        text=''.join(p.xpath('.//w:t/text()',namespaces=ns))
        if text.startswith('Biểu đồ lớp dưới đây định nghĩa'):
            ts=p.xpath('.//w:t',namespaces=ns);ts[0].text='Biểu đồ lớp ở mức khái niệm tập trung vào các adapter, service và hợp đồng model đang triển khai. Mũi tên biểu thị phụ thuộc lời gọi; quan hệ giữa các bảng dữ liệu được trình bày trong ERD.'
            for t in ts[1:]:t.text=''
    parts['word/document.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    with ZipFile(file,'w',ZIP_DEFLATED) as z:
        for n,data in parts.items():z.writestr(n,data)
print('Đã sửa quan hệ cha con ERD, phụ thuộc service và độ rộng cột API')
