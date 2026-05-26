import asyncio
import base64
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import traceback
from typing import List

import httpx
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from bot.config import MODEL_PRESENTATION, config

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

def _log_env_check() -> None:
    logger.info("PPTX env check — node: %s | soffice: %s | pdftoppm: %s | script: %s",
                shutil.which("node"),
                shutil.which("soffice"),
                shutil.which("pdftoppm"),
                os.path.exists(_PPTX_SCRIPT))
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        logger.info("Node version: %s", r.stdout.strip())
    except Exception as e:
        logger.error("node --version failed: %s", e)


async def create_presentation_pptx(data: dict, output_path: str) -> str:
    _log_env_check()

    try:
        logger.info("Step 1: generating pptx via nodejs")
        pptx_path = await _generate_pptx_nodejs(data, output_path)
    except Exception:
        logger.error("Step 1 FAILED:\n%s", traceback.format_exc())
        raise

    try:
        logger.info("Step 2: converting to images")
        png_paths = await _convert_to_images(pptx_path)
    except Exception:
        logger.error("Step 2 FAILED:\n%s", traceback.format_exc())
        png_paths = []

    if not png_paths:
        logger.warning("Visual QA skipped: conversion to images failed")
        return pptx_path

    try:
        logger.info("Step 3: visual QA (%d images)", len(png_paths))
        issues = await _visual_qa(png_paths, data)
    except Exception:
        logger.error("Step 3 FAILED:\n%s", traceback.format_exc())
        issues = None

    if issues:
        try:
            logger.info("Step 4: fixing data — issues: %s", issues[:200])
            fixed_data = await _fix_presentation_data(data, issues)
            pptx_path = await _generate_pptx_nodejs(fixed_data, output_path)
        except Exception:
            logger.error("Step 4 FAILED:\n%s", traceback.format_exc())

    for p in png_paths:
        try:
            os.unlink(p)
        except OSError:
            pass

    return pptx_path


async def _generate_pptx_nodejs(data: dict, output_path: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        json_path = f.name

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["node", _PPTX_SCRIPT, json_path, output_path],
            capture_output=True, text=True, timeout=60,
        )
        logger.info("nodejs stdout: %s", result.stdout.strip())
        if result.returncode != 0:
            logger.error("nodejs stderr: %s", result.stderr)
            raise RuntimeError(f"pptxgenjs error: {result.stderr}")
        logger.info("PPTX saved: %s", output_path)
        return output_path
    finally:
        os.unlink(json_path)


async def _convert_to_images(pptx_path: str) -> List[str]:
    try:
        dir_path = os.path.dirname(pptx_path) or "/tmp"
        basename = os.path.splitext(os.path.basename(pptx_path))[0]

        logger.info("libreoffice: converting %s → pdf in %s", pptx_path, dir_path)
        lo_result = await asyncio.to_thread(
            subprocess.run,
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", dir_path, pptx_path],
            capture_output=True, timeout=90,
        )
        logger.info("libreoffice rc=%d stdout=%s stderr=%s",
                    lo_result.returncode,
                    lo_result.stdout.decode()[:200],
                    lo_result.stderr.decode()[:200])

        pdf_path = os.path.join(dir_path, basename + ".pdf")
        if not os.path.exists(pdf_path):
            logger.warning("PDF not found at %s after libreoffice", pdf_path)
            return []

        png_prefix = os.path.join(dir_path, basename + "_slide")
        ppm_result = await asyncio.to_thread(
            subprocess.run,
            ["pdftoppm", "-png", "-r", "100", pdf_path, png_prefix],
            capture_output=True, timeout=60,
        )
        logger.info("pdftoppm rc=%d stderr=%s", ppm_result.returncode,
                    ppm_result.stderr.decode()[:200])
        os.unlink(pdf_path)

        prefix_base = os.path.basename(png_prefix)
        pngs = sorted([
            os.path.join(dir_path, f)
            for f in os.listdir(dir_path)
            if f.startswith(prefix_base) and f.endswith(".png")
        ])
        logger.info("PNG files found: %d", len(pngs))
        return pngs
    except Exception:
        logger.error("Convert to images error:\n%s", traceback.format_exc())
        return []


async def _visual_qa(png_paths: List[str], data: dict) -> str | None:
    try:
        sample = png_paths[:6]
        content: list = [{
            "type": "text",
            "text": (
                "Ты эксперт по дизайну презентаций. "
                "Проверь эти слайды и найди ТОЛЬКО критические проблемы:\n"
                "- Текст выходит за границы блока\n"
                "- Текст нечитаем (низкий контраст)\n"
                "- Элементы перекрываются\n"
                "- Слайд выглядит пустым или сломанным\n"
                "- Кириллица не отображается\n\n"
                "Если всё хорошо — ответь: OK\n"
                "Если есть проблемы — опиши кратко на русском что исправить "
                "в тексте и содержимом слайдов (не в коде). Не придирайся к мелочам."
            ),
        }]
        for i, png_path in enumerate(sample):
            with open(png_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            })
            content.append({"type": "text", "text": f"Слайд {i + 1}"})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                json={
                    "model": MODEL_PRESENTATION,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": content}],
                },
                timeout=60.0,
            )
        answer = resp.json()["choices"][0]["message"]["content"]

        if answer.strip().upper().startswith("OK"):
            logger.info("Visual QA: no issues found")
            return None
        return answer
    except Exception as e:
        logger.error("Visual QA error: %s", e)
        return None


async def _fix_presentation_data(data: dict, issues: str) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                json={
                    "model": MODEL_PRESENTATION,
                    "max_tokens": 3000,
                    "messages": [{"role": "user", "content": (
                        f"Исправь JSON презентации.\n"
                        f"Проблемы найденные при проверке:\n{issues}\n\n"
                        f"JSON:\n{json.dumps(data, ensure_ascii=False)}\n\n"
                        f"Верни ТОЛЬКО исправленный JSON без пояснений. "
                        f"Исправляй только текст и содержимое — не структуру."
                    )}],
                },
                timeout=60.0,
            )
        fixed_text = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", fixed_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return data
    except Exception as e:
        logger.error("Fix presentation data error: %s", e)
        return data


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
