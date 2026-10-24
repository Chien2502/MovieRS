"""Cập nhật bản sao báo cáo theo template gốc, đối chiếu artifacts MovieRS V2."""
from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile,ZIP_DEFLATED
from io import BytesIO
import json,hashlib,math,re,textwrap
from lxml import etree
from PIL import Image,ImageDraw,ImageFont
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

ROOT=Path(__file__).resolve().parents[2]
TASK=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'sản phẩm/TTTT_NguyenThanhChien_24ITE020.docx'
OUTPUT=SOURCE.with_name('TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx')
ASSETS=TASK/'assets';ASSETS.mkdir(exist_ok=True)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='7ca70fec0c1044f50d0bdeca00dea56619d7b8eb3f9e1790088baadb778757ab'
doc=Document(SOURCE);P=list(doc.paragraphs);T=list(doc.tables)
changes=[]

def settext(p,text):
    fmt=deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
    for child in list(p._p):
        if child.tag!=qn('w:pPr'):p._p.remove(child)
    r=p.add_run(text)
    if fmt is not None:r._r.insert(0,fmt)
    r.font.color.rgb=RGBColor(0,0,0)
    return p

def replace(i,text):
    changes.append({'paragraph':i,'old':P[i].text,'new':text});settext(P[i],text)
    if P[i].style.name in {'Normal','List Paragraph'}:
        for r in P[i].runs:r.bold=False;r.italic=False

def before(anchor,text,style='Normal'):
    template=P[130] if style=='Normal' else P[{'Heading 2':359,'Heading 3':361,'Heading 4':498,'Caption':487}.get(style,130)]
    e=deepcopy(template._p)
    for x in list(e):
        if x.tag!=qn('w:pPr'):e.remove(x)
    # Không nhân bản bookmark, số nhận dạng hoặc page break của template.
    for x in e.xpath('.//w:sectPr|.//w:pageBreakBefore|.//w:numPr'):
        x.getparent().remove(x)
    anchor._p.addprevious(e)
    p=Paragraph(e,anchor._parent);p.style=style;settext(p,text)
    p.paragraph_format.keep_with_next=style.startswith('Heading')
    p.paragraph_format.keep_together=style!='Normal'
    p.paragraph_format.space_before=Pt(10 if style.startswith('Heading') else 0)
    p.paragraph_format.space_after=Pt(6)
    if style=='Normal':
        p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
        for r in p.runs:r.font.name='Times New Roman';r.font.size=Pt(13)
    return p

def section(anchor,title,paras,level=2):
    before(anchor,title,f'Heading {level}')
    for text in paras:before(anchor,text)

def table_style(table,widths=None):
    table.alignment=WD_TABLE_ALIGNMENT.CENTER
    table.autofit=False
    if widths:
        for col,w in zip(table.columns,widths):col.width=Cm(w)
    pr=table._tbl.tblPr
    borders=pr.find(qn('w:tblBorders'))
    if borders is None:borders=OxmlElement('w:tblBorders');pr.append(borders)
    for side in ['top','left','bottom','right','insideH','insideV']:
        el=OxmlElement('w:'+side);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'6');el.set(qn('w:color'),'D9D9D9');borders.append(el)
    margins=OxmlElement('w:tblCellMar')
    for side in ['top','left','bottom','right']:
        el=OxmlElement('w:'+side);el.set(qn('w:w'),'85');el.set(qn('w:type'),'dxa');margins.append(el)
    pr.append(margins)
    for ri,row in enumerate(table.rows):
        trpr=row._tr.get_or_add_trPr()
        for height in list(trpr.findall(qn('w:trHeight'))):trpr.remove(height)
        trpr.append(OxmlElement('w:cantSplit'))
        if ri==0:trpr.append(OxmlElement('w:tblHeader'))
        for ci,c in enumerate(row.cells):
            if widths and ci<len(widths):c.width=Cm(widths[ci])
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=c._tc.get_or_add_tcPr()
            for old in list(tcpr.findall(qn('w:shd'))):tcpr.remove(old)
            sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E7E6E6' if ri==0 else 'FFFFFF');tcpr.append(sh)
            for p in c.paragraphs:
                p.paragraph_format.keep_with_next=False;p.paragraph_format.keep_together=True
                p.paragraph_format.first_line_indent=Cm(0)
                p.paragraph_format.space_before=Pt(2);p.paragraph_format.space_after=Pt(3)
                p.paragraph_format.line_spacing=1.05
                p.alignment=WD_ALIGN_PARAGRAPH.CENTER if ri==0 else WD_ALIGN_PARAGRAPH.LEFT
                for r in p.runs:
                    r.font.name='Times New Roman';r.font.size=Pt(11.5);r.font.bold=ri==0;r.font.color.rgb=RGBColor(0,0,0)

def fill_table(table,rows,widths=None):
    while len(table.rows)>len(rows):table._tbl.remove(table.rows[-1]._tr)
    while len(table.rows)<len(rows):table.add_row()
    for row,values in zip(table.rows,rows):
        for cell,text in zip(row.cells,values):cell.text=str(text)
    table_style(table,widths)

def addtable(anchor,headers,rows,widths=None):
    t=doc.add_table(rows=1,cols=len(headers))
    anchor._p.addprevious(t._tbl)
    fill_table(t,[headers,*rows],widths or [16/len(headers)]*len(headers))
    before(anchor,'')
    return t

def mathpara(anchor,text):
    p=before(anchor,'');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    m=OxmlElement('m:oMath');r=OxmlElement('m:r');v=OxmlElement('m:t');v.text=text;r.append(v);m.append(r);p._p.append(m)

