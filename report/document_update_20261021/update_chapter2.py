"""Chỉnh Chương 2 của báo cáo, giữ nguyên các chương và định dạng còn lại."""

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


ROOT = Path(r"D:\Users\BT\N3_K1\ThucTapThucTe\sản phẩm")
SOURCE = ROOT / "TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2_SoDo.docx"
OUTPUT = ROOT / "TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2_SoDo_Chuong2.docx"


REPLACEMENTS = {
    281: "THỰC TRẠNG CÁC HỆ THỐNG ĐA PHƯƠNG TIỆN",
    282: "Bối cảnh khai thác và tiếp cận nội dung",
    283: "Các nền tảng đa phương tiện cung cấp phim, chương trình và video theo yêu cầu trên nhiều thiết bị. Khi danh mục mở rộng, vấn đề không chỉ là lưu trữ và phát nội dung mà còn là giúp người xem tìm được lựa chọn phù hợp. Trang chủ, thanh tìm kiếm, danh mục thể loại và bảng xếp hạng là những cách tiếp cận phổ biến [13].",
    284: "Tìm kiếm phát huy hiệu quả khi người dùng đã biết tên hoặc chủ đề cần xem. Ngược lại, trong tình huống chỉ có nhu cầu giải trí chung, người dùng phải xem xét nhiều lựa chọn trước khi quyết định. Danh sách theo thể loại hoặc mức độ phổ biến giúp thu hẹp phạm vi, nhưng chưa phản ánh đầy đủ sở thích và bối cảnh của từng cá nhân.",
    285: "Nhu cầu thưởng thức cũng không cố định. Cùng một người có thể chọn nội dung khác nhau tùy thời điểm, thời lượng rảnh, thiết bị sử dụng hoặc mục đích xem. Vì vậy, một cách sắp xếp giống nhau cho mọi người khó đáp ứng đồng thời yêu cầu khám phá, tiếp tục xem và tìm lại nội dung quen thuộc.",
    286: "Cần xem xét cả cách nội dung được giới thiệu lẫn dữ liệu hệ thống quan sát được. Đánh giá sao và nhận xét thể hiện ý kiến trực tiếp; lượt nhấp, thời lượng xem hoặc hành động lưu nội dung chỉ phản ánh hành vi trong một ngữ cảnh cụ thể. Hai nhóm tín hiệu này không thể được diễn giải như nhau [15].",
    287: "Những hạn chế trong quá trình khám phá nội dung",
    288: "Một hệ thống chỉ dựa vào tìm kiếm, phân loại thủ công hoặc bảng xếp hạng chung có thể giúp truy cập nội dung, nhưng vẫn để phần lớn công việc lựa chọn cho người dùng. Đối với kho nội dung lớn, hạn chế này thể hiện rõ ở các trường hợp sau:",
    289: "Dữ liệu tương tác không đồng đều: người dùng chỉ tiếp xúc với một phần danh mục, còn nhiều nội dung có ít tín hiệu quan sát được. Không có tương tác không đồng nghĩa với không yêu thích, vì nội dung có thể chưa từng được hiển thị. Nếu bỏ qua sự khác biệt giữa chưa xem và không quan tâm, hệ thống dễ suy luận thiếu căn cứ về sở thích.",
    290: "Người dùng mới chưa có lịch sử đủ để nhận diện sở thích; nội dung mới cũng chưa có phản hồi để xác định khán giả phù hợp. Đây là hai dạng của bài toán khởi động lạnh. Danh sách phổ biến hoặc mô tả nội dung có thể hỗ trợ ban đầu, nhưng mức độ phù hợp vẫn cần được kiểm chứng khi có thêm tương tác [14].",
    291: "Thị hiếu thay đổi theo thời gian, trong khi dữ liệu lịch sử phản ánh những lựa chọn đã xảy ra. Nếu cách sắp xếp nội dung không được cập nhật theo tín hiệu mới, các gợi ý có thể kém phù hợp với nhu cầu hiện tại. Mặt khác, phản ứng tức thời trước một nội dung cũng chưa đủ để kết luận sở thích lâu dài của người xem.",
    292: "Việc ưu tiên nội dung phổ biến hoặc quá giống những gì người dùng đã xem có thể khiến danh sách gợi ý lặp lại và hạn chế cơ hội khám phá. Bên cạnh mức độ phù hợp, một trải nghiệm giới thiệu nội dung còn cần chú ý đến sự đa dạng và khả năng tiếp cận các phần khác nhau của danh mục [13].",
    293: "Nguyên nhân và định hướng giải pháp",
    294: "Các hạn chế trên xuất phát từ khoảng cách giữa dữ liệu quan sát được và nhu cầu thực tế. Hệ thống chỉ ghi nhận hành vi sau khi nội dung được hiển thị; mức độ tiếp xúc giữa các nội dung không giống nhau. Sở thích cá nhân phụ thuộc vào thời điểm và ngữ cảnh, còn thông tin mô tả có thể chưa đủ để phân biệt các lựa chọn gần giống nhau.",
    295: "Phản hồi tường minh thường rõ nghĩa hơn nhưng không phải lúc nào cũng sẵn có. Phản hồi ngầm phong phú hơn song mang tính suy đoán: một lượt nhấp có thể do hình ảnh thu hút, còn việc dừng xem có thể do hoàn cảnh cá nhân. Vì vậy, cần đánh giá độ tin cậy của tín hiệu và tránh coi hành vi đơn lẻ là kết luận chắc chắn về sở thích [15].",
    296: "Các phương thức dựa riêng vào mức độ phổ biến, đặc trưng nội dung hoặc lịch sử tương tác đều có giới hạn trong một số tình huống. Định hướng phù hợp là kết hợp những nguồn thông tin có thể sử dụng, đồng thời có cách xử lý riêng cho trường hợp thiếu dữ liệu. Mục tiêu là hỗ trợ lựa chọn nội dung một cách có căn cứ, thay vì thay thế hoàn toàn quyền quyết định của người xem.",
    297: "Từ thực trạng đó, có thể đề xuất xây dựng hệ khuyến nghị để hỗ trợ khám phá nội dung. Hệ thống lựa chọn và sắp xếp nội dung có khả năng phù hợp dựa trên thông tin nội dung, tín hiệu tương tác và bối cảnh sử dụng khi dữ liệu cho phép. Hiệu quả cần được xem xét qua mức độ phù hợp, độ đa dạng, khả năng bao phủ danh mục và độ tin cậy của dữ liệu đầu vào. Chương tiếp theo trình bày một phương án cụ thể theo định hướng này.",
}


