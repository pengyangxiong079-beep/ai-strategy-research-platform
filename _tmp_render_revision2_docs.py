from pathlib import Path

import fitz
import win32com.client


root = Path(r"C:\Users\leo\Desktop\ai-strategy-agent")
targets = [
    root / "Memory_Postcard_暑假经历示例.docx",
    root / "无生展示课_Revision2_完整逐字稿.docx",
]
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    for docx in targets:
        pdf = root / f"_tmp_{docx.stem}.pdf"
        out = root / f"_tmp_{docx.stem}_pages"
        out.mkdir(exist_ok=True)
        for old in out.glob("*.png"):
            old.unlink()
        doc = word.Documents.Open(str(docx), ReadOnly=True, AddToRecentFiles=False, Visible=False)
        try:
            doc.ExportAsFixedFormat(str(pdf), 17, OpenAfterExport=False, OptimizeFor=0)
            print(docx.name, "pages", doc.ComputeStatistics(2), "words", doc.ComputeStatistics(0))
        finally:
            doc.Close(False)
        rendered = fitz.open(pdf)
        for i, page in enumerate(rendered):
            page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).save(out / f"page-{i+1}.png")
finally:
    word.Quit()
