import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / '.vendor'))
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8')
path = Path(r'C:\Users\Igor\Downloads\ВКР практика (10).pdf')
reader = PdfReader(path.open('rb'))
for i in range(8, 14):
    if i >= len(reader.pages):
        break
    text = reader.pages[i].extract_text() or ''
    print(f'--- Page {i+1} ---')
    print(text[:4000])