REFERENCES = [
    "[13] Alvino, C. và Basilico, J. (2015). Learning a Personalized Homepage. Netflix Technology Blog. https://netflixtechblog.com/learning-a-personalized-homepage-aa8ec670359a .",
    "[14] Lee, J., Kothari, N. và Natsev, P. (2016). Content-based Related Video Recommendations. NIPS Demonstration Track. https://research.google/pubs/content-based-related-video-recommendations/ .",
    "[15] Hu, Y., Koren, Y. và Volinsky, C. (2008). Collaborative Filtering for Implicit Feedback Datasets. ICDM, 263–272. https://doi.org/10.1109/ICDM.2008.22 .",
]


def replace_text_keep_structure(paragraph: Paragraph, value: str) -> None:
    """Giữ bookmark/cấu trúc đoạn, xóa định dạng đậm cũ của nhãn đầu đoạn."""
    if not paragraph.runs:
        paragraph.add_run(value)
        return
    paragraph.runs[0].text = value
    if paragraph.style.name == "Normal":
        paragraph.runs[0].bold = False
    for run in paragraph.runs[1:]:
        run.text = ""


doc = Document(SOURCE)
assert doc.paragraphs[281].text == "THỰC TRẠNG HỆ THỐNG KHUYẾN NGHỊ ĐA PHƯƠNG TIỆN"
assert doc.paragraphs[298].text == "ĐỀ XUẤT GIẢI PHÁP"
assert doc.paragraphs[619].text.startswith("[12] MovieRS")

for index, content in REPLACEMENTS.items():
    replace_text_keep_structure(doc.paragraphs[index], content)

# Cập nhật mục lục tĩnh cùng nhan đề Chương 2; giữ nguyên số trang và field.
old_title = "THỰC TRẠNG HỆ THỐNG KHUYẾN NGHỊ ĐA PHƯƠNG TIỆN"
for node in doc.element.iter(qn("w:t")):
    if node.text and old_title in node.text:
        node.text = node.text.replace(old_title, REPLACEMENTS[281])

# Bổ sung nguồn gốc học thuật cho các nhận định mới, sao chép định dạng tài liệu tham khảo.
anchor = doc.paragraphs[619]
for reference in REFERENCES:
    element = deepcopy(anchor._p)
    anchor._p.addnext(element)
    anchor = Paragraph(element, anchor._parent)
    replace_text_keep_structure(anchor, reference)

# Giữ toàn bộ danh mục tài liệu tham khảo trên cùng trang, với khoảng cách hợp lý.
for paragraph in doc.paragraphs[608:]:
    if paragraph.text.startswith("["):
        paragraph.paragraph_format.space_after = 0
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

doc.save(OUTPUT)
print(OUTPUT)
