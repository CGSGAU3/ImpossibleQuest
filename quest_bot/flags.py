def matches(flags, required):
    return all(flags.get(name, False) == value for name, value in required.items())


def apply(flags, updates):
    flags.update(updates)
