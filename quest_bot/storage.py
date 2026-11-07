import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
import time

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.pool import StaticPool

from .models import State


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id = mapped_column(BigInteger, primary_key=True)


class Session(Base):
    __tablename__ = "sessions"
    user_id = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    current_scene_id = mapped_column(Integer, nullable=False)
    flags = mapped_column(JSON, nullable=False)
    player_hp = mapped_column(Integer, nullable=True)
    enemy_hp = mapped_column(Integer, nullable=True)
    battle_active = mapped_column(Boolean, nullable=False)
    minigame_state = mapped_column(JSON, nullable=True)
    state = mapped_column(JSON, nullable=False)


class OpenedEnding(Base):
    __tablename__ = "opened_endings"
    user_id = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    ending_id = mapped_column(Integer, primary_key=True)
    opened_at = mapped_column(DateTime(timezone=True), nullable=False)


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    user_id = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    scene_id = mapped_column(Integer, nullable=False)
    flags = mapped_column(JSON, nullable=False)


class Store:
    def __init__(self, url, clock=time.time):
        self.clock = clock
        self._init_lock = asyncio.Lock()
        self.engine = create_async_engine(url)
        # In-memory SQLite выдает одно соединение всем сессиям.
        self._connection_lock = (asyncio.Lock() if isinstance(self.engine.pool, StaticPool)
                                 else nullcontext())
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine.sync_engine, "connect")
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self):
        async with self._init_lock:
            async with self._connection_lock, self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

    async def read(self, uid):
        async with self._connection_lock, self.session() as db:
            row = await db.get(Session, uid)
            endings = set(await db.scalars(
                select(OpenedEnding.ending_id).where(OpenedEnding.user_id == uid)
            ))
            return (State.model_validate(row.state) if row else None), endings

    async def write(self, uid, state, endings):
        async with self._connection_lock, self.session.begin() as db:
            await db.merge(User(user_id=uid))
            await db.flush()
            battle = state.battle or {}
            await db.merge(Session(
                user_id=uid, current_scene_id=state.scene, flags=state.flags,
                player_hp=battle.get("hp"), enemy_hp=battle.get("ehp"),
                battle_active=bool(battle), minigame_state=state.game,
                state=state.model_dump(),
            ))
            for ending_id in endings:
                if await db.get(OpenedEnding, (uid, ending_id)) is None:
                    db.add(OpenedEnding(
                        user_id=uid, ending_id=ending_id,
                        opened_at=datetime.fromtimestamp(self.clock(), timezone.utc),
                    ))

    async def save_checkpoint(self, uid, state):
        async with self._connection_lock, self.session.begin() as db:
            await db.merge(User(user_id=uid))
            await db.flush()
            await db.merge(Checkpoint(user_id=uid, scene_id=state.scene, flags=state.flags))

    async def checkpoint(self, uid):
        async with self._connection_lock, self.session() as db:
            row = await db.get(Checkpoint, uid)
            return (row.scene_id, dict(row.flags)) if row else None

    async def close(self):
        await self.engine.dispose()
