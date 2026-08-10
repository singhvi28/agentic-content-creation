#!/usr/bin/env python3
"""Seed bandit arms (also runs automatically on API startup)."""

import asyncio

from app.db.session import AsyncSessionLocal, init_db
from app.services.bandit_service import seed_bandit_arms


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_bandit_arms(session)
    print("Bandit arms seeded.")


if __name__ == "__main__":
    asyncio.run(main())