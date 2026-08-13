from pathlib import Path

import win32com.client


folder = Path(r"C:\Users\leo\Desktop\ai-strategy-agent")
docx = folder / "无生展示课_v2_一般过去时专业扩充版.docx"
pdf = folder / "_tmp_lesson_v2.pdf"
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
doc = None
try:
    doc = word.Documents.Open(str(docx), ReadOnly=True, AddToRecentFiles=False, Visible=False)
    doc.ExportAsFixedFormat(str(pdf), 17, OpenAfterExport=False, OptimizeFor=0)
    print(pdf)
    print("pages", doc.ComputeStatistics(2))
    print("words", doc.ComputeStatistics(0))
finally:
    if doc is not None:
        doc.Close(False)
    word.Quit()