# Sửa nội dung theo đúng vị trí nguồn, giữ hệ đề mục của báo cáo.
replacements={
43:'Báo cáo thực tập được thực hiện tại Trường Đại học Công nghệ thông tin và Truyền thông Việt Hàn, dưới sự hướng dẫn của TS. Trần Uyên Trang.',
45:'Em xin cảm ơn các Thầy, Cô trong trường đã tạo điều kiện học tập và cung cấp kiến thức nền tảng để em nghiên cứu, xây dựng và kiểm chứng đề tài trong kỳ thực tập.',
46:'Em xin cảm ơn Công ty FPT Software đã tạo điều kiện thực tập; cảm ơn các bạn đã chia sẻ tài liệu và kinh nghiệm trong quá trình thực hiện đề tài.',
47:'Do thời gian và kinh nghiệm thực tiễn còn hạn chế, báo cáo có thể còn thiếu sót. Em mong nhận được góp ý của giảng viên và đơn vị thực tập để tiếp tục hoàn thiện.',
130:'Danh mục phim lớn làm tăng nhu cầu lựa chọn nội dung phù hợp cho từng người dùng. Hệ khuyến nghị hỗ trợ sắp xếp một danh sách ngắn từ tập ứng viên, nhưng chất lượng của danh sách phải được kiểm tra bằng dữ liệu, baseline và giao thức đánh giá rõ ràng. Đề tài MovieRS kết hợp nghiên cứu thuật toán với xây dựng nguyên mẫu ứng dụng để kiểm chứng luồng dữ liệu và cách phục vụ khuyến nghị.',
132:'Dữ liệu thưa: người dùng chỉ đánh giá một phần nhỏ catalog. Độ thưa phải gắn với tập user và tập phim dùng làm mẫu số; không dùng một tỷ lệ chung cho mọi phiên bản dữ liệu. Mẫu V2 có 8.000 user, 27.498 phim được đánh giá và 1.237.592 rating, tương ứng độ thưa khoảng 99,4374% trên ma trận này.',
135:'Khoảng cách giữa nghiên cứu và vận hành: điểm offline có thể bị lệch nếu trộn feedback mới vào holdout hoặc chọn model bằng TEST. MovieRS tách snapshot nghiên cứu bất biến khỏi PostgreSQL runtime; việc fit, đánh giá, đóng gói và rollback được lưu thành artifact có nguồn gốc.',
136:'Đề tài giữ tên “Tìm hiểu hệ thống khuyến nghị sử dụng phương pháp lai và xây dựng nguyên mẫu ứng dụng phim ảnh”. Trọng tâm sau refactor là đánh giá hybrid theo độ dài lịch sử trên mẫu ML-25M vừa sức máy, so sánh công bằng và xây dựng luồng ứng dụng nhất quán. Kết quả không mặc định hybrid tốt hơn baseline.',
139:'Về thuật toán: triển khai GlobalMean, regularized bias, MostPopular, Bayesian item mean, genre content, ItemKNN sparse, BiasedSVD và các biến thể hybrid. Phân biệt dự đoán rating với xếp hạng Top-K; kiểm tra lợi ích của trọng số thích ứng, genre, cold fallback và MMR bằng đối chứng riêng.',
140:'Về phần mềm: xây dựng FastAPI, Flutter, dashboard nghiên cứu Streamlit và PostgreSQL trên Supabase. API quản lý phiên và quyền sở hữu; cache và model snapshot phục vụ suy luận. Trình phát giữ mô phỏng, không nối dịch vụ video thật.',
141:'Về vòng đời mô hình: tổ chức luồng raw → audit → sample → split → fit TRAIN → chọn VAL → khóa cấu hình → refit TRAIN+VAL → TEST → artifact. Luồng serving dùng worker riêng, validation gate và con trỏ phiên bản; không chạy retrain nền trong API.',
142:'Cổng promotion chấm lại incumbent và candidate trên cùng validation, kiểm tra NDCG, cohort, latency và RMSE khi cả hai hỗ trợ dự đoán rating. Không dùng TEST để chọn model hoặc nới gate nhằm hợp thức hóa một phiên bản.',
143:'Về cold-start: nghiên cứu fallback bằng thống kê dữ liệu đã biết; ứng dụng có onboarding thể loại và rerank. Không suy ra sở thích onboarding từ nhãn TEST. Model đang phục vụ được chọn từ VAL, hiện là MostPopular; không tự chuyển thành SVD sau một số tương tác cố định.',
147:'Mô hình BiasedSVD biểu diễn user và phim bằng vector ẩn và bias; công thức dự đoán được giữ dưới đây. Trong dự án, implementation chuẩn là Surprise SVD, học bằng SGD có regularization, không phải phép phân rã đại số trực tiếp của một ma trận đã điền đầy [4].',
149:'Trong công thức, μ là trung bình trên dữ liệu fit, b_u và b_i là bias, p_u và q_i là vector ẩn. Tất cả được ước lượng trên TRAIN khi chọn tham số và trên TRAIN+VAL khi chấm TEST; không fit bằng nhãn TEST.',
150:'Nguyên tắc quản lý vòng đời gồm versioning, lineage, validation gate và rollback. Đây là nguyên mẫu có kiểm thử, chưa có bằng chứng về khả năng chịu tải hoặc mức trưởng thành MLOps của một hệ thống sản xuất.',
152:'Đánh giá offline dùng cutoff thời gian toàn cục, xấp xỉ 80/10/10, giữ timestamp bằng nhau ở cùng một phía. Chọn cấu hình trên VAL trước khi mở TEST. Giao thức giảm những dạng rò rỉ đã kiểm tra, không khẳng định loại bỏ mọi sai lệch của dữ liệu hồi cứu [6].',
155:'Thuộc tính danh sách: catalog coverage, genre diversity và novelty; các proxy này không thay cho mức hài lòng của người dùng.',
156:'Kiểm tra vận hành tách latency scoring model, thời gian HTTP và cache. Báo cáo sử dụng số đo được lưu trong artifact và HTTP smoke; chưa coi đây là load test đa người dùng hoặc cam kết SLA.',
157:'Kiểm thử luồng tích hợp gồm đăng ký/đăng nhập, ownership, đánh giá, favorite, watch progress, retry, rollback và hết phiên. Kiểm thử chứng minh các hợp đồng kỹ thuật; chưa chứng minh mức tăng hài lòng hoặc cá nhân hóa qua A/B test.',
159:'Phát triển theo các pha có phụ thuộc: cấu hình/môi trường, dữ liệu, evaluator, model/runner, dashboard, database/ứng dụng và nghiệm thu. Không suy diễn rằng dự án đã thực hiện Scrum hoặc bốn sprint khi không có hồ sơ tương ứng.',
163:'Nguồn nghiên cứu là ML-25M do GroupLens công bố: 25.000.095 rating từ 162.541 user; catalog có 62.423 phim, trong đó 59.047 phim có rating. Nguồn yêu cầu user có tối thiểu 20 rating và không cung cấp nhân khẩu học [2].',
164:'V2 quét toàn nguồn và chọn 8.000 user theo thứ tự SHA256 của “20261015:userId”, giữ toàn bộ lịch sử. Mẫu có 1.237.592 rating; không lấy 2 triệu rating mới nhất và không lọc phim dưới 50 rating. Catalog ứng dụng giữ 62.423 phim, kể cả phim thiếu enrichment TMDb.',
166:'Phạm vi gồm baseline thống kê, content theo genre, ItemKNN sparse và factorization có bias; hybrid kết hợp điểm chuẩn hóa. Chưa triển khai BPR/ALS hoặc mô hình học sâu trong kết quả xác nhận.',
167:'Surprise được dùng với siêu tham số chọn trên VAL và ba seed huấn luyện. Kết quả là benchmark offline và nguyên mẫu serving, chưa được gọi là triển khai production đã kiểm chứng.',
169:'Backend chạy local; tunnel Ngrok là tùy chọn khi cần truy cập từ thiết bị khác. URL mobile cấu hình bằng AppConfig hoặc --dart-define=API_URL, không lấy từ .env backend.',
173:'Nguồn dữ liệu và giới hạn sử dụng được ghi riêng. ML-25M tuân theo điều kiện nghiên cứu của GroupLens; metadata TMDb phục vụ hiển thị và không đồng nghĩa quyền phân phối video [2].',
179:'tags.csv và các file genome có trong nguồn nhưng không được dùng làm feature của benchmark V2; tránh mô tả chúng như thành phần đã huấn luyện.',
185:'Snapshot nghiên cứu lưu ratings/train/validation/test/movies dạng Parquet cùng user IDs, manifest, quality và data card tại data/snapshots/<dataset_id>. CSV processed cũ được giữ cho đối chiếu V1 và metadata ứng dụng.',
186:'Split V2 cố định T1=2016-07-25T17:31:14Z và T2=2018-01-23T19:51:49Z; tương ứng 990.073 TRAIN, 123.759 VAL và 123.760 TEST.',
187:'Dữ liệu vận hành nằm trong schema moviers của PostgreSQL. interactions_log.csv là nguồn prototype được backup/import; feedback ứng dụng chỉ tham gia fit serving, không tham gia holdout nghiên cứu.',
189:'Run nghiên cứu nằm trong artifacts/runs/<run_id>; model phục vụ nằm trong artifacts/serving/<version>/model.joblib. current.json là con trỏ nguyên tử đến manifest đã kiểm checksum.',
190:'Manifest lưu dataset/protocol/config/code/environment hashes, selection và resource budget; metrics/per-user/comparisons phục vụ kiểm chứng. models/model_latest.pkl và metadata V1 được giữ làm lịch sử, không là entrypoint serving V2.',
195:'Nội dung 3: triển khai và đối chứng 12 họ mô hình/biến thể. Đo RMSE/MAE cho model rating và NDCG/Recall/Precision cùng coverage/diversity/novelty cho ranking; phân tích cohort và CI ghép cặp.',
197:'Nội dung 5: PostgreSQL, xác thực, feedback có nguồn, idempotency, worker serving riêng, validation gate và rollback. Luồng research không bị ứng dụng sửa holdout; dữ liệu nhập được đối soát và nguồn cũ được bảo toàn.',
211:'FPT hoạt động trong các lĩnh vực công nghệ, viễn thông và giáo dục. Phần giới thiệu đơn vị cung cấp bối cảnh thực tập, còn số liệu thực nghiệm MovieRS được trình bày riêng trong chương cài đặt và kết quả [1].',
221:'Định hướng công nghệ trong bối cảnh đề tài',
222:'Các lĩnh vực AI, dữ liệu và nền tảng đám mây tạo bối cảnh phù hợp cho đề tài. MovieRS vận dụng các kỹ thuật ở phạm vi nguyên mẫu, từ xử lý dữ liệu đến cung cấp API và kiểm chứng kết quả.',
226:'FPT Software tổ chức mạng lưới nhân sự và trung tâm phát triển tại nhiều thị trường, hỗ trợ phối hợp các nhóm kỹ thuật và khách hàng trong mô hình bàn giao toàn cầu [1].',
242:'Trong phạm vi thực tập, MovieRS là bài tập nghiên cứu và xây dựng nguyên mẫu. Việc quản lý dữ liệu, đánh giá mô hình và kiểm thử phần mềm giúp rèn luyện kỹ năng liên quan đến kỹ thuật dữ liệu và AI.',
243:'Đề tài gắn với các năng lực về dữ liệu và phát triển ứng dụng của môi trường thực tập. Tuy nhiên, pipeline của sinh viên không được mô tả như quy trình nội bộ hoặc hệ thống sản xuất của FPT Software.',
253:'AI và dữ liệu mở rộng khả năng xây dựng giải pháp phần mềm. Trong phạm vi thực tập, đề tài tiếp cận các năng lực này qua xử lý dữ liệu, mô hình khuyến nghị và kiểm thử tính nhất quán.',
259:'Phát triển nguồn nhân lực công nghệ và đào tạo liên tục tạo điều kiện để sinh viên tiếp cận kỹ năng mới, rèn luyện phối hợp công việc và tư duy giải quyết vấn đề.',
282:'Phát triển linh hoạt tổ chức công việc theo vòng lặp ngắn, tiếp nhận phản hồi và điều chỉnh theo kết quả kiểm tra. Trong đề tài, các pha kỹ thuật được triển khai theo phụ thuộc và có tiêu chí nghiệm thu.',
314:'Các công cụ hỗ trợ lập trình bằng AI có thể hỗ trợ viết mã, tạo kiểm thử và rà soát. Chất lượng đầu ra vẫn cần được kiểm tra bằng quy tắc kỹ thuật và các trường hợp thực tế của dự án.',
332:'Khuyến nghị là một thành phần hỗ trợ khám phá nội dung. Đề tài chỉ đo chất lượng offline và hợp đồng phần mềm; chưa đo retention, doanh thu hay quan hệ nhân quả với hành vi sử dụng.',
337:'Độ trễ giữa feedback và model batch là một đánh đổi thiết kế. MovieRS ghi dữ liệu và làm mới cache sau commit; việc huấn luyện lại chạy bằng worker thủ công để kiểm soát tài nguyên, không cam kết model học ngay mọi thay đổi sở thích.',
341:'Hiệu ứng đuôi dài thể hiện sự không đồng đều của số tương tác giữa phim. Phân phối này được kiểm tra trên rating đã có; không gọi số rating là số lượt xem thực tế.',
344:'Thiếu versioning và đối soát có thể làm kết quả khó tái lập. V2 dùng snapshot/manifest, selection khóa trước TEST, source archive, gate và rollback; chưa có hệ thống giám sát drift hoặc CI/CD production.',
352:'Giải pháp sắp xếp phim chưa tương tác dựa trên model được chọn và sở thích ứng dụng. Mức phù hợp là giả thuyết cần đo, không đồng nghĩa hệ thống tự hiểu chính xác sở thích của người dùng.',
354:'Giải pháp được lựa chọn để kiểm chứng các bài toán sau ở quy mô nguyên mẫu:',
355:'Hỗ trợ khám phá nội dung: rút gọn catalog thành danh sách Top-K có lý do hiển thị. Lợi ích về mức hài lòng hoặc giữ chân người dùng cần đánh giá trực tuyến riêng.',
364:'Regularization hạn chế độ lớn tham số và hỗ trợ kiểm soát overfitting. Khả năng khuyến nghị phim ít phổ biến phải được đo bằng baseline, cohort và coverage, không suy ra chỉ từ việc dùng factorization.',
366:'Hybrid nghiên cứu dùng trọng số theo lịch sử; cold user dùng fallback từ dữ liệu fit. Luồng onboarding của ứng dụng là chức năng riêng, chưa có nhãn onboarding trong MovieLens.',
367:'Khi đăng ký, giao diện cho chọn genre; API lưu sở thích và rerank danh sách phục vụ. Không dùng nhãn TEST để giả lập sở thích này.',
368:'Số tương tác không tự quyết định chuyển sang SVD. Bundle serving hiện chọn MostPopular từ VAL; worker mới có quyền fit và promote phiên bản khác sau khi vượt gate.',
370:'Favorite tạo proxy 4,5; xem hoàn tất từ 95% tạo watch_complete 4,0 nếu không có nguồn mạnh hơn. Xem dở không thành dislike. Explicit/legacy_unknown ưu tiên hơn favorite, và favorite ưu tiên hơn watch_complete; bỏ favorite rút proxy tương ứng.',
371:'Sau commit, cache của user được làm mất hiệu lực. Callback cập nhật online của nhánh SVD legacy chỉ có ý nghĩa khi nhánh đó được nạp; với bundle MostPopular V2 không khẳng định có bước SGD làm thay đổi vector người dùng tức thì.',
373:'Vòng đời được tách thành nghiên cứu và serving để việc thu thập phản hồi không làm thay đổi benchmark đã khóa:',
374:'Feedback runtime được đọc vào dữ liệu fit phục vụ riêng; snapshot nghiên cứu, validation và TEST không bị repartition hoặc bổ sung nhãn ứng dụng.',
375:'Worker thủ công ngoài API có khóa một job, ngân sách RAM/thời gian và trạng thái rõ ràng. API không có tiến trình auto-retrain chạy nền; scheduling là hướng mở rộng.',
376:'Gate dùng validation chung với NDCG và guardrail cohort/latency/rating phù hợp. Bundle được xác minh trước khi thay con trỏ; reload cần admin token. Cơ chế snapshot giảm rủi ro gián đoạn, không thay thế đo tải hoặc bảo đảm zero-downtime trong production.',
392:'Python được chọn nhờ thư viện xử lý dữ liệu, sparse matrix, mô hình và API. Phiên bản đã kiểm thử của dự án là Python 3.14.2 trên Windows, với dependency khóa; không suy ra tính tương thích mọi OS/Python từ lần chạy này.',
395:'Mã nguồn Python có tính di động ở mức ngôn ngữ, nhưng phụ thuộc native như Surprise và driver có thể cần bản build phù hợp. Vì vậy lock hiện tại gắn với môi trường Windows đã được kiểm chứng.',
400:'FastAPI dựa trên ASGI/Starlette và dùng Pydantic để kiểm tra dữ liệu; hiệu năng thực tế phụ thuộc workload, I/O và cách triển khai, không suy ra ưu thế tốc độ tuyệt đối từ tên framework [7].',
403:'Async/await hỗ trợ I/O bất đồng bộ; các tác vụ SQL và tính toán đồng bộ được tổ chức phù hợp. Khả năng chịu tải đồng thời cần một thí nghiệm tải riêng.',
405:'Request từ Flutter được Uvicorn tiếp nhận, qua middleware xác thực/ownership và định tuyến tới endpoint. CORS xử lý chính sách truy cập chéo nguồn của trình duyệt, không thay thế xác thực hoặc phân quyền.',
417:'Khi phát hành mobile, Dart có thể biên dịch AOT; trên web có pipeline biên dịch cho trình duyệt. Build web đã được kiểm chứng nhưng không thay cho thử nghiệm Android/iOS vật lý.',
423:'Flutter kết xuất giao diện bằng engine tương ứng nền tảng. Báo cáo không khẳng định 60–120 FPS vì chưa có phép đo hiệu năng khung hình.',
437:'V2 đọc artifact đã hoàn tất khi script rerun, không fit model hoặc gọi retrain khi mở dashboard. Cache giao diện và dữ liệu không được dùng để che việc kiểm tra checksum và tính tương thích run.',
440:'SVD trong Surprise là matrix factorization có bias học bằng SGD, thường được gọi BiasedSVD. Cần phân biệt với phép phân rã UΣVᵀ của đại số tuyến tính; dữ liệu thiếu không được điền bằng nhãn TEST [4].',
441:'Mỗi user và phim đã biết có vector ẩn. Khi một phía chưa xuất hiện trong dữ liệu fit, cách fallback của model ảnh hưởng kết quả; đây là lý do phải giữ cold user trong đánh giá.',
444:'μ là trung bình dữ liệu fit; b_u, b_i là bias; tích vô hướng giữa hai vector biểu diễn phần tương tác. Sai số rating thấp không bảo đảm ranking tốt khi cạnh tranh với toàn catalog chưa tương tác.',
447:'Khi chọn siêu tham số, Surprise fit trên 990.073 rating TRAIN. Sau khi khóa selection, từng seed refit trên 1.113.832 rating TRAIN+VAL rồi chấm cùng TEST. VAL chọn 32 factors, 15 epochs và regularization 0,02.',
448:'Trọng số được học qua các epoch SGD đã cấu hình, không khẳng định hội tụ tối ưu toàn cục. Source archive, seed, môi trường và metric được lưu để tái lập; model nghiên cứu không tự được deploy dựa trên TEST.',
473:'MovieRS gồm ứng dụng Flutter, API FastAPI, dashboard nghiên cứu và worker/pipeline riêng. PostgreSQL giữ dữ liệu ứng dụng; ML-25M, snapshot nghiên cứu và model lớn nằm ở artifact local.',
476:'Dashboard Streamlit đọc dữ liệu nguồn gốc, so sánh model/CI, ablation và trạng thái vận hành. Nó không trực tiếp kích hoạt huấn luyện; người vận hành chạy CLI worker có khóa job.',
482:'Bảng sau liệt kê các nhóm endpoint thực tế của V2 và ranh giới truy cập. Các route tương thích cũ được giữ nhưng client dùng endpoint favorite thống nhất để tránh gửi hai lần.',
494:'V2 đã tích hợp PostgreSQL trên Supabase trong schema riêng moviers. Dữ liệu tài khoản, phiên, phản hồi, favorite và watch progress có FK/unique/check; không upload toàn bộ ML-25M vào database ứng dụng.',
498:'Bảng app_users',
501:'Catalog giữ movie_id gốc, title/genre canonical và metadata TMDb khi có; thiếu enrichment không làm mất phim khỏi catalog. Điểm TMDb không là feature lịch sử của benchmark.',
502:'Bảng feedback',
503:'Mỗi cặp user–movie có một phản hồi hiệu lực và source. Đây không phải event log lưu mọi thay đổi; explicit và proxy được phân biệt trước khi đưa vào fit serving.',
508:'Registry model dạng artifact local',
509:'Registry serving nằm trong thư mục bundle/manifest và current.json, không phải bảng SQL. Dataset, validation gate, spec, checksum và previous version xác định khả năng rollback.',
571:'Backend đọc .env gốc cho secrets và môi trường runtime; pipeline nghiên cứu đọc configs/research.toml. Flutter dùng AppConfig hoặc --dart-define=API_URL, không đọc .env. Không chèn URI có mật khẩu, API key hoặc bearer token thật vào báo cáo.',
589:'Ảnh là giao diện nguyên mẫu trước refactor và chỉ minh họa bố cục. V2 dùng user_id làm khóa chính, username duy nhất không phân biệt hoa thường; mật khẩu tối thiểu 8 ký tự, băm Argon2id. Login/register cấp bearer token có hạn 12 giờ; Splash xác minh phiên với API trước khi vào ứng dụng.',
593:'Trang chủ phân biệt gợi ý theo onboarding và lịch sử đã biết. Ở V2, model đang phục vụ là MostPopular được chọn trên VAL, kết hợp rerank theo genre; lịch sử đã tương tác bị loại khỏi candidate.',
594:'Nhãn “gợi ý SVD” trong ảnh nguyên mẫu là nhãn V1, không đại diện model V2. Client hiện nhận strategy, stage, history_count, candidate_count và reason từ API; ranking score không được tự hiển thị như xác suất thích hoặc số sao dự đoán khi model chỉ ranking.',
595:'Khi sở thích hoặc feedback thay đổi, cache theo user/chế độ được invalidation sau commit. Cache tối đa 5 phút; lỗi API có trạng thái thử lại riêng, không bị đổi thành danh sách rỗng.',
596:'Không còn quy tắc “đủ 5 tương tác thì retrain nền” hoặc hai learning rate 0,15/0,005 như mô tả cũ. Worker thủ công chọn model bằng validation và giữ nguồn research tách biệt khỏi dữ liệu ứng dụng.',
600:'Tìm kiếm hỗ trợ từ khóa tên phim và bộ lọc theo API; mỗi trang mặc định tối đa 20 kết quả. Lỗi mạng và trạng thái không tìm thấy được phân biệt. Ảnh giữ để minh họa giao diện nguyên mẫu.',
604:'Favorite phục vụ danh sách lưu và đồng thời tạo proxy theo quy tắc ưu tiên. Client chỉ gửi một request; database cập nhật favorite cùng feedback trong transaction. Bỏ tim rút proxy, không ghi rating âm.',
608:'Hồ sơ hiển thị thông tin tài khoản, thể loại đã chọn và thống kê. Lịch sử đánh giá sao chỉ gồm explicit; watch_complete không được đếm như một đánh giá chủ động. Người dùng không truy cập hồ sơ của tài khoản khác.',
612:'Trang chi tiết cho phép đánh giá sao, thêm/bỏ favorite và mở player mô phỏng. Bộ đếm chạy 1 giây thực bằng 1 giây phim, gửi heartbeat mỗi 5 giây, hỗ trợ resume và xác nhận lưu khi thoát; không phát video thật.',
613:'Phản hồi explicit là số sao người dùng chủ động chọn. Favorite là hành vi do người dùng thực hiện nhưng chỉ được mô hình hóa thành proxy, không là một rating explicit.',
614:'Tiến độ xem là tín hiệu vận hành mô phỏng. Chỉ tỷ lệ từ 95% mới tạo watch_complete 4,0 nếu không có nguồn mạnh hơn; dưới ngưỡng không ghi dislike. Watch/favorite không ghi đè sao chủ động.',
617:'Đề tài đã xây dựng được quy trình nghiên cứu và nguyên mẫu ứng dụng có thể kiểm tra. Thành công của refactor được đánh giá bằng tính đúng đắn, truy vết dữ liệu và luồng vận hành; không lấy giả định hybrid phải thắng làm điều kiện kết luận.',
621:'Tổ chức vòng đời model với worker riêng, validation gate, artifact version, checksum và rollback; không khẳng định tự động hóa production hoàn toàn.',
625:'Phân biệt mục tiêu tối ưu rating và ranking; kiểm tra cold fallback, genre và trọng số bằng ablation cùng giao thức thay vì chỉ so một chỉ số RMSE.',
626:'API cung cấp catalog 62.423 phim và cache gợi ý. HTTP smoke xác nhận hợp đồng đọc và bảo toàn input; chưa có load test đủ để khẳng định latency trung bình dưới 800 ms hoặc SLA cho nhiều người dùng.',
627:'PostgreSQL đã được migration/đối soát; feedback transaction và idempotency được kiểm thử trên database thật. Worker thủ công ngoài API thực hiện fit serving, gate và reload có bảo vệ quản trị.',
628:'Dashboard nghiên cứu bảy trang đọc artifact thật, từ chối delta giữa các run khác protocol/dataset/user và hiển thị CI, cohort, chi phí cùng kết quả âm.',
634:'Giới hạn dữ liệu: mẫu user-cluster vẫn có thiên lệch MovieLens, thiếu exposure/demographic; genre là snapshot hồi cứu. Các tỷ lệ giống nguồn không chứng minh đại diện mọi khán giả.',
635:'Giới hạn mô hình: hybrid chưa vượt MostPopular; phần lợi ích so SVD thuần chưa tách được khỏi cold fallback. Chưa có bằng chứng riêng cho genre và chưa có xác nhận trên nhiều cửa sổ hoặc mẫu độc lập.',
636:'Giới hạn kiểm chứng: chưa có A/B test, khảo sát người dùng, thiết bị Android/iOS vật lý, drift monitor hay load test production. Player là mô phỏng; độ tin cậy proxy xem xong chưa được xác thực bằng hành vi xem thực.',
638:'Các hướng sau là công việc tương lai, không được mô tả như kết quả đã triển khai. Ưu tiên mở rộng bằng thí nghiệm có nguồn dữ liệu và tiêu chí xác nhận rõ ràng.',
640:'Duy trì PostgreSQL hiện có: theo dõi truy vấn/pool, kiểm thử restore từ backup và quản lý migration. Không cần lặp lại đề xuất chuyển từ CSV vì V2 đã hoàn tất cutover và diễn tập export.',
641:'Chỉ cân nhắc Redis khi đo được bottleneck hoặc triển khai nhiều process; cache in-memory hiện đủ cho demo. Mốc latency mục tiêu phải gắn với workload, tỷ lệ cache hit và kết quả đo mới.',
642:'Có thể bổ sung đóng gói/deployment và load test khi mở rộng. Các dịch vụ cloud, Docker/CI/CD và tính sẵn sàng 24/7 chưa thuộc bằng chứng của lần nghiệm thu này.',
644:'Ưu tiên mục tiêu tối ưu ranking, đối chứng BPR/ALS và cửa sổ xác nhận mới. Hybrid genre đã triển khai nhưng chưa cho thấy ưu thế chính; thêm TF-IDF/embedding là giả thuyết nghiên cứu, không bảo đảm giải quyết triệt để cold-start.',
645:'Thu thập nhãn để kiểm tra độ tin cậy proxy, mô hình hóa exposure và cân nhắc propensity/bias. Muốn tuyên bố nhiều so sánh cần đăng ký và hiệu chỉnh đa kiểm định; không điều chỉnh trọng số trên TEST hiện tại.'}
for i,text in replacements.items():replace(i,text)
replace(134,P[134].text.replace(' (Hu et al., 2008).','.'))
replace(231,P[231].text.replace('$m^2$','m²'))

