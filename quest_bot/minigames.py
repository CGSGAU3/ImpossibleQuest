from . import drunk, lost


def enter(choice, now, rng, rules):
    if choice.room == "drunk":
        return drunk.enter(choice.win, choice.lose, now, rng)
    if choice.room == "lost":
        return lost.enter(now, rules, rng)
    raise ValueError("Неизвестная мини-игра")


def step(game, value, now, rules, flags=None):
    if game["kind"] == "drunk":
        return drunk.step(game, value)
    if game["kind"] == "lost":
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError as error:
                raise ValueError("Неверная числовая кнопка") from error
        return lost.step(game, value, now, rules, flags)
    raise ValueError("Неизвестная мини-игра")
