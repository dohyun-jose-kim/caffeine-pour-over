from pathlib import Path

import pymupdf


def representative_scientific_pdf(path: Path) -> Path:
    """Generate a tiny native-text paper fixture; no copyrighted fixture is stored."""
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((50, 50), "A Two-Column Test Paper", fontsize=16)
    page.insert_textbox(
        pymupdf.Rect(50, 90, 285, 300),
        "1. Methods\nNative claim: MIC = 2 ug/mL.\nLeft-column methods text.",
    )
    page.insert_textbox(
        pymupdf.Rect(315, 90, 550, 300),
        "2. Results\nStructured conflict fixture: MIC = 20 ug/mL.\nRight-column results text.",
    )
    page.draw_rect(pymupdf.Rect(80, 340, 260, 460), color=(0, 0, 0))
    page.insert_text((80, 485), "Figure 1. Synthetic response curve.")
    page.insert_text((80, 540), "Table 1. Model | Accuracy")
    page.insert_text((80, 565), "A | 0.92")
    page.insert_text((80, 620), "Equation 1: y = sum_i x_i")
    document.new_page(width=600, height=800)
    page = document.new_page(width=600, height=800)
    page.insert_text((50, 50), "3. Discussion")
    page.insert_text((50, 90), "The numeric discrepancy requires original evidence.")
    document.save(path)
    document.close()
    return path
