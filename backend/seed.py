"""Seed script to create default admin user and initial system config."""
import asyncio

from sqlalchemy import select

from app.database import async_session_factory, engine, Base
from app.models import User, UserRole, SystemConfig
from app.core.security import hash_password


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        # Create admin user if not exists
        result = await db.execute(select(User).where(User.email == "admin@example.com"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role=UserRole.admin,
                is_active=True,
            )
            db.add(admin)

        # Default system config
        defaults = {
            "chunk_size": {"value": 512},
            "chunk_overlap": {"value": 64},
            "similarity_threshold": {"value": 0.75},
            "max_retrieval_count": {"value": 5},
            "chat_model": {"value": "gpt-4"},
            "embedding_model": {"value": "text-embedding-ada-002"},
        }
        for key, value in defaults.items():
            result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
            if not result.scalar_one_or_none():
                db.add(SystemConfig(key=key, value=value))

        await db.commit()
        print("Seed completed: admin user and system config created.")


if __name__ == "__main__":
    asyncio.run(seed())
