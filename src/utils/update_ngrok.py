"""
update_ngrok.py — Đồng bộ NGROK_URL giữa .env và mobile_app/lib/config/app_config.dart

Sử dụng:
  python src/utils/update_ngrok.py https://xxxx.ngrok-free.dev

Script này idempotent: chạy lại nhiều lần an toàn.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DART_FILE = PROJECT_ROOT / "mobile_app" / "lib" / "config" / "app_config.dart"


def update_env(url: str) -> bool:
    """Cập nhật NGROK_URL trong .env (thêm dòng nếu chưa tồn tại)."""
    if not ENV_FILE.exists():
        print(f"[✗] Không tìm thấy {ENV_FILE}")
        return False

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    out = []
    for line in lines:
        if line.strip().startswith("NGROK_URL"):
            out.append(f"NGROK_URL={url}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"NGROK_URL={url}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[✓] Đã cập nhật NGROK_URL trong {ENV_FILE}")
    return True


def update_dart(url: str) -> bool:
    """Cập nhật giá trị ngrokUrl trong app_config.dart."""
    if not DART_FILE.exists():
        print(f"[✗] Không tìm thấy {DART_FILE}")
        return False

    content = DART_FILE.read_text(encoding="utf-8")
    new_content = re.sub(
        r"ngrokUrl\s*=\s*'[^']*'",
        f"ngrokUrl = '{url}'",
        content,
        count=1,
    )
    if new_content == content:
        print("[✗] Không tìm thấy dòng 'ngrokUrl = ...' trong app_config.dart")
        return False
    DART_FILE.write_text(new_content, encoding="utf-8")
    print(f"[✓] Đã cập nhật ngrokUrl trong {DART_FILE}")
    return True


def main():
    if len(sys.argv) != 2:
        print("Sử dụng: python src/utils/update_ngrok.py https://xxxx.ngrok-free.dev")
        sys.exit(1)

    url = sys.argv[1].strip().rstrip("/")
    if not url.startswith("https://"):
        print("[✗] URL phải bắt đầu bằng https:// (ví dụ: https://xxxx.ngrok-free.dev)")
        sys.exit(1)

    ok = update_env(url) and update_dart(url)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
