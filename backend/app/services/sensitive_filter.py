import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SensitiveWord


class SensitiveFilter:
    def __init__(self):
        self._words: list[str] = []
        self._pattern: Optional[re.Pattern] = None

    async def load_words(self, db: AsyncSession):
        result = await db.execute(
            select(SensitiveWord.word).where(SensitiveWord.is_active == True)
        )
        self._words = [row[0] for row in result.fetchall()]
        if self._words:
            escaped = [re.escape(w) for w in self._words]
            self._pattern = re.compile("|".join(escaped), re.IGNORECASE)
        else:
            self._pattern = None

    def contains_sensitive(self, text: str) -> tuple[bool, list[str]]:
        if not self._pattern:
            return False, []
        matches = self._pattern.findall(text)
        return len(matches) > 0, list(set(matches))

    def mask_sensitive(self, text: str) -> str:
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: "*" * len(m.group()), text)


sensitive_filter = SensitiveFilter()