# Các bảng hiện có được cập nhật, không đổi vị trí và vai trò trong dàn ý.
fill_table(T[1],[['STT','Tác nhân','Vai trò','Giao diện'],['1','Người dùng','Khám phá, chấm sao, favorite, mô phỏng xem; chỉ đọc/ghi dữ liệu của mình.','Flutter'],['2','Người nghiên cứu và vận hành','Xem benchmark/dashboard, chạy CLI, kiểm tra gate và rollback.','Streamlit và CLI'],['3','Worker hệ thống','Thực thi job có khóa sau lệnh thủ công; ghi trạng thái và bundle.','Tiến trình riêng ngoài API']],[.8,3.1,8,4.1])
features=[('Tài khoản và phiên','Người dùng','Đăng ký, login, xác minh phiên, logout; token có hạn và kiểm tra ownership.'),('Trang chủ','Người dùng','Model chọn trên VAL, onboarding rerank, loại phim đã tương tác.'),('Catalog và tìm kiếm','Người dùng','Danh sách/phổ biến/từ khóa/chi tiết từ metadata.'),('Sao explicit','Người dùng','0,5–5 sao; ưu tiên hơn proxy; idempotency khi ghi.'),('Favorite','Người dùng','Một request cập nhật danh sách và proxy trong transaction.'),('Player mô phỏng','Người dùng','Heartbeat 5 giây, resume, xem xong từ 95%, kiểm tra lỗi lưu.'),('Hồ sơ và sở thích','Người dùng','Lịch sử explicit, favorite và genre của chính tài khoản.'),('Provenance và dữ liệu','Nghiên cứu','Audit, mẫu toàn lịch sử, tính đại diện và split có hash.'),('Benchmark và CI','Nghiên cứu','Cùng candidate/user, paired bootstrap, cohort và ablation.'),('Serving job','Vận hành','Worker thủ công, khóa một job, validation gate và bundle.'),('Health và rollback','Vận hành','Kiểm tra model/database; reload có admin token, rollback có checksum.')]
fill_table(T[2],[['STT','Chức năng','Tác nhân','Mô tả'],*[[str(i+1),*r] for i,r in enumerate(features)]],[.8,3.5,2.4,9.3])
endpoints=[('POST','/api/auth/register','Tạo tài khoản và phiên; công khai'),('POST','/api/auth/login','Xác thực, cấp bearer; công khai'),('GET / POST','/api/auth/me; /api/auth/logout','Xác minh / thu hồi phiên; bearer'),('GET','/api/movies; /api/movies/popular','Catalog / thống kê phim; công khai'),('GET','/api/movies/search; /api/movies/{movie_id}','Tìm kiếm / chi tiết; công khai'),('GET','/api/recommendations/{user_id}','User app cần bearer/ownership; ID MovieLens là demo lịch sử'),('POST','/api/interactions/rating','Explicit, bearer/ownership; Idempotency-Key'),('POST','/api/users/{user_id}/favorites','Favorite và proxy cùng transaction; bearer'),('POST','/api/interactions/favorite; /api/interactions/watch','Alias tương thích; không gọi trùng endpoint chính'),('PUT','/api/watch/progress','Heartbeat/resume; bearer/ownership'),('GET','/api/watch/progress/{user_id}[/{movie_id}]','Tiến độ toàn user hoặc một phim; bearer'),('DELETE','/api/watch/progress/{user_id}/{movie_id}','Xóa tiến độ thuộc user; bearer'),('GET','/api/users/{user_id}/profile; /favorites; /ratings','Hồ sơ/favorite/lịch sử explicit; ownership'),('PUT','/api/users/{user_id}/preferences','Cập nhật genre; ownership'),('POST','/api/recommendations/reload','Yêu cầu X-Admin-Token; không là thao tác mobile'),('GET','/api/health; /api/health/database','Readiness model/catalog và database; không tạo schema')]
fill_table(T[3],[['STT','Method','Endpoint','Mục đích và truy cập'],*[[str(i+1),*r] for i,r in enumerate(endpoints)]],[.7,1.5,6.6,7.2])
fill_table(T[4],[['Trường','Kiểu','Ràng buộc','Mô tả'],['user_id','bigint','PK, identity ≥200000','Không trùng miền ID MovieLens'],['username','text','unique lower, 3–50','Tên đăng nhập không là khóa chính'],['password_hash','text','NOT NULL','Argon2id cho mật khẩu mới; legacy nâng sau login hợp lệ'],['salt','text','NOT NULL','Tương thích hash legacy; Argon2 có salt trong chuỗi mã hóa'],['genres','text[]','NOT NULL, {}','Thể loại onboarding; không suy ra từ TEST'],['created_at','timestamptz','DEFAULT now()','Dấu thời gian có múi giờ']],[3,2.1,4,6.9])
fill_table(T[5],[['Trường','Kiểu','Ràng buộc','Mô tả'],['movie_id','bigint','PK >0','ID MovieLens canonical'],['title','text','NOT NULL','Tiêu đề gốc vẫn giữ khi thiếu TMDb'],['genres','text[]','NOT NULL, {}','Mảng genre trong SQL'],['tmdb_id','bigint','nullable','ID enrichment nếu có'],['poster_path / overview','text','DEFAULT trống','Metadata hiển thị'],['vote_average / vote_count','numeric / bigint','0–10 / ≥0','Điểm cộng đồng hiển thị, không là feature benchmark'],['runtime_minutes','integer','>0, DEFAULT 100','Giá trị mặc định chỉ dùng mô phỏng'],['release_date / release_year','date / integer','nullable / 0–9999','Thông tin phát hành']],[3.7,2.5,3.4,6.4])
fill_table(T[6],[['Trường','Kiểu','Ràng buộc','Mô tả'],['user_id, movie_id','bigint','PK ghép; hai FK','Một phản hồi hiệu lực mỗi cặp'],['rating','numeric(2,1)','0,5–5,0','Giá trị explicit hoặc proxy có source'],['source','text','CHECK nguồn hợp lệ','explicit, legacy_unknown, favorite, watch, watch_complete'],['updated_at','timestamptz','DEFAULT now()','Thời điểm cập nhật hiệu lực']],[3.7,2.6,3.7,6])
fill_table(T[7],[['Trường','Kiểu','Ràng buộc','Mô tả'],['user_id, movie_id','bigint','PK ghép; hai FK','Cặp tài khoản và phim đã lưu'],['added_at','timestamptz','DEFAULT now()','Favorite và feedback ghi cùng transaction']],[3.7,2.6,3.7,6])
fill_table(T[8],[['Trường','Kiểu','Ràng buộc','Mô tả'],['user_id, movie_id','bigint','PK ghép; hai FK','Một tiến độ mỗi cặp'],['position_seconds','bigint','0 ≤ position ≤ duration','Vị trí resume'],['duration_seconds','bigint','>0','Thời lượng mô phỏng'],['ratio','double precision','GENERATED STORED','position / duration, không ghi từ client'],['status','text','GENERATED STORED','finished nếu ratio≥0,95; ngược lại in_progress'],['updated_at','timestamptz','DEFAULT now()','Heartbeat gần nhất']],[3.7,2.6,3.7,6])
fill_table(T[9],[['Artifact','Định dạng','Ràng buộc','Nội dung'],['current.json','JSON','Con trỏ atomic','version và hash manifest'],['manifest.json','JSON','status=ready, files hash','dataset/spec/previous và checksum bundle'],['model.joblib','Joblib','Nguồn tin cậy, verify hash','Model, lịch sử fit và catalog phục vụ'],['gate.json','JSON','Validation chung','Candidate/incumbent, cohort, latency/rating guards'],['job.json','JSON','Trạng thái job','started/completed, family, reload result'],['resource_usage.json','JSON','Budget đã khai báo','Thời gian và RSS quan sát']],[3.9,2.1,3.8,6.2])
fill_table(T[10],[['Thành phần','Máy và cấu hình đã quan sát','Giới hạn hoặc diễn giải'],['Hệ điều hành','Windows; Python 3.14.2','Lock gắn với môi trường đã kiểm thử'],['RAM','Hệ thống báo 13,81 GiB; còn ≥3 GiB trước job','Research peak 940,2 MiB nội bộ; budget 2 GiB'],['CPU','16 logical CPU; giới hạn job 4 thread','Một job tại một thời điểm'],['Ổ đĩa','Raw, Parquet snapshots, bundles và backup local','Dung lượng phụ thuộc số run; không ghi như mức tối thiểu đã chứng minh'],['Client','Flutter widget tests và build web đạt','Chưa kiểm thử thiết bị Android/iOS vật lý']],[2.8,6.6,6.6])
lock={}
for line in (ROOT/'requirements.lock.txt').read_text(encoding='utf-8').splitlines():
    if '==' in line:
        k,v=line.split('==',1);lock[k]=v
