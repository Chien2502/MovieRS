# Định dạng lại sơ đồ MovieRS

Mẫu: D:/Users/BT/N3_K1/ThucTapThucTe/sản phẩm/TTTT_NguyenThanhChien_24ITE020.docx, SHA256 7ca70fec0c1044f50d0bdeca00dea56619d7b8eb3f9e1790088baadb778757ab. Đã xem các trang 48–50, 54–55, 61–65 của bản render gốc; các trang còn lại đã kiểm tra ở lượt cập nhật nội dung.

Nguồn nội dung: bản CapNhat_MovieRS_V2.docx hiện tại người dùng đã lưu bằng Word, 84 trang, SHA256 006d9b4cbcce059a96c6d50c1c49a2aa1a77d852773588ff4a06084e41daab66. Đã đối chiếu với bản giao: thêm một paragraph trống sau ảnh đăng nhập, không thay văn bản. Giữ mọi thay đổi định dạng hiện tại của người dùng. Chỉ đổi 16 sơ đồ và biểu đồ kết quả. Không thay số liệu, heading, caption, ảnh UI, nội dung chương hoặc dữ liệu dự án.

Phong cách mẫu: trắng đen, chữ sans serif như Arial, đường mảnh, không tô màu nền. Use case có actor hình người, ellipse và khung hệ thống. Class có ngăn tên, thuộc tính và phương thức. ERD có ba cột kiểu/tên/khóa, quan hệ một đến không hoặc nhiều; các bảng con không nối trực tiếp nhau. Activity có đầu/cuối bo tròn, bước chữ nhật, quyết định hình thoi và nhánh có nhãn. Sequence có actor đầu/cuối, participant chữ nhật, lifeline, lời gọi liền/return đứt, khung alt/opt/loop và self-call. Không lặp lại thuật toán, schema hay retrain V1 đã lỗi thời.

Giữ bìa, 3 section, lề, styles, numbering, headers/footers, bảng và mọi part ngoài ảnh media được đổi. Hai sơ đồ tuần tự 15–16 tăng chiều cao lên 18 cm để có khung dọc như mẫu gốc, các ảnh khác giữ slot cũ. Kiểm tra chúng vẫn ở trang cũ, không đẩy nội dung sang trang khác. Biểu đồ NDCG dùng ReportLab, dữ liệu metrics.json đã xác nhận, chuyển sang nét đen/tô xám.

Xuất một DOCX mới đuôi _SoDo.docx. Render bằng Microsoft Word ExportAsFixedFormat rồi rasterize bằng render_docx.py đóng gói vì bundle Windows không có LibreOffice. Kiểm tra toàn trang, có thể dùng đối chiếu pixel với 84 trang đã nghiệm thu cho các trang không đổi. Không dùng LibreOffice cá nhân. PDF/PNG là QA nội bộ.
