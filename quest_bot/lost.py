CODE = [4, 8, 15, 16, 23, 42]


def enter(now, rules, rng):
    buttons = CODE.copy()
    rng.shuffle(buttons)
    return {"kind": "lost", "deadline": now + rules.lost_timeout,
            "entered": [], "buttons": buttons}


def step(game, number, now, rules, flags=None):
    if now >= game["deadline"]:
        return rules.lost_lose
    if type(number) is not int or number not in CODE:
        raise ValueError("Неверная числовая кнопка")
    game["entered"].append(number)
    if game["entered"] != CODE[:len(game["entered"])]:
        return rules.lost_lose
    if game["entered"] == CODE:
        return rules.lost_win if (flags or {}).get("death_after_lost", False) else rules.lost_win_safe
    return None