def ver(k):return lock.get(k,'xem lock')
fill_table(T[11],[['Thành phần','Công nghệ','Phiên bản khóa','Vai trò'],['Ngôn ngữ','Python','3.14.2','Môi trường Windows đã kiểm thử'],['API','FastAPI',ver('fastapi'),'REST và Pydantic'],['ASGI','Uvicorn',ver('uvicorn'),'API port 8000'],['Model','scikit-surprise',ver('scikit-surprise'),'BiasedSVD nghiên cứu'],['SQL','Psycopg / pool',ver('psycopg')+' / '+ver('psycopg-pool'),'PostgreSQL runtime trên Supabase'],['Config','python-dotenv',ver('python-dotenv'),'.env backend; research dùng TOML']],[2.5,3.4,3.3,6.8])
fill_table(T[12],[['Thành phần','Công nghệ','Phiên bản hoặc nguồn','Vai trò'],['Framework','Flutter','Theo flutter --version của máy','Widget/service tests và build web'],['Ngôn ngữ','Dart','Ràng buộc SDK ^3.10.7','Không đồng nhất với bản SDK đang cài'],['Dependency','pubspec.lock','Bản resolved trong repo','Khóa thư viện mobile'],['Thiết bị','Android/iOS','Chưa kiểm thử vật lý','Không suy ra từ web build']],[2.5,3.2,4.5,5.8])
fill_table(T[13],[['Thành phần','Công nghệ','Phiên bản','Vai trò'],['Dashboard','Streamlit',ver('streamlit'),'7 trang đọc artifacts V2'],['Biểu đồ','Altair',ver('altair'),'CI, so sánh metric; tách đơn vị'],['Dữ liệu','Pandas / PyArrow',ver('pandas')+' / '+ver('pyarrow'),'JSON/CSV/Parquet'],['Cổng','HTTP local','8501','Mặc định khi chạy Streamlit']],[2.6,3.3,3.5,6.6])
fill_table(T[14],[['Công cụ','Mô tả'],['Git','Version code; source archive và hashes ghi trong manifest'],['Ngrok tùy chọn','Tunnel khi cần; đồng bộ AppConfig bằng công cụ cập nhật URL'],['CLI worker','Chạy job phục vụ thủ công, ngoài tiến trình API'],['Notebook tùy chọn','Phân tích thăm dò; không thay evaluator đã khóa']],[4,12])
rows=[['Thư viện','Phiên bản','Vai trò']]
mobile_versions={}
try:
 import yaml
 mobile_versions={k:v.get('version','SDK') for k,v in yaml.safe_load((ROOT/'mobile_app/pubspec.lock').read_text())['packages'].items()}
