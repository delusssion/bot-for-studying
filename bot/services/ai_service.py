import asyncio
import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from bot.config import config, MODEL_DEFAULT, MODEL_PRESENTATION

logger = logging.getLogger(__name__)

# Configured by logging_setup.setup_logging(); used for per-request AI stats
# Format: timestamp | user_id | order_type | model | tokens_in | tokens_out | cost_usd
_ai_logger = logging.getLogger("ai_requests")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = MODEL_DEFAULT
TIMEOUT = 90.0
MAX_RETRIES = 2
RETRY_DELAY = 3.0

# ─── System prompts ───────────────────────────────────────────────────────────

LAB_SYSTEM = """Ты эксперт по оформлению учебных работ.
Твоя задача — сгенерировать содержимое лабораторной работы в формате JSON.
Отвечай СТРОГО только валидным JSON без markdown-блоков и пояснений.
Если данные измерений не предоставлены — используй типовые учебные значения
и добавь поле "has_placeholder_data": true.

Структура ответа:
{
  "title": "название лабы",
  "subject": "предмет",
  "student_placeholder": true,
  "has_placeholder_data": false,
  "sections": [
    {
      "heading": "заголовок раздела",
      "text": "текст раздела",
      "formulas": ["формула 1", "формула 2"],
      "tables": [
        {
          "caption": "Таблица 1. Название",
          "headers": ["col1", "col2"],
          "rows": [["val1", "val2"]]
        }
      ]
    }
  ],
  "conclusion": "текст вывода",
  "calculations": "подробный расчёт с подстановкой значений"
}"""

PRESENTATION_SYSTEM = """Ты эксперт по созданию учебных презентаций для студентов вузов.
Твоя задача — создать структурированную, содержательную презентацию.

Требования к содержанию:
- Каждый слайд должен раскрывать одну чёткую мысль
- Текст лаконичный — не более 5-6 пунктов на слайд
- Каждый пункт — одна завершённая мысль, не обрывок
- Обязательно включай конкретные факты, цифры, формулы где уместно
- Заметки докладчика (notes) — развёрнутые, 2-4 предложения, то что студент скажет вслух по этому слайду
- Первый слайд — титульный (название, предмет, автор-заглушка)
- Последний слайд — "Спасибо за внимание" / выводы

Структура по количеству слайдов:
- Если не указано — делай 10-12 слайдов
- Оптимальное распределение: 1 титульный + 1-2 введение/актуальность + 5-7 основная часть + 1-2 выводы + 1 заключительный

Отвечай СТРОГО только валидным JSON без markdown-блоков, без пояснений, без текста до и после JSON.

Структура ответа:
{
  "title": "полное название презентации",
  "subject": "предмет",
  "slides_count": 11,
  "color_scheme": "blue",
  "custom_colors": null,
  "color_scheme_reasoning": "почему выбрана эта цветовая схема",
  "slides": [
    {
      "slide_number": 1,
      "layout": "title",
      "title": "название презентации",
      "subtitle": "предмет · группа · год",
      "notes": "заметки докладчика"
    },
    {
      "slide_number": 2,
      "layout": "content",
      "title": "заголовок слайда",
      "content": ["пункт 1 — конкретный и содержательный", "пункт 2"],
      "notes": "что сказать вслух по этому слайду"
    },
    {
      "slide_number": 3,
      "layout": "two_column",
      "title": "заголовок слайда",
      "left_column": ["пункт 1", "пункт 2"],
      "right_column": ["пункт 1", "пункт 2"],
      "notes": "заметки докладчика"
    }
  ]
}

Layouts доступные: title | content | two_column | section_header | conclusion
color_scheme доступные: blue | green | dark | minimal"""

_CUSTOM_COLORS_INSTRUCTION = """

Пользователь указал свой цветовой стиль. Интерпретируй его и выбери наиболее подходящую схему из: blue, green, dark, minimal.
Дополнительно верни поле custom_colors с точными HEX-цветами:
{
  "custom_colors": {
    "primary": "#HEX",
    "accent": "#HEX",
    "background": "#HEX",
    "text": "#HEX",
    "header_fill": "#HEX",
    "header_text": "#HEX"
  }
}"""

TEXT_SYSTEM = """Ты помощник студента. Отвечай подробно, структурированно и по существу.
Отвечай СТРОГО только валидным JSON без markdown-блоков и пояснений.

{
  "answer": "полный ответ с форматированием markdown",
  "format": "markdown"
}"""

