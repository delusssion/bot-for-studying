import asyncio
import io
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_PHOTOS = 20
FINALIZE_DELAY = 2.0

# In-memory cache for PDF-converted images; keyed by user_id
_pdf_cache: Dict[int, List[bytes]] = {}


class MediaCollector:
    """Collects Telegram media groups (burst of photos) and fires callback after quiet period."""

    def __init__(self) -> None:
        self._groups: Dict[str, Dict] = {}

    async def add_photo(
        self,
        message,  # aiogram Message
        on_finalize: Callable,
    ) -> None:
        group_id = message.media_group_id or f"single_{message.message_id}"

        if group_id not in self._groups:
            self._groups[group_id] = {
                "file_ids": [],
                "message": message,
                "timer": None,
                "callback": on_finalize,
            }

        group = self._groups[group_id]
        file_id = message.photo[-1].file_id  # largest resolution
        if file_id not in group["file_ids"]:
            group["file_ids"].append(file_id)

        if group["timer"] and not group["timer"].done():
            group["timer"].cancel()

        group["timer"] = asyncio.create_task(self._delayed_finalize(group_id))

    async def _delayed_finalize(self, group_id: str) -> None:
        try:
            await asyncio.sleep(FINALIZE_DELAY)
            if group_id in self._groups:
                group = self._groups.pop(group_id)
                await group["callback"](group_id, group["file_ids"], group["message"])
        except asyncio.CancelledError:
            pass

    @staticmethod
    async def get_photo_bytes(file_id: str, bot) -> bytes:
        buf = await bot.download(file_id)
        return buf.read()


# ─── PDF helpers ──────────────────────────────────────────────────────────────

def store_pdf_cache(user_id: int, photos: List[bytes]) -> None:
    _pdf_cache[user_id] = photos


def pop_pdf_cache(user_id: int) -> Optional[List[bytes]]:
    return _pdf_cache.pop(user_id, None)


async def convert_pdf_to_images(pdf_bytes: bytes, max_pages: int = 10) -> List[bytes]:
    loop = asyncio.get_event_loop()

    def _sync() -> List[bytes]:
        from pdf2image import convert_from_bytes  # lazy import — optional dep
        images = convert_from_bytes(pdf_bytes, last_page=max_pages, fmt="jpeg", dpi=150)
        result = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            result.append(buf.getvalue())
        return result

    return await loop.run_in_executor(None, _sync)