except ImportError:pass
for name,role in [('http','Gọi API, bearer và Idempotency-Key; lỗi truyền riêng'),('shared_preferences','Lưu token/thời hạn; Splash xác minh phiên với API, logout xóa local'),('cached_network_image','Cache poster; không tải video'),('flutter_rating_bar','Chọn sao explicit và chỉ báo thành công sau response'),('cupertino_icons','Biểu tượng giao diện')]:rows.append([name,mobile_versions.get(name,'xem pubspec.lock'),role])
fill_table(T[16],rows,[4,3,9])
packages=[('fastapi','Router/validation và kiểm tra ownership'),('uvicorn','ASGI API; không chạy retrain nền'),('pydantic','Request/config schema'),('scikit-surprise','BiasedSVD fit và score'),('scipy','Sparse ItemKNN theo block'),('pandas','Audit/transform DataFrame'),('numpy','Score vector hóa'),('pyarrow','Snapshot và per-user Parquet'),('streamlit','Dashboard đọc artifact'),('altair','Biểu đồ cùng đơn vị và CI'),('psycopg','SQL transaction và tham số hóa'),('psycopg-pool','Pool/queue/timeout có giới hạn'),('argon2-cffi','Password hashing Argon2id'),('joblib','Serialize payload tin cậy có checksum'),('psutil','Giám sát cây tiến trình và deadline'),('python-dotenv','.env backend, không là config nghiên cứu')]
fill_table(T[17],[['Thư viện','Phiên bản khóa','Vai trò'],*[[k,ver(k),r] for k,r in packages]],[4,3,9])
fill_table(T[18],[['Công cụ','Phiên bản hoặc nguồn','Vai trò'],['pytest',ver('pytest'),'Unit/protocol và integration opt-in'],['httpx',ver('httpx'),'FastAPI TestClient'],['Streamlit AppTest',ver('streamlit'),'Smoke 7 trang'],['flutter_test','Flutter SDK','Widget và service tests'],['flutter_lints',mobile_versions.get('flutter_lints','pubspec.lock'),'Phân tích tĩnh'],['Jupyter / Locust','Nhóm dependency tùy chọn','Chưa là bằng chứng load test V2']],[4,4,8])
envs=[('DATABASE_URL','Không hiển thị','URI PostgreSQL có password; không dùng API key/MCP OAuth thay thế'),('MOVIERS_STORAGE','files hoặc postgres','Chọn một nguồn; sau migration dùng postgres'),('DATABASE_POOL_SIZE','4; tối đa 8','Giới hạn kết nối và queue'),('DATABASE_STATEMENT_TIMEOUT_MS','15000','SET LOCAL trong mỗi transaction qua pooler'),('DATABASE_LOCK_TIMEOUT_MS','5000','Chặn chờ lock quá lâu'),('DATABASE_SSLMODE','require','Giữ verify-full nếu URI cấu hình'),('DATABASE_CONNECT_TIMEOUT','5','Giới hạn mở kết nối'),('MOVIERS_SERVING_POINTER','artifacts/serving/current.json','Bundle đã qua gate'),('ADMIN_API_TOKEN','Không hiển thị','Bảo vệ reload quản trị; không đưa vào Flutter'),('API_HOST / API_PORT','127.0.0.1 / 8000','Địa chỉ API demo'),('API_RELOAD','0','Tắt reloader khi demo ổn định'),('AUTO_RETRAIN','0','V2 luôn worker riêng; biến legacy không bật job trong API'),('TMDB_API_KEY','Không hiển thị','Tùy chọn enrichment metadata, không cần cho benchmark'),('NGROK_URL','Tùy phiên tunnel','Flutter vẫn phải dùng AppConfig/--dart-define'),('configs/research.toml','Không phải secret .env','Data/protocol/seeds/search/resources; nguồn config nghiên cứu')]
fill_table(T[19],[['Biến hoặc file','Giá trị cấu hình','Ý nghĩa'],*envs],[5,4,7])

# Bổ sung phần còn thiếu vào đúng chương, không xây một báo cáo khác.
section(P[201],'Câu hỏi nghiên cứu và căn cứ kiểm chứng',[
    'Bản cập nhật nội dung ngày 18/10/2026 đối chiếu mã nguồn và biên bản nghiệm thu ngày 16/10/2026. Thông tin hành chính ở bìa theo hồ sơ gốc; các số liệu kỹ thuật dưới đây thuộc lần kiểm chứng V2.',
    'Câu hỏi chính: hybrid thích ứng có cải thiện NDCG@10 so với baseline mạnh nhất được chọn trên VAL không? Các câu hỏi phụ kiểm tra hiệu quả theo lịch sử, lợi ích ngoài fallback, đóng góp genre và đánh đổi MMR.',
    'Thành công về kỹ thuật và kết quả thuật toán được báo riêng. MostPopular hiện tốt hơn hybrid ở so sánh chính; kết quả này không bị thay bằng số minh họa hoặc điều chỉnh TEST sau khi quan sát.'])
intro_heading=next(p for p in doc.paragraphs if p.text=='Câu hỏi nghiên cứu và căn cứ kiểm chứng')
intro_heading.style='Normal'
for r in intro_heading.runs:r.bold=True
section(P[388],'Kiến trúc tách nghiên cứu và vận hành',[
    'Nhánh nghiên cứu chỉ nhận raw ML-25M, config và snapshot có hash. Nhánh ứng dụng ghi PostgreSQL, rồi worker dùng dữ liệu fit phục vụ riêng. Không có mũi tên feedback quay vào TEST nghiên cứu.',
    'Mẫu research và các trial được giữ bất biến; các lần chạy khác code/config/data không resume chung. Dashboard không tính delta giữa các run khác snapshot, split, tập user hay protocol.'])
section(P[470],'Lấy mẫu user và đánh giá theo thời gian',[
    'Quét nguồn theo chunk 250.000 dòng, thu ID rồi sắp theo digest SHA256 của chuỗi seed:userId; chọn N ID đầu và giữ mọi rating của họ. Các profile lồng nhau: smoke 1.000, dev 4.000, research 8.000, extended 12.000 user. Tất cả dùng cùng cutoff, không tự đổi thời gian để development nhìn thấy tương lai.',
    'Đánh giá tại đầu cửa sổ tương lai: lịch sử là dữ liệu trước cutoff; fit TRAIN, chọn VAL, ghi selection bền vững rồi mới đọc TEST; refit TRAIN+VAL cho mọi model cần fit. Toàn catalog fit trừ phim đã tương tác là candidate set; tie-break score giảm và movie ID tăng.',
    'Positive là rating≥3,5; user cần ít nhất một positive trong cửa sổ. Positive ngoài catalog vẫn nằm trong relevant chính, user không có positive phục vụ được nhận 0. Conditional-on-servable là phép đo phụ có mẫu số riêng. Không lấy 99/999 item âm tính để thay metric chính [5,6].'])
section(P[470],'Baseline và thiết kế hybrid',[
    'MostPopular đếm rating trong dữ liệu fit; BayesianItemMean dùng trung bình co về mean toàn cục với prior strength 5. GlobalMean và regularized user/item bias là đối chứng rating. GenreContent dùng vector genre chuẩn hóa và hồ sơ từ các rating≥3,5 đã biết; ItemKNN dùng positive co-occurrence/cosine, shrinkage và top-neighbor sparse.',
    'Hybrid dùng percentile điểm trên cùng candidate set. Với n rating trước cutoff, trọng số SVD là w=n/(n+tau); điểm bằng w×SVD chuẩn hóa cộng (1−w)×[beta×genre chuẩn hóa+(1−beta)×Bayesian chuẩn hóa]. Nếu thiếu profile genre, beta hiệu lực bằng 0; cold user dùng Bayesian fallback. FixedHybrid, không genre và SVDSharedFallback giúp tách đóng góp.',
    'VAL chọn tau=20, beta=0,75; SVD 32 factors/15 epochs/reg=0,02; ItemKNN 50 neighbors/shrinkage10. MMR chọn trọng số 0 vì mục tiêu selection là NDCG; bảng thử trọng số MMR vẫn lưu để phân tích đánh đổi.'])
