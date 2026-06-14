import asyncio
from typing import Optional

import openai

from app.config import get_settings

settings = get_settings()

_semaphore = asyncio.Semaphore(10)


def _get_client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    embeddings = []

    # Process in batches of 20 (OpenAI limit is higher but 20 is safe)
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        async with _semaphore:
            response = await client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
            )
        embeddings.extend([item.embedding for item in response.data])

    return embeddings


async def generate_single_embedding(text: str) -> list[float]:
    result = await generate_embeddings([text])
    return result[0]
