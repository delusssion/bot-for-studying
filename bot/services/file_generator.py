import asyncio
import json
import logging
import os
import pathlib
import subprocess
import tempfile
from typing import List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

logger = logging.getLogger(__name__)

_PPTX_SCRIPT = str(
    pathlib.Path(__file__).resolve().parent.parent.parent / "scripts" / "generate_pptx.js"
)


# ─── DOCX helpers ─────────────────────────────────────────────────────────────

def _set_font(run, bold: bool = False, italic: bool = False, size_pt: int = 14) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic


def _add_body_paragraph(doc: Document, text: str) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.first_line_indent = Cm(1.25)
    para.paragraph_format.space_after = Pt(0)
    run = para.add_run(text)
    _set_font(run)


def _add_heading(doc: Document, text: str, level: int = 1) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(12)
    para.paragraph_format.space_after = Pt(6)
    run = para.add_run(text.upper() if level == 1 else text)
    _set_font(run, bold=True, size_pt=14)


def _set_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tbl_pr.append(borders)


def _shade_cell(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _add_table(doc: Document, table_data: dict) -> None:
    caption = table_data.get("caption", "")
    headers: List[str] = table_data.get("headers", [])
    rows: List[List[str]] = table_data.get("rows", [])

    if not headers:
        return

    if caption:
        cap_para = doc.add_paragraph()
        cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_run = cap_para.add_run(caption)
        _set_font(cap_run, italic=True, size_pt=12)

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    _set_table_borders(table)

    # Header row
    for i, header_text in enumerate(headers):
        cell = table.rows[0].cells[i]
        _shade_cell(cell, "D9D9D9")
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cell.paragraphs[0].add_run(header_text)
        _set_font(run, bold=True, size_pt=12)

    # Data rows
    for r_idx, row_data in enumerate(rows, start=1):
        for c_idx, cell_value in enumerate(row_data):
            if c_idx >= len(headers):
                break
            cell = table.rows[r_idx].cells[c_idx]
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = cell.paragraphs[0].add_run(str(cell_value))
            _set_font(run, size_pt=12)

    doc.add_paragraph()  # spacing after table


def _add_footer_warning(doc: Document) -> None:
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.clear()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run("⚠️ Данные замерные — замените своими")
    run.font.name = "Times New Roman"
    run.font.size = Pt(10)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)


# ─── DOCX public ──────────────────────────────────────────────────────────────

def create_lab_docx(data: dict, output_path: str) -> str:
    doc = Document()

    # Page setup: GOST margins
    section = doc.sections[0]
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    # Remove default styles noise by resetting Normal style
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(14)

    # Title page block
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.paragraph_format.space_before = Pt(72)
    title_run = title_para.add_run(data.get("title", "Лабораторная работа"))
    _set_font(title_run, bold=True, size_pt=16)

    subject_para = doc.add_paragraph()
    subject_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subject_run = subject_para.add_run(f"Дисциплина: {data.get('subject', '')}")
    _set_font(subject_run, size_pt=14)

    if data.get("student_placeholder"):
        student_para = doc.add_paragraph()
        student_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        student_run = student_para.add_run("Выполнил(а): _______________")
        _set_font(student_run, size_pt=14)

    doc.add_page_break()

    # Sections
    for section_data in data.get("sections", []):
        _add_heading(doc, section_data.get("heading", ""))

        text = section_data.get("text", "")
        if text:
            _add_body_paragraph(doc, text)

        for formula in section_data.get("formulas", []):
            formula_para = doc.add_paragraph()
            formula_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            formula_run = formula_para.add_run(formula)
            _set_font(formula_run, italic=True)

        for table_data in section_data.get("tables", []):
            _add_table(doc, table_data)

    # Calculations
    if data.get("calculations"):
        _add_heading(doc, "Расчёты")
        _add_body_paragraph(doc, data["calculations"])

    # Conclusion
    if data.get("conclusion"):
        _add_heading(doc, "Вывод")
        _add_body_paragraph(doc, data["conclusion"])

    if data.get("has_placeholder_data"):
        _add_footer_warning(doc)

    doc.save(output_path)
    logger.info("DOCX saved: %s", output_path)
    return output_path


# ─── PPTX public ──────────────────────────────────────────────────────────────

async def create_presentation_pptx(data: dict, output_path: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f, ensure_ascii=False)
        json_path = f.name

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["node", _PPTX_SCRIPT, json_path, output_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pptxgenjs error: {result.stderr}")
        logger.info("PPTX saved: %s", output_path)
        return output_path
    finally:
        os.unlink(json_path)


# ─── Text formatter ──────────────────────────────────────────────────────────

def format_text_answer(data: dict) -> List[str]:
    """Splits answer into Telegram-safe chunks (≤4096 chars)."""
    answer: str = data.get("answer", "")
    max_len = 4096

    if len(answer) <= max_len:
        return [answer]

    parts: List[str] = []
    while answer:
        if len(answer) <= max_len:
            parts.append(answer)
            break

        # Split at last newline within limit to avoid cutting mid-sentence
        cut = answer.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len

        parts.append(answer[:cut])
        answer = answer[cut:].lstrip("\n")

    return parts