mathpara(P[470],'wᵤ = nᵤ / (nᵤ + τ)')
section(P[470],'Định nghĩa metric và khoảng tin cậy',[
    'Metric chính là macro NDCG@10 theo user; DCG dùng relevance nhị phân và chiết khấu log₂(rank+1), IDCG dùng min(K, số positive). Precision chia K, Recall chia tổng positive của user, HitRate là có ít nhất một hit. K=5/20 chỉ là phân tích phụ. RMSE/MAE chỉ áp dụng model dự đoán rating; model chỉ ranking hiển thị N/A.',
    'Coverage là tỷ lệ catalog được khuyến nghị; diversity dùng khoảng cách genre trong danh sách và novelty dựa trên tần suất fit. Các metric này đo đặc tính danh sách, không phải cảm nhận hoặc satisfaction thực tế.',
    'Mô hình ngẫu nhiên dùng seed 42/43/44. Trung bình theo user qua seed trước khi bootstrap ghép cặp 2.000 lần cho CI95 của delta; không coi user×seed là quan sát độc lập. Baseline chính được chọn bằng VAL. CI phụ thuộc sample/cutoff; ablation là thăm dò chưa hiệu chỉnh nhiều so sánh.'])
section(P[470],'PostgreSQL và ranh giới xác thực',[
    'Schema moviers chỉ được backend truy cập qua SQL, bật RLS và thu hồi quyền public/anon/authenticated. API quản lý bearer opaque, chỉ lưu digest, hỗ trợ logout và ownership. Kết nối owner có thể bypass RLS nên không coi RLS tự xác thực token FastAPI [8].',
    'Transaction ghi favorite+feedback và progress+watch_complete nguyên tử. Idempotency-Key được hash cùng payload, có hiệu lực 24 giờ; replay cùng request không đảo trạng thái mới, đổi payload dùng lại key trả 409. Mất DB trả lỗi, không fallback ghi CSV.'])
section(P[510],'Bảng sessions và idempotency_keys',[
    'Hai bảng bổ sung quản lý phiên và retry, đều có FK tới app_users và index phục vụ truy vấn thời hạn. schema_version ghi phiên bản migration.'])
addtable(P[510],['Bảng','Khóa và trường','Hợp đồng'],[
    ['sessions','token_hash PK; user_id FK; expires_at; created_at','SHA256 digest của token opaque, không lưu bearer thô; TTL12 giờ, logout xóa phiên'],
    ['idempotency_keys','PK(user_id,key_hash); payload_hash; expires_at','Ledger commit cùng nghiệp vụ, TTL24 giờ; payload khác cùng key bị từ chối'],
    ['schema_version','version PK; applied_at','Ghi marker sau khi migration hoàn tất']],[3.5,6,6.5])
section(P[510],'Migration và bảo toàn dữ liệu',[
    'Dry-run kiểm đếm và FK; apply backup nguyên trạng, cách ly orphan và import trong transaction. Chạy lại không ghi đè dữ liệu runtime mới. Timestamp naive legacy dùng Asia/Ho_Chi_Minh; timestamp có offset được giữ nguyên.',
    'Đối soát ngày 16/10/2026 có 7 accounts, 62.423 movies, 41 feedback, 13 favorites, 20 watch progress; 1 favorite không có tài khoản được cách ly, không tạo user giả. Export rollback có checksum được đọc lại bằng adapter file; sessions không export nên cần đăng nhập lại. ML-25M và model lớn vẫn local.'])

# Caption ảnh UI giữ nguồn nhưng không dùng ảnh V1 làm bằng chứng model V2.
for i in [592,599,603,607,611]:
    if P[i].text.strip():P[i].add_run(' của nguyên mẫu trước refactor')

section(P[615],'Dữ liệu thực nghiệm và chất lượng mẫu',[
    'Benchmark V2 dùng snapshot 0bf8337c28f8baeb49a9 và run_20261015T235317064101Z. Raw ratings có SHA256 9c85525758597dca76e8d98cebb9c13e018c2317b09a0878b6d383179526e385; ZIP MD5 khớp checksum GroupLens 6b51fb2759a8657d3bfcbfc42b592ada.',
    'Quét 25.000.095 dòng không phát hiện null cột bắt buộc, rating ngoài miền/bước 0,5, cặp trùng hoặc movie ID ngoài catalog. Checksum và kiểm tra schema chứng minh tính toàn vẹn/kỹ thuật; không chứng minh mọi rating là sở thích khách quan.',
    'Mẫu có 27.498 phim được chấm, trung vị 71 rating/user, min20 trên toàn lịch sử; TV distance số sao so nguồn 0,002337. Dashboard còn so năm, hoạt động user, genre và long-tail, tách mẫu số theo user/rating/phim. Nguồn có thiên lệch tự chọn và thiếu exposure/demographic; không gọi mẫu là đại diện toàn bộ khán giả.'])
addtable(P[615],['Tập','User / rating','Vai trò'],[
    ['Nguồn ML-25M','162.541 / 25.000.095','Audit toàn nguồn, catalog62.423'],['Mẫu research','8.000 / 1.237.592','Giữ toàn lịch sử user được chọn'],['TRAIN','990.073 rating','Fit và mọi thống kê trước T1'],['VAL','123.759 rating','Chọn cấu hình, không dùng TEST'],['TEST','123.760 rating','Chấm sau refit TRAIN+VAL'],['User TEST / ranking','903 / 900','3 user không có positive bị loại có công bố'],['Known / cold trong TEST','342 / 561','Khoảng75,29% rating TEST từ cold'],['Catalog TEST và unavailable','22.821 / khoảng7,30% positive','Positive ngoài catalog vẫn ở mẫu số chính']],[4,5.4,6.6])
section(P[615],'So sánh mô hình theo giao thức chung',[
    'Bảng dưới tổng hợp cùng snapshot, cutoff, candidate policy và 900 user ranking. SVD/hybrid báo trung bình seed42/43/44; baseline xác định không nhân bản seed để tăng cỡ mẫu. Điểm RMSE thấp nhất không đồng nghĩa xếp hạng tốt nhất.'])
metrics=json.loads((ROOT/'report/experiments/v2/metrics.json').read_text(encoding='utf-8'))['families']
ranked=sorted(metrics,key=lambda n:metrics[n]['ndcg'],reverse=True)
num=lambda x:f'{x:.6f}'.replace('.',',')
addtable(P[615],['Mô hình','NDCG@10','RMSE','MAE'],[[n,num(metrics[n]['ndcg']),num(metrics[n]['RMSE']) if metrics[n]['RMSE'] is not None else 'N/A',num(metrics[n]['MAE']) if metrics[n]['MAE'] is not None else 'N/A'] for n in ranked],[6,3.4,3.3,3.3])
before(P[615],'So sánh chính AdaptiveHybrid − MostPopular: delta NDCG=-0,161770, tương đối -57,70%, CI95 [-0,175655; -0,147796], n=900. Có bằng chứng giảm chất lượng xếp hạng theo giao thức này. Không dùng kết quả âm để đổi seed, candidate hoặc threshold sau khi xem TEST.')
before(P[615],'BiasedSVD đạt RMSE0,955751 nhưng NDCG0,027047; MostPopular đạt NDCG0,280358. Chênh lệch cho thấy bài toán tối ưu rating và ranking khác nhau trên mẫu/cửa sổ này. Tỷ trọng cold user cao cần được xem cùng cohort; kết quả không chứng minh SVD luôn kém mọi tình huống.')
section(P[615],'Ablation và đánh đổi của hybrid',[
    'Các đối chứng sau so cùng user sau trung bình seed. Đây là phân tích thăm dò, chưa điều chỉnh đa kiểm định; không dùng nhãn “có cải tiến” cho mọi CI dương riêng lẻ.'])
abl=json.loads((ROOT/'report/experiments/v2/ablations.json').read_text(encoding='utf-8'))
interpret={'BiasedSVD':'Gain có thể chủ yếu từ cold fallback','SVDSharedFallback':'Chưa chứng minh thêm lợi ích ngoài fallback','FixedHybrid':'Lợi ích nhỏ của thích ứng; thăm dò','AdaptiveWithoutGenre':'Chưa chứng minh genre cải thiện'}
addtable(P[615],['Đối chứng','Delta NDCG','CI95','Diễn giải'],[[r['baseline'],num(r['delta']),'['+num(r['ci95'][0])+'; '+num(r['ci95'][1])+']',interpret[r['baseline']]] for r in abl],[4.6,2.7,4.3,4.4])
before(P[615],'AdaptiveMMR trùng AdaptiveHybrid vì VAL chọn MMR=0; không bỏ nhánh này khỏi báo cáo. Trọng số MMR>0 làm tăng diversity nhưng giảm NDCG trên VAL. Genre diversity và coverage là proxy danh sách, không thay A/B test.')
section(P[615],'Chi phí tài nguyên và khả năng tái lập',[
    'Run chính mất 611,779 giây, peak RSS nội bộ 940,2 MiB, dưới budget2 GiB/120 phút. Run độc lập trước đó có cùng metric cả12 family, split hash, user hash và delta chính; peak watchdog ngoài925,94 MiB thuộc run trước, không gán cho run chính.',
    'Payload được đo độc lập với selection khóa, fit TRAIN+VAL và Joblib nén mức3, không gồm cache evaluator. Seed42 có MostPopular64.134 byte, SVD khoảng14,78 MB và hybrid16,08 MB. Thời gian fit riêng hybrid không bao gồm fit backbone dùng chung.',
    'Các bản sửa timeout/idempotency/checkpoint/UI sau benchmark có hash ở biên bản kiểm thử. Source archive trong run giữ đúng code đã tạo metric; không sửa manifest cũ để gán kết quả cho code mới.'])
section(P[615],'Dashboard nghiên cứu và truy vết số liệu',[
    'Bảy trang gồm tổng quan, provenance, tính đại diện, so sánh mô hình, phân tích đóng góp, khuyến nghị minh họa và vận hành. Loader chỉ nhận run complete, xác minh checksum và kiểm tra compatibility trước delta; missing không được tự đổi thành0.',
    'Biểu đồ tách NDCG, rating error và diversity theo đơn vị. CI của từng model và paired CI của delta có ý nghĩa khác nhau. Trang minh họa dùng lịch sử trước cutoff và danh sách đã lưu; điểm thành phần chỉ hiện khi payload xác minh được tái tạo đúng danh sách.',
    'Đã kiểm tra20 danh sách thực của MostPopular và AdaptiveHybrid tái tạo đúng từ payload; đây là kiểm tra tính nhất quán kỹ thuật, không là một lần lựa chọn lại model trên TEST.'])
section(P[615],'Kiểm thử phần mềm và database',[
    'Biên bản ngày16/10/2026 ghi lệnh python scripts/verify_refactor.py --database --flutter, exit code, thời gian và100 source hashes. Đây là kết quả đã lưu của lần nghiệm thu, không khẳng định vừa chạy lại trong ngày cập nhật báo cáo.'])
