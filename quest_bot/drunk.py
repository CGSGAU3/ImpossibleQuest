PRE_LABELS = ("я пьяный ты пьяный", "а где тут туалет", "а чиво все крутица")
ROUNDS = [
    ("КОТ", "Любитель ловить мышей"),
    ("ВОДА", "Самое распространенное вещество на земле"),
    ("АРГОН", "18-ый элемент периодической таблицы"),
]
LETTERS = list("КОТВДАРГН")


def enter(win, lose, now, rng):
    letters = LETTERS.copy()
    rng.shuffle(letters)
    return {"kind": "drunk", "round": 0, "word": "", "letters": letters,
            "win": win, "lose": lose, "shuffled": now}


def step(game, letter):
    if letter not in LETTERS:
        raise ValueError("Эта буква недоступна")
    word = game["word"] + letter
    target = ROUNDS[game["round"]][0]
    if not target.startswith(word):
        return game["lose"]
    game["word"] = word
    if word == target:
        game["round"] += 1
        game["word"] = ""
        if game["round"] == len(ROUNDS):
            return game["win"]
    return None
