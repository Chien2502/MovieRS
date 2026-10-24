"""Vẽ lại các sơ đồ theo ký hiệu và phong cách trắng đen của báo cáo gốc."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import math

from PIL import Image, ImageDraw, ImageFont
from lxml import etree


TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[1]
ASSETS = TASK / "assets"
ASSETS.mkdir(exist_ok=True)
SOURCE = ROOT.parent / "sản phẩm/TTTT_NguyenThanhChien_24ITE020_CapNhat_MovieRS_V2.docx"
OUTPUT = SOURCE.with_stem(SOURCE.stem + "_SoDo")
OLD_ASSETS = ROOT / "report/document_update_20261018/assets"
FONT = "C:/Windows/Fonts/arial.ttf"
BOLD = "C:/Windows/Fonts/arialbd.ttf"
SCALE = 2
W = H = 1600
diagnostics = []


def font(size=36, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, round(size * SCALE))


class Diagram:
    def __init__(self, height=1600):
        self.image = Image.new("RGB", (W * SCALE, height * SCALE), "white")
        self.d = ImageDraw.Draw(self.image)

    def line(self, points, dash=False, width=2):
        if not dash:
            self.d.line([(round(x * SCALE), round(y * SCALE)) for x, y in points], fill="black", width=max(1, round(width * SCALE)))
            return
        for a, b in zip(points, points[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            for pos in range(0, max(1, math.ceil(length)), 14):
                lo, hi = pos / max(length, 1), min(pos + 7, length) / max(length, 1)
                self.line([(a[0] + dx * lo, a[1] + dy * lo), (a[0] + dx * hi, a[1] + dy * hi)], width=width)

    def arrow(self, points, dash=False, open_head=False):
        self.line(points, dash)
        a, b = points[-2:]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        p = [(b[0] - 15 * math.cos(angle - .42), b[1] - 15 * math.sin(angle - .42)), b,
             (b[0] - 15 * math.cos(angle + .42), b[1] - 15 * math.sin(angle + .42))]
        if open_head:
            self.line(p)
        else:
            self.d.polygon([(round(x * SCALE), round(y * SCALE)) for x, y in p], fill="black")

    def rect(self, box, radius=0):
        coords = tuple(round(v * SCALE) for v in box)
        if radius:
            self.d.rounded_rectangle(coords, radius=round(radius * SCALE), fill="white", outline="black", width=2 * SCALE)
        else:
            self.d.rectangle(coords, fill="white", outline="black", width=2 * SCALE)

    def ellipse(self, box):
        self.d.ellipse(tuple(round(v * SCALE) for v in box), fill="white", outline="black", width=2 * SCALE)

    def wrap(self, text, size, width, bold=False):
        f = font(size, bold)
        rows = []
        for para in text.split("\n"):
            line = ""
            for word in para.split():
                candidate = (line + " " + word).strip()
                if self.d.textlength(candidate, font=f) > width * SCALE and line:
                    rows.append(line)
                    line = word
                else:
                    line = candidate
            rows.append(line)
        return rows

    def text(self, box, text, size=36, bold=False, align="center", valign="center", padding=12):
        x1, y1, x2, y2 = box
        rows = self.wrap(text, size, x2 - x1 - 2 * padding, bold)
        height = len(rows) * size * 1.2
        if height > y2 - y1 - padding:
            diagnostics.append({"text": text, "overflow": round(height - (y2 - y1 - padding), 1), "box": box})
        top = y1 + (y2 - y1 - height) / 2 if valign == "center" else y1 + padding
        f = font(size, bold)
        for i, row in enumerate(rows):
            tw = self.d.textlength(row, font=f) / SCALE
            x = (x1 + x2 - tw) / 2 if align == "center" else x1 + padding
            self.d.text((round(x * SCALE), round((top + i * size * 1.2) * SCALE)), row, font=f, fill="black")

    def box(self, rect, text, size=36, radius=0):
        self.rect(rect, radius)
        self.text(rect, text, size)

    def actor(self, x, y, name, size=30):
        self.ellipse((x - 22, y, x + 22, y + 44))
        self.line([(x, y + 44), (x, y + 105)])
        self.line([(x - 35, y + 65), (x + 35, y + 65)])
        self.line([(x, y + 105), (x - 30, y + 145)])
        self.line([(x, y + 105), (x + 30, y + 145)])
        self.text((x - 115, y + 150, x + 115, y + 245), name, size, valign="top", padding=1)

    def diamond(self, cx, cy, text, width=440, height=260, size=34):
        pts = [(cx, cy - height / 2), (cx + width / 2, cy), (cx, cy + height / 2), (cx - width / 2, cy)]
        self.d.polygon([(round(x * SCALE), round(y * SCALE)) for x, y in pts], fill="white", outline="black", width=2 * SCALE)
        self.text((cx - width * .34, cy - height * .28, cx + width * .34, cy + height * .28), text, size, padding=0)

    def save(self, n):
        path = ASSETS / f"diagram-{n}.png"
        self.image.save(path, dpi=(530, 530))
        return path


def use_cases():
    d = Diagram()
    d.rect((265, 35, 1335, 1565))
    d.text((600, 42, 990, 105), "MovieRS V2", 38, True)
    d.actor(115, 680, "Người dùng", 31)
    d.actor(1470, 340, "Nghiên cứu\nvà vận hành", 30)
    d.actor(1470, 1110, "Worker\nhệ thống", 30)
    user = ["Đăng ký / đăng nhập\nvà đăng xuất", "Tìm kiếm phim", "Xem gợi ý phim", "Xem chi tiết phim", "Yêu thích / bỏ thích", "Xem phim mô phỏng", "Xem danh sách\nyêu thích", "Đánh giá sao\n(explicit)", "Quản lý hồ sơ\nvà thể loại"]
    for i, label in enumerate(user):
        y = 155 + i * 160
        d.ellipse((320, y - 60, 820, y + 60))
        d.text((335, y - 56, 805, y + 56), label, 34)
        d.arrow([(150, 750), (320, y)])
    for y, label in [(225, "Audit dữ liệu\nvà nguồn gốc"), (470, "So sánh model,\nCI và ablation"), (715, "Chạy CLI worker /\nreload / rollback")]:
        d.ellipse((880, y - 85, 1305, y + 85))
        d.text((895, y - 77, 1290, y + 77), label, 33)
        d.arrow([(1435, 415), (1305, y)])
    for y, label in [(1110, "Kiểm định VAL\nvà guardrail"), (1400, "Đóng gói, verify\nvà đổi phiên bản")]:
        d.ellipse((880, y - 85, 1305, y + 85))
        d.text((895, y - 77, 1290, y + 77), label, 33)
        d.arrow([(1435, 1185), (1305, y)])
    return d.save(1)


def class_box(d, rect, name, fields, methods, stereotype=""):
    x1, y1, x2, y2 = rect
    d.rect(rect)
    head = y1 + (100 if stereotype else 75)
    middle = head + (y2 - head) * .42
    d.line([(x1, head), (x2, head)])
    d.line([(x1, middle), (x2, middle)])
    d.text((x1, y1, x2, head), (stereotype + "\n" if stereotype else "") + name, 32, True)
    d.text((x1, head, x2, middle), fields, 28, align="left", valign="top", padding=20)
    d.text((x1, middle, x2, y2), methods, 29, align="left", valign="top", padding=20)


def classes():
    d = Diagram()
    class_box(d, (40, 50, 690, 440), "ApiService", "- http.Client _client\n+ sessionExpired\n+ baseUrl", "+ hasValidSession()\n+ _request(), _write()\n+ login(), register(), logout()", "Flutter")
    class_box(d, (930, 50, 1560, 440), "api.routes + security", "Bearer / ownership\nValidation / idempotency", "+ auth, users, interactions\n+ movies, watch\n+ recommendations / reload", "«module»")
    class_box(d, (40, 610, 690, 1040), "RecommenderService", "- ranking_model, model\n- histories, candidate_ids\n- recommendations_cache", "+ get_recommendation_result()\n+ invalidate_user()\n+ apply_online_update()\n+ reload_model()")
    class_box(d, (930, 610, 1560, 1040), "PostgresRepository", "Kho dữ liệu PostgreSQL\nGiao dịch + ledger", "+ register(), session()\n+ write_feedback()\n+ favorite(), progress()")
    class_box(d, (40, 1210, 690, 1550), "RankingModel", "+ supports_rating_prediction", "+ fit(), score_items()\n+ save()", "«protocol»")
    class_box(d, (930, 1210, 1560, 1550), "src.pipeline.worker", "snapshot / selection\nbundle / current.json", "+ train_worker()\n+ promotion_gate(), rollback()", "«module»")
    d.arrow([(690, 245), (930, 245)], dash=True, open_head=True)
    d.text((705, 155, 915, 235), "HTTP", 28)
    d.arrow([(1040, 440), (1040, 515), (800, 515), (800, 790), (690, 790)], dash=True, open_head=True)
    d.text((480, 470, 790, 550), "gọi service", 27)
    d.arrow([(1300, 440), (1300, 610)], dash=True, open_head=True)
    d.text((1320, 475, 1560, 575), "gọi kho dữ liệu", 27)
    d.arrow([(690, 875), (930, 875)], dash=True, open_head=True)
    d.text((700, 790, 920, 865), "qua store", 27)
    d.arrow([(360, 1040), (360, 1210)], dash=True, open_head=True)
    d.text((390, 1080, 680, 1185), "score model", 27)
    d.arrow([(930, 1385), (690, 1385)], dash=True, open_head=True)
    d.text((690, 1270, 930, 1375), "fit và lưu", 27)
    return d.save(2)


def entity(d, rect, name, rows, size=28):
    x1, y1, x2, y2 = rect
    d.rect(rect)
    rh = (y2 - y1 - 62) / len(rows)
    d.text((x1, y1, x2, y1 + 62), name, 30, True)
    d.line([(x1, y1 + 62), (x2, y1 + 62)])
    # Hai ngăn kiểu dữ liệu và khóa bám sát mẫu ERD gốc.
    c1 = x1 + (x2 - x1) * .235
    c2 = x1 + (x2 - x1) * .84
    d.line([(c1, y1 + 62), (c1, y2)])
    d.line([(c2, y1 + 62), (c2, y2)])
    for i, (typ, field, key) in enumerate(rows):
        top = y1 + 62 + i * rh
        if i:
            d.line([(x1, top), (x2, top)])
        d.text((x1, top, c1, top + rh), typ, size - 3, align="left", padding=8)
        d.text((c1, top, c2, top + rh), field, size, align="left", padding=8)
        d.text((c2, top, x2, top + rh), key, size - 3, padding=2)


def cardinality(d, points):
    """Một bảng cha tới không hoặc nhiều bản ghi con bằng ký hiệu crow foot."""
    d.line(points)
    a, b = points[0], points[1]
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    for dist in (14, 27):
        x, y = a[0] + ux * dist, a[1] + uy * dist
        d.line([(x - px * 12, y - py * 12), (x + px * 12, y + py * 12)])
    a, b = points[-2], points[-1]
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    stem = (b[0] - ux * 25, b[1] - uy * 25)
    for sign in (-1, 0, 1):
        d.line([stem, (b[0] + sign * px * 14, b[1] + sign * py * 14)])
    x, y = b[0] - ux * 45, b[1] - uy * 45
    d.ellipse((x - 10, y - 10, x + 10, y + 10))


def erd():
    d = Diagram()
    entity(d, (520, 30, 1080, 365), "app_users", [("bigint", "user_id", "PK"), ("text", "username", "UK"), ("text", "password_hash", ""), ("text[]", "genres", ""), ("tstz", "created_at", "")], 28)
    entity(d, (20, 50, 460, 345), "sessions", [("text", "token_hash", "PK"), ("bigint", "user_id", "FK"), ("tstz", "expires_at", ""), ("tstz", "created_at", "")], 27)
    entity(d, (1140, 30, 1580, 365), "idempotency_keys", [("bigint", "user_id", "P/F"), ("text", "key_hash", "PK"), ("text", "payload_hash", ""), ("tstz", "expires_at", "")], 27)
    entity(d, (20, 580, 500, 995), "feedback", [("bigint", "user_id", "P/F"), ("bigint", "movie_id", "P/F"), ("num", "rating", ""), ("text", "source", ""), ("tstz", "updated_at", "")], 28)
    entity(d, (560, 580, 1040, 920), "favorites", [("bigint", "user_id", "P/F"), ("bigint", "movie_id", "P/F"), ("tstz", "added_at", "")], 28)
    entity(d, (1100, 580, 1580, 1080), "watch_progress", [("bigint", "user_id", "P/F"), ("bigint", "movie_id", "P/F"), ("bigint", "position_seconds", ""), ("bigint", "duration_seconds", ""), ("float8", "ratio (generated)", ""), ("text", "status (generated)", ""), ("tstz", "updated_at", "")], 27)
    entity(d, (550, 1270, 1070, 1550), "movies", [("bigint", "movie_id", "PK"), ("text", "title", ""), ("text[]", "genres", ""), ("int", "runtime_minutes", "")], 28)
    entity(d, (20, 1280, 470, 1495), "schema_version", [("text", "version", "PK"), ("tstz", "applied_at", "")], 28)
    cardinality(d, [(520, 190), (460, 190)])
    cardinality(d, [(1080, 190), (1140, 190)])
    for sx, tx in [(650, 260), (800, 800), (950, 1340)]:
        cardinality(d, [(sx, 365), (sx, 455), (tx, 455), (tx, 580)])
    for sy, tx, endy in [(710, 260, 995), (810, 800, 920), (910, 1340, 1080)]:
        cardinality(d, [(sy, 1270), (sy, 1185), (tx, 1185), (tx, endy)])
    d.text((1090, 1300, 1590, 1550), "PK: khóa chính; FK: khóa ngoại\nP/F: thành phần PK và FK\nUK: unique lower(username)\ntstz: timestamptz\nChỉ liệt kê các trường chính;\nchi tiết xem từ điển dữ liệu.", 26, align="left", padding=8)
    return d.save(3)


def flow(number, left, question, right, no_text, note, no_loop=False):
    """Bố cục hai cột với nhánh quyết định và đường quay lại như mẫu gốc."""
    d = Diagram()
    lx, rx = 415, 1220
    d.box((280, 30, 550, 115), "Bắt đầu", 36, radius=42)
    ys = [245, 465, 685] if len(left) == 3 else [215, 405, 595, 785]
    prev = 115
    for y, label in zip(ys, left):
        d.arrow([(lx, prev), (lx, y - 70)])
        d.box((120, y - 70, 710, y + 70), label, 35)
        prev = y + 70
    d.arrow([(lx, prev), (lx, 925)])
    d.diamond(lx, 1060, question, 450, 270, 33)
    rys = [245 + i * 270 for i in range(len(right))] if len(right) <= 4 else [210 + i * 220 for i in range(len(right))]
    d.arrow([(640, 1060), (810, 1060), (810, 100), (rx, 100), (rx, rys[0] - 70)])
    d.text((640, 970, 800, 1050), "Có", 32)
    for i, (y, label) in enumerate(zip(rys, right)):
        if i:
            d.arrow([(rx, rys[i - 1] + 70), (rx, y - 70)])
        d.box((920, y - 70, 1520, y + 70), label, 35)
    d.arrow([(rx, rys[-1] + 70), (rx, 1390)])
    d.box((1075, 1390, 1365, 1475), "Kết thúc", 36, radius=42)
    d.arrow([(lx, 1195), (lx, 1260)])
    d.text((435, 1190, 670, 1260), "Không", 32)
    d.box((120, 1260, 710, 1440), no_text, 34)
    if no_loop:
        d.arrow([(710, 1350), (850, 1350), (850, 1520), (1220, 1520), (1220, 1475)])
    else:
        # Lỗi được đưa về bước nhập/gửi, không tạo nhánh đi xuyên các bước khác.
        target = ys[1]
        d.arrow([(120, 1350), (45, 1350), (45, target), (120, target)])
    d.text((60, 1535, 1550, 1590), note, 28, padding=2)
    return d.save(number)


def activities():
    specs = {
        4: (["Mở màn hình đăng ký", "Nhập username, password ≥ 8 ký tự\nvà thể loại yêu thích", "Gửi POST /api/auth/register"], "Dữ liệu hợp lệ,\ntên chưa trùng?", ["Tạo user_id ≥ 200000;\nbăm mật khẩu Argon2id", "Lưu tài khoản PostgreSQL", "Cấp bearer opaque 12 giờ;\nchỉ lưu digest phía server", "Flutter lưu phiên;\nchuyển sang trang chủ"], "Hiển thị lỗi 409 / 422;\ncho phép sửa và gửi lại", "Lỗi cơ sở dữ liệu được báo rõ; không chuyển sang ghi CSV.", False),
        5: (["Mở ứng dụng / màn hình đăng nhập", "Nhập username và password", "Gửi POST /api/auth/login"], "Thông tin\nxác thực đúng?", ["Nâng hash legacy sau\nđăng nhập hợp lệ nếu cần", "Cấp bearer 12 giờ;\nlưu digest và expires_at", "Lưu phiên local; Splash\nkiểm tra GET /api/auth/me", "Vào trang chủ; đăng xuất\nsẽ thu hồi phiên server"], "Hiển thị lỗi sai tài khoản /\nmật khẩu; nhập lại", "Phiên hết hạn hoặc bị thu hồi đưa người dùng về đăng nhập.", False),
        6: (["Mở mục tìm kiếm phim", "Nhập từ khóa / bộ lọc", "GET /api/movies/search;\nAPI truy vấn catalog"], "Truy vấn\nthành công?", ["Trả kết quả phân trang\nvà metadata hiển thị", "Danh sách có phim\nhoặc rỗng không lỗi", "Flutter hiển thị kết quả\nvà phân trang", "Chọn phim để mở chi tiết"], "Hiển thị lỗi kết nối / máy chủ;\ncho phép thử lại", "Danh sách rỗng và lỗi mạng là hai trạng thái khác nhau.", False),
        7: (["Mở chi tiết phim; chọn số sao", "POST rating + bearer\nvà Idempotency-Key", "Kiểm tra phiên, ownership, rating;\nBEGIN, khóa cặp và claim ledger"], "Yêu cầu hợp lệ,\nkhông xung đột key?", ["Ledger có hiệu lực 24 giờ;\nphân biệt ghi mới và replay", "Upsert feedback explicit;\nreplay không ghi lại", "COMMIT; invalidate cache;\nonline update nếu hỗ trợ", "Trả kết quả; UI xác nhận\nđánh giá đã được lưu"], "Rollback nếu đang giao dịch;\nhiển thị lỗi 401 / 403 / 409 / 422", "Chỉ feedback thay đổi mới kích hoạt online update; retry không lặp SGD.", False),
        8: (["Bấm biểu tượng trái tim", "Gửi một POST favorite\nkèm bearer và key", "Xác minh quyền; BEGIN;\nclaim ledger, khóa cặp"], "Bật\nyêu thích?", ["Upsert favorites", "Proxy favorite 4,5\nkhi nguồn mạnh hơn vắng", "COMMIT favorite + feedback\ncùng giao dịch", "Invalidate; trả trạng thái\nvà cập nhật trái tim"], "Xóa favorite và rút proxy\nchỉ khi source=favorite;\nCOMMIT, invalidate, trả trạng thái", "Không rút đánh giá explicit; lỗi giao dịch rollback toàn bộ; replay không đảo trạng thái mới.", True),
        9: (["Mở player mô phỏng;\nkhôi phục vị trí resume", "Timer 1 giây thực = 1 giây phim;\nheartbeat mỗi 5 giây", "PUT progress + bearer + key;\nBEGIN, upsert và tính ratio"], "Tỷ lệ xem\nđạt ≥ 95%?", ["Status finished; proxy 4,0\nnếu không có nguồn mạnh hơn", "COMMIT progress + feedback;\ninvalidate khi feedback đổi", "Trả ratio / status;\nUI cập nhật tiến độ", "Lưu khi thoát; nếu lỗi\nhiển thị thao tác thử lại"], "Status in_progress;\nCOMMIT tiến độ, không dislike;\ntrả kết quả và tiếp tục xem", "Player không phát video thật; watch_complete không phải sao chủ động.", True),
        10: (["Mở trang chủ / làm mới", "GET recommendations + bearer;\nkiểm tra ownership", "Tra cache theo user / explore\nvới hạn tối đa 300 giây"], "Cache trống\nhoặc hết hạn?", ["Gom lịch sử fit, feedback\nvà sở thích runtime", "Score bundle chọn trên VAL;\nloại phim đã tương tác", "Rerank genre onboarding;\nexplore có MMR riêng", "Lưu cache; trả danh sách,\nstrategy, stage và reason"], "Trả kết quả cache còn hạn;\nkhông chạy score lại", "Bundle hiện tại là MostPopular; ranking score không phải xác suất thích hay số sao.", True),
        11: (["Người vận hành chạy CLI;\nworker khóa một job", "Đọc snapshot và selection\nđã khóa trước TEST", "Fit candidate và incumbent;\nchấm cùng TRAIN / VAL"], "Vượt gate NDCG\nvà guardrail?", ["Fit serving bằng TRAIN+VAL\nvà feedback app riêng", "Ghi bundle / manifest mới;\nkiểm tra checksum", "Đổi current.json nguyên tử;\ngiữ lịch sử phiên bản", "Reload API nếu có admin token;\nkiểm tra version / rollback"], "Ghi trạng thái rejected / failed;\ngiữ bundle và pointer hiện hành", "Worker ngoài API; không dùng TEST chọn model; rollback chỉ tới bundle hợp lệ.", True),
    }
    return {n: flow(n, *spec) for n, spec in specs.items()}


class Sequence(Diagram):
    def __init__(self, labels, count, break_before=None, portrait=False):
        super().__init__(1840 if portrait else 1600)
        self.xs = [90 + i * 1360 / (len(labels) - 1) for i in range(len(labels))]
        self.top, self.bottom = 270, 1565 if portrait else 1370
        break_before = break_before or {}
        self.gap = (self.bottom - self.top - sum(break_before.values())) / max(count - 1, 1)
        self.row_y = [self.top + row * self.gap + sum(v for k, v in break_before.items() if k <= row) for row in range(count)]
        self.labels = labels
        for i, (x, label) in enumerate(zip(self.xs, labels)):
            if i == 0:
                self.actor(x, 8, label, 27)
                self.actor(x, self.bottom + 20, label, 27)
            else:
                width = min(245, 1250 / (len(labels) - 1))
                self.box((x - width / 2, 40, x + width / 2, 150), label, 29)
                self.box((x - width / 2, self.bottom + 40, x + width / 2, self.bottom + 150), label, 29)
            self.line([(x, 175), (x, self.bottom + 20)], width=1.7)

    def y(self, row):
        return self.row_y[row]

    def frame(self, first, last, label, left=225, right=1580, divider=None):
        top, bottom = self.y(first) - 130, self.y(last) + 30
        self.line([(left, top), (right, top), (right, bottom), (left, bottom), (left, top)], dash=True, width=1.5)
        self.rect((left, top, left + 95, top + 42))
        kind, _, condition = label.partition(" ")
        self.text((left, top, left + 95, top + 42), kind, 25, padding=0)
        self.text((left + 100, top - 3, right, top + 40), condition, 26, align="left", padding=5)
        if divider is not None:
            y = self.y(divider) - 105
            self.line([(left, y), (right, y)], dash=True, width=1.5)

    def message(self, row, a, b, label, ret=False, size=28):
        y = self.y(row)
        x1, x2 = self.xs[a], self.xs[b]
        if a == b:
            self.arrow([(x1, y - 15), (x1 + 80, y - 15), (x1 + 80, y + 20), (x1, y + 20)], open_head=False)
            limit = min(1570, x1 + 350)
            # Gọi nội bộ đặt nhãn bên trái nếu participant sát lề phải.
            if limit - x1 < 180:
                self.text((x1 - 420, y - 86, x1 - 10, y - 18), label, size, padding=0)
            else:
                self.text((x1 + 5, y - 86, limit, y - 18), label, size, padding=0)
        else:
            self.arrow([(x1, y), (x2, y)], dash=ret, open_head=ret)
            self.text((min(x1, x2) + 10, y - 84, max(x1, x2) - 10, y - 8), label, size, padding=0)


def sequences():
    all_paths = {}
    d = Sequence(["Người dùng", "Flutter App", "FastAPI", "PostgreSQL"], 8)
    for args in [(0,0,1,"Nhập từ khóa / bộ lọc"), (1,1,2,"GET /api/movies/search"), (2,2,3,"Truy vấn catalog canonical"), (3,3,2,"Phim và metadata"), (4,2,2,"Áp dụng phân trang"), (5,2,1,"200: danh sách hoặc rỗng"), (6,1,0,"Hiển thị kết quả / lỗi"), (7,0,1,"Chọn phim; mở chi tiết")]:
        d.message(*args, ret=args[0] in {3,5,6}, size=30)
    all_paths[12] = d.save(12)

    d = Sequence(["Người dùng", "Flutter App", "FastAPI", "PostgreSQL", "Reco Service"], 10, {7: 70})
    d.frame(7, 7, "opt [changed và model hỗ trợ]", left=710)
    for args in [(0,0,1,"Chọn số sao"), (1,1,2,"POST rating + bearer + key"), (2,2,3,"Xác minh phiên / ownership"), (3,3,2,"User hợp lệ"), (4,2,3,"BEGIN; ledger + explicit"), (5,3,2,"COMMIT; changed / replay"), (6,2,4,"Invalidate cache user"), (7,2,4,"Online update một lần"), (8,2,1,"200 hoặc lỗi có mã"), (9,1,0,"Xác nhận đã lưu / thử lại")]:
        d.message(*args, ret=args[0] in {3,5,8,9})
    all_paths[13] = d.save(13)

    d = Sequence(["Người dùng", "Flutter Player", "FastAPI", "PostgreSQL", "Reco Service"], 9, {2: 70, 4: 65})
    d.frame(2, 7, "loop [heartbeat mỗi 5 giây]", left=290)
    d.frame(4, 4, "opt [ratio ≥ 95%]", left=1040)
    for args in [(0,0,1,"Mở player; resume"), (1,1,1,"Timer mô phỏng 1:1"), (2,1,2,"PUT progress + bearer + key"), (3,2,3,"BEGIN; ledger + upsert"), (4,3,3,"Proxy 4,0 nếu nguồn cho phép"), (5,3,2,"COMMIT; ratio, status, changed"), (6,2,4,"changed: invalidate / online"), (7,2,1,"200 / lỗi lưu cần thử lại"), (8,0,1,"Thoát: xác nhận lưu cuối")]:
        d.message(*args, ret=args[0] in {5,7})
    all_paths[14] = d.save(14)

    d = Sequence(["Người dùng", "Flutter App", "FastAPI", "Reco Service", "PostgreSQL", "Bundle model"], 13, {4: 70, 5: 60, 10: 55}, portrait=True)
    d.frame(4, 9, "alt [cache hit / cache miss]", left=560, divider=5)
    for args in [(0,0,1,"Mở trang chủ"), (1,1,2,"GET gợi ý + bearer"), (2,2,3,"Ownership hợp lệ; get_result"), (3,3,3,"Tra cache 300 giây"), (4,3,3,"[hit] Lấy danh sách đã lưu"), (5,3,4,"[miss] Feedback + sở thích"), (6,4,3,"Lịch sử runtime"), (7,3,5,"Score bundle; loại lịch sử"), (8,5,3,"Điểm và tập ứng viên"), (9,3,3,"Genre rerank; lưu cache"), (10,3,2,"Danh sách + strategy / reason"), (11,2,1,"200: kết quả / lỗi"), (12,1,0,"Hiển thị gợi ý")]:
        d.message(*args, ret=args[0] in {4,6,8,10,11,12}, size=26)
    all_paths[15] = d.save(15)

    d = Sequence(["Vận hành", "CLI", "Worker", "Validation", "Bundle / pointer", "FastAPI"], 13, {4: 70, 5: 35, 11: 55, 12: 55}, portrait=True)
    d.frame(4, 11, "alt [vượt gate / không vượt]", left=235, divider=11)
    for args in [(0,0,1,"Chạy lệnh worker"), (1,1,2,"Khóa job; snapshot + selection"), (2,2,3,"Candidate / incumbent cùng VAL"), (3,3,2,"NDCG + guardrail; không TEST"), (4,2,2,"Fit serving + feedback app"), (5,2,4,"Ghi bundle và verify checksum"), (6,4,2,"Bundle hợp lệ"), (7,2,4,"Đổi current.json nguyên tử"), (8,2,5,"Reload nếu có admin token"), (9,5,2,"Version mới hoặc lỗi reload"), (10,2,1,"promoted; api_reloaded"), (11,2,1,"rejected; giữ incumbent"), (12,1,0,"Trạng thái job; có thể rollback")]:
        d.message(*args, ret=args[0] in {3,6,9,10,11,12}, size=26)
    all_paths[16] = d.save(16)
    return all_paths


def ranking_chart():
    """Biểu đồ khoa học dùng thư viện ReportLab và số liệu artifact đã khóa."""
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics import renderPDF
    from reportlab.lib.colors import black, HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import pypdfium2 as pdfium
    pdfmetrics.registerFont(TTFont("ArialVN", FONT))
    metrics = json.loads((ROOT / "report/experiments/v2/metrics.json").read_text(encoding="utf-8"))["families"]
    ranked = sorted(metrics, key=lambda n: metrics[n]["ndcg"])
    dr = Drawing(600, 340)
    chart = HorizontalBarChart()
    chart.x, chart.y, chart.width, chart.height = 180, 40, 360, 260
    chart.data = [[metrics[n]["ndcg"] for n in ranked]]
    chart.categoryAxis.categoryNames = ranked
    chart.categoryAxis.labels.fontName, chart.categoryAxis.labels.fontSize = "ArialVN", 11
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, .32, .08
    chart.valueAxis.labels.fontName, chart.valueAxis.labels.fontSize = "ArialVN", 10
    chart.bars[0].fillColor = HexColor("#E5E5E5")
    chart.bars[0].strokeColor, chart.bars[0].strokeWidth = black, .55
    chart.barWidth = 14
    dr.add(chart)
    dr.add(String(180, 320, "NDCG@10 trên cùng 900 user và giao thức V2", fontName="ArialVN", fontSize=13))
    dr.add(String(180, 13, "Nguồn metrics.json   MostPopular 0,280358   AdaptiveHybrid 0,118589", fontName="ArialVN", fontSize=9))
    pdf_path = ASSETS / "ranking-comparison.pdf"
    renderPDF.drawToFile(dr, str(pdf_path))
    pdf = pdfium.PdfDocument(str(pdf_path))
    png = ASSETS / "ranking-comparison.png"
    pdf[0].render(scale=4).to_pil().save(png)
    return png


def main():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == "006d9b4cbcce059a96c6d50c1c49a2aa1a77d852773588ff4a06084e41daab66"
    drawings = {1: use_cases(), 2: classes(), 3: erd(), **activities(), **sequences()}
    chart = ranking_chart()
    (TASK / "drawing_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    with ZipFile(SOURCE) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    # Word đã lưu lại bản người dùng, nên dùng tên ảnh OOXML thay vì checksum PNG cũ.
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
          "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
          "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
          "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    rels = {e.get("Id"): e.get("Target") for e in etree.fromstring(parts["word/_rels/document.xml.rels"])}
    root = etree.fromstring(parts["word/document.xml"])
    lookup = {f"diagram-{n}.png": path for n, path in drawings.items()}
    lookup["ranking-comparison.png"] = chart
    changed = []
    for drawing in root.xpath("//w:drawing", namespaces=ns):
        names = drawing.xpath(".//pic:cNvPr/@name", namespaces=ns)
        if not names or names[0] not in lookup:
            continue
        embed = drawing.xpath(".//a:blip/@r:embed", namespaces=ns)[0]
        member = "word/" + rels[embed]
        parts[member] = lookup[names[0]].read_bytes()
        changed.append(member)
        if names[0] in {"diagram-15.png", "diagram-16.png"}:
            # Hai sơ đồ dày nội dung dùng khung dọc như mẫu gốc, vẫn nằm cùng trang.
            for ext in drawing.xpath(".//wp:extent|.//a:xfrm/a:ext", namespaces=ns):
                ext.set("cy", str(18 * 360000))
    assert len(changed) == 17, changed
    parts["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    manifest = {"source": str(SOURCE), "output": str(OUTPUT), "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "changed_media": changed, "drawings": 16, "charts": 1, "xml_changes": "Chỉ tăng chiều cao hai ảnh diagram-15 và diagram-16 lên 18 cm", "drawing_diagnostics": diagnostics}
    (TASK / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "changed_media": len(changed), "diagnostics": len(diagnostics)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
