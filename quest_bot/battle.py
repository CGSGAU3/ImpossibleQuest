def enter(choice):
    return {
        "hp": 10,
        "ehp": 7,
        "hit": choice.hit,
        "miss": choice.hit_by_enemy,
        "win": choice.win,
        "lose": choice.lose,
    }


def step(battle, index, rng):
    if type(index) is not int or not 0 <= index < 3:
        raise ValueError("Неверное действие в бою")
    hit = index + 1 == rng.randint(1, 3)
    battle["ehp" if hit else "hp"] -= 1
    if battle["ehp"] == 0:
        return battle["win"], True
    if battle["hp"] == 0:
        return battle["lose"], True
    return battle["hit" if hit else "miss"], False
