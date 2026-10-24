"""Nghiệm thu có biên bản: test thường, HTTP, dashboard; DB/Flutter là lựa chọn."""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.experiments.artifacts import sha256,utc_now,write_json


def redact_output(value):
    """Không lưu token hoặc URI kết nối nếu fixture thất bại và in repr."""
    value=re.sub(r'postgres(?:ql)?://[^\s\x27\x22]+','[DATABASE_URI]',value)
    value=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~-]+',r'\1[REDACTED]',value)
    return re.sub(r'(?i)([\x27\x22]?(?:access_token|password_hash)[\x27\x22]?\s*[:=]\s*[\x27\x22])[^\x27\x22]+',r'\1[REDACTED]',value)


def dashboard_smoke():
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=60).run()
    if at.exception:raise AssertionError([e.message for e in at.exception])
    pages=['Tổng quan','Dữ liệu & provenance','Tính đại diện của mẫu','So sánh mô hình',
           'Phân tích đóng góp','Khuyến nghị minh họa','Vận hành']
    if not at.sidebar.radio:raise AssertionError('Cần có ít nhất một run hoàn tất để nghiệm thu dashboard')
    for page in pages:
        at.sidebar.radio[0].set_value(page).run()
        if at.exception:raise AssertionError([e.message for e in at.exception])
    return {'pages':pages,'exceptions':0}


def main():
    parser=argparse.ArgumentParser(description='Kiểm chứng refactor, ghi biên bản có exit code và hash code')
    parser.add_argument('--database',action='store_true')
    parser.add_argument('--flutter',action='store_true')
    args=parser.parse_args()
    output=ROOT/'report/refactor/verification_v2.json'
    report={'started_at':utc_now(),'status':'running','checks':[]}
    def fingerprint():
        paths=[p for directory in ['api','src','dashboard','mobile_app/lib','tests','scripts'] for p in (ROOT/directory).rglob('*')
               if p.is_file() and p.suffix in {'.py','.dart'} and '__pycache__' not in p.parts]
        return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(paths)}
    initial_sources=fingerprint()
    initial_lock=sha256(ROOT/'requirements.lock.txt')
    def command(name,arguments,cwd=ROOT,env=None,timeout=180):
        started=time.monotonic()
        process=subprocess.Popen(arguments,cwd=cwd,env={**os.environ,'PYTHONIOENCODING':'utf-8',**(env or {})},
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
        timed_out=False
        try:stdout,stderr=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            import psutil
            timed_out=True
            try:
                for child in psutil.Process(process.pid).children(recursive=True):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
            except psutil.NoSuchProcess:pass
            process.kill()
            stdout,stderr=process.communicate(timeout=10)
        code=124 if timed_out else process.returncode
        report['checks'].append({'name':name,'exit_code':code,'timeout_seconds':timeout,'timed_out':timed_out,
                                 'duration_seconds':round(time.monotonic()-started,2),
                                 'stdout_tail':redact_output(stdout[-2200:]),'stderr_tail':redact_output(stderr[-1000:])})
        write_json(output,report)
        print(name,code,flush=True)
        if code:raise RuntimeError(name+' thất bại; xem verification_v2.json')
    try:
        command('python_unit',[sys.executable,'-m','pytest','-q'],env={'MOVIERS_RUN_DB_TESTS':'0'})
        if args.database:
            command('postgres_integration',[sys.executable,'-m','pytest','tests/test_postgres_integration.py','-q'],env={'MOVIERS_RUN_DB_TESTS':'1'})
        command('http_smoke',[sys.executable,'-m','src.pipeline.verify_runtime'])
        command('compile',[sys.executable,'-m','compileall','-q','api','src','dashboard'])
        started=time.monotonic()
        result=dashboard_smoke()
        report['checks'].append({'name':'dashboard_smoke','duration_seconds':round(time.monotonic()-started,2),**result,'exit_code':0})
        if args.flutter:
            import shutil
            flutter=shutil.which('flutter')
            for arguments in [['analyze'],['test'],['build','web']]:
                command('flutter_'+'_'.join(arguments),[flutter,*arguments],ROOT/'mobile_app',timeout=600)
        command('pip_check',[sys.executable,'-m','pip','check'])
        report['status']='passed'
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        report['completed_at']=utc_now()
        report['source_sha256']=fingerprint()
        report['requirements_lock_sha256']=sha256(ROOT/'requirements.lock.txt')
        report['sources_unchanged_during_verification']=(initial_sources==report['source_sha256'] and initial_lock==report['requirements_lock_sha256'])
        if not report['sources_unchanged_during_verification']:
            report.update(status='failed',error_type='SourceChangedDuringVerification')
        write_json(output,report)
    if report['status']!='passed':raise RuntimeError('Nghiệm thu thất bại; xem verification_v2.json')


if __name__=='__main__':main()
