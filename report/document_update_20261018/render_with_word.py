"""Dùng rasterizer đóng gói với PDF do Microsoft Word xuất trên Windows."""
import argparse,importlib.util,os
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('docx');parser.add_argument('pdf');parser.add_argument('out')
args=parser.parse_args()
skill=Path('C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/render_docx.py')
spec=importlib.util.spec_from_file_location('packaged_renderer',skill)
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
pdf=str(Path(args.pdf).resolve())
renderer.convert_to_pdf=lambda *a,**k:(pdf,'Microsoft Word ExportAsFixedFormat; không dùng LibreOffice cá nhân')
os.environ['PATH']='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'+os.pathsep+os.environ['PATH']
Path(args.out).mkdir(parents=True,exist_ok=True)
renderer.rasterize(str(Path(args.docx).resolve()),str(Path(args.out).resolve()),100,False,True)
