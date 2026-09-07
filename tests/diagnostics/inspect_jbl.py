import joblib
from pathlib import Path

path = Path('/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/data/temp/శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ__1a55ba2e/page_18_0.jbl')
if not path.exists():
    path = Path('/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/data/temp/శ_ర_క_ష_ణ_చర_త_ర_6వ_భ_గమ__1a55ba2e/page_18.jbl')

if path.exists():
    data = joblib.load(path)
    for key, value in data.items():
        if key != 'text' and key != 'images':
            print(f"{key}: {value}")
else:
    print(f"File not found: {path}")
