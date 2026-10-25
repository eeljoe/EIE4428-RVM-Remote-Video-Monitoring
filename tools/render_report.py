"""Render the report to page images for visual acceptance.

Microsoft Word is used for the DOCX to PDF step because LibreOffice is not
installed on this machine; Word is the authority for how the file actually
renders. The PDF is then rasterised with PyMuPDF.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPORT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/EIE4428-mini-project-report-RVM.docx").resolve()
# Word's export runs under its own security context and refuses some project
# paths, so the PDF and page images are staged in the user temp directory.
OUT = Path(tempfile.gettempdir()) / "rvm-report-render"
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / (REPORT.stem + ".pdf")


def to_pdf() -> Path:
    import win32com.client as win32

    PDF.parent.mkdir(parents=True, exist_ok=True)
    if PDF.exists():
        PDF.unlink()

    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        document = word.Documents.Open(str(REPORT), ReadOnly=True)
        try:
            # ExportAsFixedFormat is the supported PDF path; SaveAs with
            # FileFormat=17 is unreliable across Word builds.
            document.ExportAsFixedFormat(
                OutputFileName=str(PDF),
                ExportFormat=17,  # wdExportFormatPDF
                OpenAfterExport=False,
                OptimizeFor=0,  # wdExportOptimizeForPrint
                Range=0,  # wdExportAllDocument
                Item=0,  # wdExportDocumentContent
                IncludeDocProps=True,
                KeepIRM=True,
                CreateBookmarks=0,
                DocStructureTags=True,
                BitmapMissingFonts=True,
                UseISO19005_1=False,
            )
        finally:
            document.Close(SaveChanges=0)
    finally:
        word.Quit()
    return PDF


def to_images(pdf: Path) -> list[Path]:
    import fitz

    document = fitz.open(pdf)
    paths: list[Path] = []
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(dpi=110)
        target = OUT / f"page-{index + 1:02d}.png"
        pixmap.save(target)
        paths.append(target)
    document.close()
    return paths


def main() -> int:
    pdf = to_pdf()
    pages = to_images(pdf)
    print(f"pdf:  {pdf}  ({pdf.stat().st_size} bytes)")
    print(f"pages: {len(pages)}")
    for path in pages:
        print(f"  {path}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())