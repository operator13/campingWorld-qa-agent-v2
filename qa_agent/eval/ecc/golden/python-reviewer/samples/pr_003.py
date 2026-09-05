"""Shopping cart utilities."""


def add_item(name: str, price: float, cart: list = []) -> list:
    cart.append({"name": name, "price": price})
    return cart


def add_tag(item: str, tags: list = []) -> list:
    if item not in tags:
        tags.append(item)
    return tags


def build_config(overrides: dict = {}) -> dict:
    config = {
        "debug": False,
        "timeout": 30,
        "retries": 3,
    }
    config.update(overrides)
    return config


def register_handler(event: str, handlers: dict = {}) -> None:
    if event not in handlers:
        handlers[event] = []
    handlers[event].append(f"handler_{event}")
