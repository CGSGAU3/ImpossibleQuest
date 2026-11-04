import random

import pytest

from quest_bot.content import load_content
from quest_bot.models import Quest, Rules
from quest_bot.story import StoryEngine


class CoreClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def core_clock():
    return CoreClock()


@pytest.fixture
def core_engine(core_clock):
    return StoryEngine(load_content(), random.Random(7), core_clock, Rules())


@pytest.fixture
def small_engine(core_clock):
    content = Quest.model_validate({
        "start": 1,
        "secret_ending": 4,
        "scenes": {
            1: {"type": "scene", "text": "Начало", "choices": [
                {"text": "Дальше", "next": 2, "flags": {"seen": True}},
                {"text": "По флагу", "next": 3, "flags_required": {"seen": True}},
                {"text": "Случайно", "note": "random_choice", "options": [2, 3]},
            ]},
            2: {"type": "scene", "text": "Условие", "choices": [{
                "text": "Проверить", "note": "conditional", "conditions": [
                    {"flags_required": {"seen": True}, "next": 3},
                    {"flags_required": {"seen": False}, "next": 4},
                ],
            }]},
            3: {"type": "scene", "text": "Назад", "choices": [{"text": "Начало", "next": 1}]},
            4: {"type": "ending", "text": "Конец", "choices": [], "ending_id": 1},
        },
    })
    return StoryEngine(content, random.Random(7), core_clock, Rules())