EDIT_SYSTEM = """Ты редактор документа. Получишь JSON документа и инструкцию по правке.
Верни ТОЛЬКО исправленный JSON той же структуры без пояснений.
Меняй только то что указано в инструкции."""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    md = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if md:
        try:
            return json.loads(md.group(1))
        except json.JSONDecodeError:
            pass
    obj = re.search(r"(\{[\s\S]*\})", text)
    if obj:
        try:
            return json.loads(obj.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot parse JSON: {text[:300]!r}")


def _encode_photos(photos: List[bytes]) -> List[Dict]:
    items = []
    for img_bytes in photos:
        b64 = base64.b64encode(img_bytes).decode()
        items.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    return items


def _build_user_message(text: str, photos: Optional[List[bytes]]) -> Dict:
    if not photos:
        return {"role": "user", "content": text}
    content = [{"type": "text", "text": text}] + _encode_photos(photos)
    return {"role": "user", "content": content}


async def _chat(
    messages: List[Dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/studybot",
        "X-Title": "StudyBot",
    }
    payload = {"model": model, "messages": messages, "temperature": temperature}

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                t_in = usage.get("prompt_tokens", 0)
                t_out = usage.get("completion_tokens", 0)

                # Count images in request for logging
                n_images = sum(
                    1 for m in messages
                    if isinstance(m.get("content"), list)
                    for item in m["content"]
                    if item.get("type") == "image_url"
                )
                _ai_logger.info(
                    "model=%s in=%s out=%s images=%s prompt=%s",
                    model, t_in, t_out, n_images,
                    str(messages[-1].get("content", ""))[:80].replace("\n", " "),
                )
                logger.info("OpenRouter in=%s out=%s images=%s model=%s", t_in, t_out, n_images, model)
                return data
        except httpx.TimeoutException:
            if attempt < MAX_RETRIES:
                logger.warning("Timeout attempt %d/%d, retry in %ss", attempt + 1, MAX_RETRIES, RETRY_DELAY)
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise


def _extract(response: Dict) -> tuple[str, int, int]:
    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})
    return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


# ─── Public API ───────────────────────────────────────────────────────────────

# Gemini 2.0 Flash approximate pricing (USD per token)
_COST_IN = 0.0000001   # $0.10 / 1M
_COST_OUT = 0.0000004  # $0.40 / 1M


def _log_ai(user_id: int, order_type: str, t_in: int, t_out: int) -> None:
    cost = t_in * _COST_IN + t_out * _COST_OUT
    _ai_logger.info(
        "%s | %s | %s | %s | %s | %.8f",
        user_id, order_type, DEFAULT_MODEL, t_in, t_out, cost,
    )


async def generate_lab(
    task_data: dict,
    photos: Optional[List[bytes]] = None,
    user_id: int = 0,
) -> dict:
    user_parts = [
        f"Предмет: {task_data.get('subject', 'не указан')}",
        f"Тема: {task_data.get('topic', 'не указана')}",
        f"Задание/условие: {task_data.get('description', 'не указано')}",
    ]
    if task_data.get("measurements"):
        user_parts.append(f"Данные измерений: {task_data['measurements']}")
    if task_data.get("requirements"):
        user_parts.append(f"Дополнительные требования: {task_data['requirements']}")
    if photos:
        user_parts.append(f"[Прикреплено {len(photos)} фото задания]")

    user_msg = _build_user_message("\n".join(user_parts), photos)
    response = await _chat([{"role": "system", "content": LAB_SYSTEM}, user_msg])
    raw, t_in, t_out = _extract(response)
    _log_ai(user_id, "lab_docx", t_in, t_out)
    return {"json_data": _parse_json(raw), "tokens_input": t_in, "tokens_output": t_out}


async def generate_presentation(
    task_data: dict,
    photos: Optional[List[bytes]] = None,
    user_id: int = 0,
) -> dict:
    user_parts = [
        f"Тема: {task_data.get('topic', 'не указана')}",
    ]
    if task_data.get("subject"):
        user_parts.append(f"Предмет: {task_data['subject']}")
    if task_data.get("description") and task_data["description"] not in ("[фото задания]", "[PDF задание]"):
        user_parts.append(f"Задание/условие: {task_data['description']}")
    if task_data.get("requirements"):
        user_parts.append(f"Требования: {task_data['requirements']}")

    color_scheme = task_data.get("color_scheme", "blue")
    if color_scheme == "custom":
        custom_desc = task_data.get("color_scheme_custom", "")
        user_parts.append(f"Цветовой стиль по пожеланию пользователя: {custom_desc}")
        system = PRESENTATION_SYSTEM + _CUSTOM_COLORS_INSTRUCTION
    else:
        user_parts.append(f"Цветовая схема: {color_scheme}")
        system = PRESENTATION_SYSTEM

    if photos:
        user_parts.append(f"[Прикреплено {len(photos)} фото задания]")

    user_msg = _build_user_message("\n".join(user_parts), photos)
    response = await _chat(
        [{"role": "system", "content": system}, user_msg],
        model=MODEL_PRESENTATION,
    )
    raw, t_in, t_out = _extract(response)
    _log_ai(user_id, "presentation_pptx", t_in, t_out)
    return {"json_data": _parse_json(raw), "tokens_input": t_in, "tokens_output": t_out}


async def generate_text_answer(task_data: dict, user_id: int = 0) -> dict:
    question = task_data.get("question") or task_data.get("description", "")
    response = await _chat([
        {"role": "system", "content": TEXT_SYSTEM},
        {"role": "user", "content": question},
    ])
    raw, t_in, t_out = _extract(response)
    _log_ai(user_id, "text_answer", t_in, t_out)
    return {"json_data": _parse_json(raw), "tokens_input": t_in, "tokens_output": t_out}


async def apply_edit(
    original_json: dict,
    edit_instruction: str,
    order_type: str,
    user_id: int = 0,
) -> dict:
    user_content = (
        f"Документ (тип: {order_type}):\n{json.dumps(original_json, ensure_ascii=False)}\n\n"
        f"Инструкция: {edit_instruction}"
    )
    response = await _chat(
        [
            {"role": "system", "content": EDIT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    raw, t_in, t_out = _extract(response)
    _log_ai(user_id, f"edit_{order_type}", t_in, t_out)
    return {"json_data": _parse_json(raw), "tokens_input": t_in, "tokens_output": t_out}
