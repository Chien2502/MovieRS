"""Đối chiếu URL API thực sự của app Flutter debug trên Android qua VM Service."""

import argparse
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import urlopen


def adb(device, *arguments):
    command = ["adb", *(["-s", device] if device else []), *arguments]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def active_vm_service(device):
    pid = adb(device, "shell", "pidof", "com.example.mobile_app").strip()
    if not pid:
        raise RuntimeError("Không thấy ứng dụng MovieRS đang chạy trên điện thoại.")
    pattern = re.compile(
        rf"I/flutter \(\s*{re.escape(pid)}\): The Dart VM service is listening on "
        r"(http://127\.0\.0\.1:(\d+)/\S+)"
    )
    for _ in range(12):
        lines = adb(device, "logcat", "-d", "-v", "time", "-s", "flutter:I")
        match = pattern.search(lines)
        if match:
            return match.group(1), match.group(2)
        time.sleep(1)
    raise RuntimeError("Không thấy VM Service của bản Flutter debug đang chạy.")


def rpc(base, method, **parameters):
    with urlopen(f"{base}{method}?{urlencode(parameters)}", timeout=8) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(f"VM Service báo lỗi tại {method}.")
    return payload["result"]


def runtime_url(device):
    service_url, remote_port = active_vm_service(device)
    local_port = adb(device, "forward", "tcp:0", f"tcp:{remote_port}")
    try:
        parsed = urlsplit(service_url)
        base = urlunsplit((parsed.scheme, f"127.0.0.1:{local_port}", parsed.path, "", ""))
        isolate = next(item for item in rpc(base, "getVM")["isolates"] if item["name"] == "main")
        libraries = rpc(base, "getIsolate", isolateId=isolate["id"])["libraries"]
        library = next(item for item in libraries if item["uri"].endswith("/config/app_config.dart"))
        classes = rpc(base, "getObject", isolateId=isolate["id"], objectId=library["id"])["classes"]
        app_config = next(item for item in classes if item["name"] == "AppConfig")
        result = rpc(
            base,
            "invoke",
            isolateId=isolate["id"],
            targetId=app_config["id"],
            selector="get:serverUrl",
            argumentIds="[]",
        )
        return result["valueAsString"]
    finally:
        adb(device, "forward", "--remove", f"tcp:{local_port}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected_url")
    parser.add_argument("--device")
    args = parser.parse_args()
    try:
        actual = runtime_url(args.device)
    except (KeyError, StopIteration, OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Không xác minh được URL trong ứng dụng: {error}", file=sys.stderr)
        return 2
    if actual.rstrip("/") != args.expected_url.rstrip("/"):
        print(f"URL trong ứng dụng là {actual}; cần {args.expected_url}.", file=sys.stderr)
        return 1
    print(f"Đã xác minh URL API trong ứng dụng trên điện thoại: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