addtable(P[615],['Hạng mục','Kết quả ghi nhận','Phạm vi kiểm chứng'],[
    ['Python','66 passed; 9 DB test skip ở lượt mặc định','Protocol, metric, leakage, artifact, feedback, watchdog, gate'],['PostgreSQL opt-in','9 passed trên DB thật','Ownership, transaction rollback, concurrency, pool, timeout, replay/ledger'],['HTTP smoke','8 route đọc200; auth401; reload403','Uvicorn thật, SHA256 đầu vào trước/sau không đổi'],['Dashboard','7 trang không exception','AppTest và kiểm tra artifacts/compatibility'],['Flutter analyze','No issues found','Phân tích tĩnh'],['Flutter tests','9 passed','Phiên, lỗi API, favorite một request, player resume/lưu lỗi'],['Flutter web','Build thành công','Không thay thử nghiệm Android/iOS vật lý'],['Migration và rollback','Đối soát/export/bundle rollback đạt','File nguồn và live serving pointer không đổi']],[4,4.3,7.7])
section(P[615],'Quy trình chạy lại và kịch bản demo',[
    'Tại repo root, tạo môi trường đúng phiên bản và cài requirements.lock.txt, sau đó pip install --no-deps -e .; dependency lock hiện gắn với Windows/Python3.14.2. Không đưa secrets vào config nghiên cứu.',
    'Chuẩn bị và chạy: python -m src.experiments prepare --profile research; python -m src.experiments run --profile research. Đây là full pipeline từ raw local; cần giữ đúng config/source và đủ RAM trước job.',
    'Mở dashboard bằng streamlit run dashboard/app.py, API bằng python api/main.py. Worker: python -m src.pipeline.worker --snapshot <snapshot_folder> --selection <run_folder>/selection.json. Chỉ chọn bundle đã qua gate; TEST không kích hoạt deployment.',
    'Demo theo thứ tự: provenance → tính đại diện → bảng so sánh/CI → ablation → danh sách minh họa → health; sau đó đăng nhập app, cập nhật genre/rating/favorite, mô phỏng xem và kiểm tra resume. Không dùng demo ghi để thay benchmark nghiên cứu.'])

# Tham khảo đánh số rõ, bổ sung nguồn phương pháp và hồ sơ nội bộ.
references=[
 'FPT Corporation và FPT Software. Giới thiệu doanh nghiệp. https://fpt.com/en/about-us ; https://fptsoftware.com/about-us . Truy cập 18/10/2026.',
 'GroupLens Research. MovieLens 25M README và điều kiện sử dụng. https://files.grouplens.org/datasets/movielens/ml-25m-README.html . Truy cập 18/10/2026.',
 'Harper, F. M. và Konstan, J. A. (2015). The MovieLens Datasets History and Context. ACM TiiS 5(4), Article19. https://doi.org/10.1145/2827872 .',
 'Hug, N. (2020). Surprise A Python library for recommender systems. JOSS5(52),2174. https://doi.org/10.21105/joss.02174 . Tài liệu SVD: https://surprise.readthedocs.io/en/stable/matrix_factorization.html .',
 'Krichene, W. và Rendle, S. (2020). On Sampled Metrics for Item Recommendation. KDD. https://research.google/pubs/on-sampled-metrics-for-item-recommendation/ .',
 'Ji, Y., Sun, A., Zhang, J. và Li, C. (2023). A Critical Study on Data Leakage in Recommender System Offline Evaluation. ACM TOIS. https://arxiv.org/abs/2010.11060 .',
 'FastAPI. Features và tài liệu framework. https://fastapi.tiangolo.com/features/ . Truy cập18/10/2026.',
 'Supabase. Row Level Security. https://supabase.com/docs/guides/database/postgres/row-level-security . Truy cập18/10/2026.',
 'Koren, Y., Bell, R. và Volinsky, C. (2009). Matrix Factorization Techniques for Recommender Systems. Computer42(8),30–37. https://doi.org/10.1109/MC.2009.263 .',
 'Flutter và Streamlit. Tài liệu chính thức: https://docs.flutter.dev/ ; https://docs.streamlit.io/ .',
 'MovieRS. Hồ sơ thực nghiệm V2, ngày16/10/2026: configs/research.toml; report/experiments/v2/ gồm metrics, selection, comparisons, intervals, ablations, quality và per_user_metrics; nguồn nội bộ dự án.',
 'MovieRS. Biên bản kỹ thuật: report/REFACTOR_ACCEPTANCE.md; report/refactor/verification_v2.json; runtime_reconciliation.json; final_audit.json; dashboard_explanations.json. Ngày kiểm chứng16/10/2026; nguồn nội bộ dự án.'
]
for p in P[656:665]:
    if p._p.getparent() is not None:p._p.getparent().remove(p._p)
for i,text in enumerate(references):
    p=doc.add_paragraph(f'[{i+1}] {text}');p.paragraph_format.space_after=Pt(7);p.paragraph_format.first_line_indent=Cm(0)
    for r in p.runs:r.font.name='Times New Roman';r.font.size=Pt(12)

# Đánh dấu chú thích nguồn nội bộ ngay các bảng số liệu, tránh đòi người đọc suy đoán.
before(P[615],'Nguồn các bảng kết quả, dataset, tài nguyên và kiểm thử trong mục này: artifacts và hồ sơ nghiệm thu MovieRS V2 [11,12]. Các metric đã được làm tròn khi trình bày; JSON/Parquet giữ độ chính xác gốc.')

FONT='C:/Windows/Fonts/times.ttf';BOLD='C:/Windows/Fonts/timesbd.ttf'
def canvas(size=(1600,1600)):
    im=Image.new('RGB',size,'white');return im,ImageDraw.Draw(im)
def wrapped(draw,text,font,maxwidth):
    lines=[]
    for line in text.split('\n'):
        words=line.split();current=''
        for word in words:
            candidate=(current+' '+word).strip()
            if draw.textlength(candidate,font=font)>maxwidth and current:lines.append(current);current=word
            else:current=candidate
        lines.append(current)
    return lines
def box(draw,rect,text,size=43):
    draw.rounded_rectangle(rect,radius=10,outline='#333333',width=3,fill='white')
    font=ImageFont.truetype(FONT,size);lines=wrapped(draw,text,font,rect[2]-rect[0]-30)
    top=(rect[1]+rect[3]-len(lines)*size*1.15)/2
    for line in lines:
        draw.text(((rect[0]+rect[2]-draw.textlength(line,font=font))/2,top),line,font=font,fill='black');top+=size*1.15
def arrow(draw,start,end):
    draw.line([start,end],fill='#333333',width=4)
    a=math.atan2(end[1]-start[1],end[0]-start[0]);l=18
    draw.polygon([end,(end[0]-l*math.cos(a-.5),end[1]-l*math.sin(a-.5)),(end[0]-l*math.cos(a+.5),end[1]-l*math.sin(a+.5))],fill='#333333')
def flow(number,nodes,note):
    im,d=canvas();n=len(nodes);h=180 if n<=6 else 150;gap=48;start=35;total=n*h+(n-1)*gap
    if total>1460:h=int((1420-(n-1)*gap)/n)
    for i,node in enumerate(nodes):
        y=start+i*(h+gap);box(d,(150,y,1450,y+h),node)
        if i<n-1:arrow(d,(800,y+h),(800,y+h+gap))
    d.text((55,1520),note,font=ImageFont.truetype(FONT,34),fill='black')
    path=ASSETS/f'diagram-{number}.png';im.save(path);return path
