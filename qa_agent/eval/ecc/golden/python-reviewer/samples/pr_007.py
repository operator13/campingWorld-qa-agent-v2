"""Simple calculator service."""


def calculate(expression: str) -> float:
    """Evaluate a math expression from user input."""
    result = eval(expression)
    return float(result)


def batch_calculate(expressions: list[str]) -> list[float]:
    """Evaluate multiple expressions from user input."""
    results = []
    for expr in expressions:
        try:
            results.append(eval(expr))
        except Exception:
            results.append(0.0)
    return results


def apply_formula(data: dict, formula: str) -> float:
    """Apply a user-defined formula to data values."""
    for key, value in data.items():
        formula = formula.replace(key, str(value))
    return eval(formula)


def dynamic_filter(items: list[dict], condition: str) -> list[dict]:
    """Filter items using a user-provided condition string."""
    return [item for item in items if eval(condition, {"item": item})]
