# Hợp đồng cập nhật báo cáo MovieRS

Reference: D:/Users/BT/N3_K1/ThucTapThucTe/sản phẩm/TTTT_NguyenThanhChien_24ITE020.docx
SHA256: 7ca70fec0c1044f50d0bdeca00dea56619d7b8eb3f9e1790088baadb778757ab
Word render: 81 trang, 3 section; original.pdf và reference_render/page-N.png.

Giữ bìa VKU, thông tin sinh viên/lớp/người hướng dẫn/đơn vị, ngày bìa tháng 8/2026, phiếu nhận xét trống và lời cảm ơn. Không tự đổi thông tin hành chính. Ghi ngày đối chiếu kỹ thuật 16/10 và cập nhật báo cáo 18/10 trong phần nội dung.

Trang 21 x 29,7 cm; lề trên/dưới/phải 2 cm, trái 3 cm, header/footer 1,27 cm. Ba section giữ nguyên geometry và đánh số trang đầu Roman, thân Arabic. Header có PAGE phía phải, footer khoa/lớp/tác giả; giữ nguyên. Bìa có khung và logo, không thay.

Body Times New Roman 13, justified, giãn dòng theo nguồn (1,15), đầu dòng theo mẫu. H1 16 bold black, H2 14 bold black, H3/H4 theo style nguồn. Hệ đánh số chương 1–6 và các mục đa cấp lấy từ numbering/styles thật. Caption có trường SEQ Hình. TOC 1–4, danh mục hình tự động; refresh bằng Word trên bản QA, không dùng LibreOffice save.

Slot map theo paragraph index trên reference, lưu original_text.txt: P129–197 mở đầu, P201–324 công ty, P327–344 thực trạng, P346–376 giải pháp, P388–448 lý thuyết, P470–552 thiết kế, P558–614 cài đặt, P615–645 kết luận, P655–664 tham khảo. Giữ tên chương/đề mục chính, sửa nội dung bằng chứng V2 và thêm H2/H3 trước ranh giới chương tương ứng. P8 giữ tên đề tài nguồn.

20 bảng được chỉnh tại vị trí nguồn: actors/features/API, dictionary, environment/dependencies/.env. Bảng có header lặp, không chia row, font 11–12, border xám nhẹ, padding đủ; không giữ các khẳng định RDBMS chưa có hoặc version phỏng đoán. Thêm bảng schema sessions/idempotency, snapshot/protocol/metrics/CI/tests trong chương tương ứng.

Hình 1–16 phải thay bằng sơ đồ cập nhật từ implementation. Hình 17–24 giữ asset nguồn nhưng caption và prose xác định là giao diện nguyên mẫu trước refactor, không là bằng chứng model V2; thêm hình thực nghiệm từ artifact thật. Không tự tạo screenshot UI hoặc số benchmark.

Preserve-only: bìa, headers/footers, logo, styles/numbering nền, customXml/opaque parts và ảnh UI nguồn. Editable: document.xml, settings.xml (field refresh), document.xml.rels và ảnh/sơ đồ mới. Nếu Word field refresh tạo package mới, chỉ nhập lại document.xml chứa cached TOC vào package đã chỉnh, không thay preserve-only parts.

Fidelity: original còn byte-identical; 3 section/geometry không đổi; các chương và đề mục gốc vẫn nhận ra. Có thể bỏ paragraph trống thừa và sửa lỗi chính tả; thêm mục đúng nhu cầu người dùng. Render bằng Word PDF rồi rasterize qua render_docx.py với converter Word vì runtime Windows thiếu bundled LibreOffice; tuyệt đối không gọi LibreOffice cài cá nhân. Kiểm tra toàn trang, bảng/caption/page number/TOC; PDF/PNG chỉ là QA, giao một DOCX sạch.
