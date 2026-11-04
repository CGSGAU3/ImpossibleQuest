import random

import pytest

from quest_bot.application import Application
from quest_bot.content import load_content
from quest_bot.models import Rules
from quest_bot.sessions import SessionManager
from quest_bot.storage import Store
from quest_bot.story import StoryEngine


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FixedRandom(random.Random):
    def randint(self, low, high):
        return 1


@pytest.fixture
async def b_kit(tmp_path):
    clock = Clock()
    store = Store(f"sqlite+aiosqlite:///{tmp_path}/telegram-tests.db", clock=clock)
    await store.init()
    story = StoryEngine(load_content(), FixedRandom(42), clock, Rules())
    sessions = SessionManager(store, story)
    app = Application(sessions)
    yield app, sessions, story, clock, store
    await store.close()


async def position(kit, scene, uid=1):
    app, sessions, story, *_ = kit
    await sessions.get(uid)
    state = story.new()
    state.scene = scene
    story.arrive(state)
    return await sessions.put(uid, state)
