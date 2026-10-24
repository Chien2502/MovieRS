"""Đo RAM cả cây tiến trình và dừng job khi vượt ngân sách đã khai báo."""

import threading
import time
import os
import subprocess
import sys

import psutil


class BudgetExceeded(RuntimeError):
    """Job chưa hoàn tất vì vượt tài nguyên; không được báo kết quả thành công."""


class ResourceMonitor:
    def __init__(self, config, minutes):
        self.config, self.seconds = config, minutes * 60
        self.started = time.monotonic()
        self.peak_rss = 0
        self.reason = None
        self.stopped = threading.Event()

    def sample(self):
        proc = psutil.Process()
        rss = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                rss += child.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        self.peak_rss = max(self.peak_rss, rss)
        if rss > self.config.max_rss_gib * 2**30:
            self.reason = 'Vượt ngân sách RAM'
        if time.monotonic() - self.started > self.seconds:
            self.reason = 'Vượt ngân sách thời gian'

    def _loop(self):
        while not self.stopped.wait(0.2):
            self.sample()

    def check(self):
        self.sample()
        if self.reason:
            raise BudgetExceeded(self.reason)

    def __enter__(self):
        if psutil.virtual_memory().available < self.config.min_available_gib * 2**30:
            raise BudgetExceeded('RAM trống chưa đủ để bắt đầu job')
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stopped.set()
        self.thread.join()
        self.sample()

    def report(self):
        return {'elapsed_seconds': round(time.monotonic() - self.started, 3),
                'peak_process_tree_rss_mib': round(self.peak_rss / 2**20, 2),
                'budget_exceeded': self.reason}


def supervise(command, config, profile):
    """Watchdog ở tiến trình riêng vẫn dừng được fit Cython đang giữ GIL."""
    from src.experiments.artifacts import read_json, utc_now, write_json
    resource=config.resources
    if psutil.virtual_memory().available < resource.min_available_gib*2**30:
        raise BudgetExceeded('RAM trống chưa đủ để bắt đầu job')
    child=subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    owned_pids={child.pid}
    started=time.monotonic()
    peak=0
    reason=None
    while child.poll() is None:
        try:
            process=psutil.Process(child.pid)
            rss=process.memory_info().rss
            for p in process.children(recursive=True):
                owned_pids.add(p.pid)
                try:rss+=p.memory_info().rss
                except psutil.NoSuchProcess:pass
            peak=max(peak,rss)
            if rss>resource.max_rss_gib*2**30:reason='Vượt RAM: watchdog đã dừng job'
            if time.monotonic()-started>config.profiles[profile].minutes*60:reason='Vượt thời gian: watchdog đã dừng job'
        except psutil.NoSuchProcess:
            break
        if reason:
            for p in process.children(recursive=True):
                try:p.kill()
                except psutil.NoSuchProcess:pass
            child.kill()
            child.wait()
            break
        time.sleep(.2)
    code=child.wait()
    base=config.path(config.run_dir)
    for manifest_path in base.glob('*/manifest.json'):
        manifest=read_json(manifest_path)
        if manifest.get('worker_pid') not in owned_pids:continue
        report={'watchdog_peak_rss_mib':round(peak/2**20,2),'elapsed_seconds':round(time.monotonic()-started,2),
                'reason':reason,'exit_code':code,'checked_at':utc_now()}
        # Bổ sung watchdog vào manifest; không sửa artifacts đã có checksum.
        manifest['watchdog']=report
        if reason or code:
            manifest['status']='failed'
            manifest['error_type']='WatchdogBudgetExceeded' if reason else 'WorkerFailed'
        write_json(manifest_path,manifest)
    lock=base/'.research.lock'
    if lock.exists() and lock.read_text().strip() in {str(p) for p in owned_pids}:lock.unlink()
    if reason:raise BudgetExceeded(reason)
    return code