flows={
4:(['Nhập username, password ≥8 và genre','API kiểm tra dữ liệu, tên trùng và tạo user_id ≥200000','Băm Argon2id và commit tài khoản PostgreSQL','Phát token12 giờ, SQL chỉ lưu digest','Flutter lưu phiên và mở trang chủ'], 'Tên trùng hoặc dữ liệu sai: trả lỗi; không tạo bản ghi dở.'),
5:(['Nhập username và password','API kiểm tra hash, nâng legacy sau login hợp lệ','Cấp token opaque và expires_at','Splash gọi auth/me; middleware xác minh phiên','Vào ứng dụng; logout thu hồi phiên'], 'Sai thông tin hoặc phiên hết hạn: giữ / chuyển về Login.'),
6:(['Nhập từ khóa hoặc chọn bộ lọc','Flutter gửi GET /api/movies/search','API tìm trên catalog canonical + metadata hiển thị','Trả danh sách có phân trang hoặc trạng thái rỗng','Flutter mở chi tiết phim được chọn'], 'Lỗi kết nối được hiển thị riêng, có thao tác thử lại.'),
7:(['Chọn sao explicit, gửi bearer và Idempotency-Key','Xác minh quyền sở hữu, user và movie tồn tại','Khóa nghiệp vụ, kiểm tra ledger / source priority','Commit feedback source=explicit cùng ledger SQL','Invalidate cache; client chỉ báo lưu sau response'], 'Replay không ghi lại; payload khác cùng key trả409.'),
8:(['Nhấn tim; một POST users/{id}/favorites','Xác minh bearer / ownership và idempotency','Trong transaction: lưu / xóa favorite','Cập nhật proxy favorite4,5 theo ưu tiên; bỏ tim rút proxy','Commit, invalidate cache và trả trạng thái'], 'Không dùng bỏ tim như rating âm; không ghi đè explicit.'),
9:(['Mở player mô phỏng, khôi phục vị trí','Timer1 giây thực =1 giây phim; heartbeat5 giây','PUT progress có bearer và idempotency','SQL upsert vị trí, tự tính ratio / status','Nếu ratio≥95%: watch_complete4,0 khi nguồn mạnh hơn vắng','Commit; lưu lúc thoát, thất bại hiển thị thử lại'], 'Xem dở không thành dislike; không phát video thật.'),
10:(['GET recommendations; xác minh ownership user app','Đọc cache user / explore nếu còn hạn5 phút','Gom lịch sử đã biết và feedback runtime','Score bằng bundle chọn trên VAL; hiện là MostPopular','Loại phim đã tương tác, onboarding genre rerank','Trả strategy, stage, reason và danh sách; cache'], 'Explore bật MMR riêng; ranking score không là số sao.'),
11:(['Người vận hành chạy CLI worker; khóa một job','Đọc snapshot TRAIN/VAL và selection đã khóa','Fit candidate, chấm cùng validation với incumbent','Gate NDCG, cohort, latency và rating khi phù hợp','Fit serving + feedback riêng; ghi bundle / manifest','Verify, đổi current.json atomic; admin reload'], 'Gate lỗi giữ incumbent; TEST nghiên cứu không bị đọc để chọn.')}
diagrams={}
for number,(nodes,note) in flows.items():diagrams[number]=flow(number,nodes,note)
# Use case và class theo các nhóm chức năng thật.
im,d=canvas()
for y,text in [(180,'Người dùng\nFlutter'),(680,'Người nghiên cứu\nDashboard'),(1180,'Người vận hành\nCLI / admin')]:box(d,(30,y,430,y+230),text,42)
for y,text in [(100,'Tài khoản, phiên và ownership'),(400,'Catalog, tìm kiếm và khuyến nghị'),(700,'Sao, favorite và player mô phỏng'),(1000,'Audit, benchmark, CI và giải thích'),(1300,'Worker, validation gate, reload và rollback')]:box(d,(650,y,1560,y+180),text,42)
for a,b in [(295,190),(295,490),(295,790),(795,1090),(1295,1390)]:arrow(d,(430,a),(650,b))
diagrams[1]=ASSETS/'diagram-1.png';im.save(diagrams[1])
im,d=canvas()
classes=[((30,40,750,430),'ApiService Flutter\nrequest bearer và idempotency\nkiểm tra lỗi / phiên / lưu progress'),((850,40,1570,430),'FastAPI routes + security\nauth, ownership, validation\ncommit nghiệp vụ rồi invalidate'),((30,600,750,1000),'RecommenderService\nsnapshot + cache\nscore bundle và onboarding rerank'),((850,600,1570,1000),'PostgresRepository\nuser, session, feedback, favorite\nprogress và ledger transaction'),((30,1160,750,1550),'RankingModel\nfit, score_items, save / load\nsupports_rating_prediction'),((850,1160,1570,1550),'ServingWorker\nvalidation gate và bundle\npointer atomic và rollback')]
for r,t in classes:box(d,r,t,42)
for a,b in [((750,220),(850,220)),((1210,430),(1210,600)),((400,430),(400,600)),((400,1000),(400,1160)),((850,1350),(750,1350))]:arrow(d,a,b)
diagrams[2]=ASSETS/'diagram-2.png';im.save(diagrams[2])
im,d=canvas()
erd=[((40,40,760,380),'app_users\nPK user_id\nusername unique, hash, genres'),((840,40,1560,380),'movies\nPK movie_id\ntitle, genres, metadata'),((40,520,760,860),'sessions\nPK token_hash, FK user_id\nexpires_at'),((840,520,1560,860),'feedback\nPK / FK user_id + movie_id\nrating, source, updated_at'),((40,1000,760,1350),'idempotency_keys\nPK user_id + key_hash\npayload_hash, expires_at'),((840,1000,1560,1350),'favorites / watch_progress\nPK / FK user_id + movie_id\nadded_at / position, duration')]
for r,t in erd:box(d,r,t,42)
for a,b in [((400,380),(400,520)),((1200,380),(1200,520)),((760,220),(840,690)),((400,860),(400,1000)),((1200,860),(1200,1000))]:arrow(d,a,b)
d.text((80,1450),'1 user và 1 movie có nhiều bản ghi con; schema_version lưu migration.',font=ImageFont.truetype(FONT,36),fill='black')
diagrams[3]=ASSETS/'diagram-3.png';im.save(diagrams[3])
sequences={12:(['Flutter','API','Catalog'],[(0,1,'GET tìm kiếm / phổ biến'),(1,2,'Đọc metadata canonical'),(2,1,'Phim và phân trang'),(1,0,'JSON hoặc lỗi có mã trạng thái')]),13:(['Flutter','API','PostgreSQL','Cache'],[(0,1,'POST rating + bearer + key'),(1,2,'Ownership, ledger và source'),(2,1,'Commit / rollback'),(1,3,'Invalidate sau commit'),(1,0,'changed / replay / lỗi')]),14:(['Player','API','PostgreSQL','Cache'],[(0,1,'PUT heartbeat / save cuối'),(1,2,'Transaction progress + proxy'),(2,1,'Commit; ratio / status'),(1,3,'Invalidate user'),(1,0,'Trả tiến độ; lỗi cần thử lại')]),15:(['Flutter','API','Snapshot','PostgreSQL'],[(0,1,'GET gợi ý + bearer'),(1,3,'Xác minh phiên và lấy feedback'),(3,1,'Lịch sử runtime đã commit'),(1,2,'Cache miss: score bundle'),(2,1,'Ranking / strategy / reason'),(1,0,'Danh sách chưa tương tác')]),16:(['Vận hành','Worker','Validation','API'],[(0,1,'Chạy CLI, khóa job'),(1,2,'Candidate + incumbent chung data'),(2,1,'Gate và guardrail'),(1,1,'Fit serving; verify bundle'),(1,3,'Pointer atomic + admin reload'),(3,0,'Health version; có thể rollback')])}
for number,(actors,messages) in sequences.items():
    im,d=canvas();xs=[140+i*1320/max(1,len(actors)-1) for i in range(len(actors))]
    for x,name in zip(xs,actors):box(d,(x-125,40,x+125,160),name,38);d.line([(x,170),(x,1470)],fill='#888888',width=2)
    for j,(a,b,label) in enumerate(messages):
        y=300+j*190
        if a==b:arrow(d,(xs[a],y),(xs[a]+120,y));labelx=xs[a]-200
        else:arrow(d,(xs[a],y),(xs[b],y));labelx=min(xs[a],xs[b])+20
        font=ImageFont.truetype(FONT,35)
        for k,line in enumerate(wrapped(d,label,font,1100)):d.text((labelx,y-85+k*42),line,font=font,fill='black')
    path=ASSETS/f'diagram-{number}.png';im.save(path);diagrams[number]=path

# Thay hình sơ đồ qua relationship mới; không chạm asset nguồn và ảnh mobile.
locations={1:486,2:490,3:495,4:512,5:515,6:518,7:522,8:525,9:528,10:531,11:535,12:539,13:542,14:545,15:548,16:551}
for number,idx in locations.items():
    p=P[idx]
    for child in list(p._p):
        if child.tag!=qn('w:pPr'):p._p.remove(child)
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next=True
    p.add_run().add_picture(str(diagrams[number]),width=Cm(15.3))

# Hai biểu đồ định lượng dùng thư viện biểu đồ ReportLab, dữ liệu thật trong bundle.
from reportlab.graphics.shapes import Drawing,String,Line,Rect
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pypdfium2 as pdfium
pdfmetrics.registerFont(TTFont('TimesVN',FONT))
def png_drawing(drawing,name):
    pdf_path=ASSETS/(name+'.pdf');renderPDF.drawToFile(drawing,str(pdf_path))
    pdf=pdfium.PdfDocument(str(pdf_path));im=pdf[0].render(scale=3).to_pil();path=ASSETS/(name+'.png');im.save(path);return path
dr=Drawing(600,410);chart=HorizontalBarChart();chart.x=180;chart.y=40;chart.width=360;chart.height=340
chart.data=[[metrics[n]['ndcg'] for n in reversed(ranked)]];chart.categoryAxis.categoryNames=list(reversed(ranked));chart.categoryAxis.labels.fontName='TimesVN';chart.categoryAxis.labels.fontSize=10
chart.valueAxis.valueMin=0;chart.valueAxis.valueMax=.32;chart.valueAxis.valueStep=.08;chart.valueAxis.labels.fontName='TimesVN'
chart.bars[0].fillColor=__import__('reportlab.lib.colors',fromlist=['HexColor']).HexColor('#526879');chart.barWidth=16
dr.add(chart);dr.add(String(180,390,'NDCG@10 trên cùng 900 user và giao thức V2',fontName='TimesVN',fontSize=14))
dr.add(String(180,14,'Nguồn metrics.json  MostPopular 0,280358  AdaptiveHybrid 0,118589',fontName='TimesVN',fontSize=10))
chartpath=png_drawing(dr,'ranking-comparison')
anchor=next(p for p in doc.paragraphs if p.text.startswith('So sánh chính AdaptiveHybrid'))
p=before(anchor,'');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True;p.add_run().add_picture(str(chartpath),width=Cm(16))
cap=before(anchor,'Hình ','Caption')
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),' SEQ Hình \\* ARABIC ')
rr=OxmlElement('w:r');tt=OxmlElement('w:t');tt.text='25';rr.append(tt);fld.append(rr);cap._p.append(fld)
cap.add_run(' So sánh NDCG trên mẫu research V2')

# Chuẩn hóa các mục trống và hành vi giữ trang; giữ section geometry.
front_nodes={p._p for p in P[:129]}
for original in [*P[62:75],*P[101:124]]:
    if not original.text.strip() and not original._p.xpath('.//w:fldChar|.//w:instrText|.//w:sectPr|.//w:drawing|.//w:pict|.//w:bookmarkStart|.//w:bookmarkEnd'):
        if original._p.getparent() is not None:original._p.getparent().remove(original._p)
P[100].style='Normal'
P[100].paragraph_format.space_before=Pt(0);P[100].paragraph_format.space_after=Pt(0)
P[100].paragraph_format.line_spacing=Pt(1)
for p in list(doc.paragraphs):
    if p._p in front_nodes:continue
    if p.style.name=='Title' and not p.text.strip() and not p._p.xpath('.//w:sectPr|.//w:fldChar|.//w:instrText|.//w:bookmarkStart|.//w:bookmarkEnd'):
        p._p.getparent().remove(p._p);continue
    if p.style.name.startswith('Heading'):
        p.paragraph_format.keep_with_next=True;p.paragraph_format.keep_together=True
        if p.style.name=='Heading 1':p.paragraph_format.page_break_before=True
    if p.style.name=='Caption':
        p.paragraph_format.keep_with_next=False;p.paragraph_format.keep_together=True
    if not p.text.strip() and not p._p.xpath('.//w:drawing|.//w:pict|.//m:oMath|.//m:oMathPara|.//w:sectPr|.//w:br|.//w:fldChar|.//w:instrText|.//w:bookmarkStart|.//w:bookmarkEnd'):
        prev=p._p.getprevious()
        if prev is not None and prev.tag==qn('w:p') and not ''.join(prev.itertext()).strip():p._p.getparent().remove(p._p)
for t in doc.tables:
    table_style(t)
    for p in t.rows[0].cells[0].paragraphs:p.paragraph_format.keep_with_next=False
for i in [60,75,124,615,655]:P[i].paragraph_format.page_break_before=True
settings=doc.settings.element;u=settings.find(qn('w:updateFields'))
if u is None:u=OxmlElement('w:updateFields');settings.append(u)
u.set(qn('w:val'),'true')
doc.save(OUTPUT)
# Lưu package gốc từng phần không bị Python-docx chỉnh dù không liên quan.
with ZipFile(SOURCE) as z:original_parts={n:z.read(n) for n in z.namelist()}
with ZipFile(OUTPUT) as z:parts={n:z.read(n) for n in z.namelist()}
preserve=[]
for name in original_parts:
    if name not in {'word/document.xml','word/_rels/document.xml.rels','word/settings.xml'}:
        parts[name]=original_parts[name];preserve.append(name)
with ZipFile(OUTPUT,'w',ZIP_DEFLATED) as z:
    for name,data in parts.items():z.writestr(name,data)
(TASK/'changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
(TASK/'build_manifest.json').write_text(json.dumps({'output':str(OUTPUT),'original_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'preserved_parts':preserve,'paragraphs_revised':len(changes),'new_diagrams':16,'evidence_run':'run_20261015T235317064101Z'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUTPUT),'paragraphs_revised':len(changes),'tables':len(doc.tables)},ensure_ascii=False))
