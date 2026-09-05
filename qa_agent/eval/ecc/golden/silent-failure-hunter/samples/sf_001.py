"""Background worker with bare except: pass."""
import time


def run_worker(tasks: list[dict]) -> list[str]:
    """Process tasks in a loop, silently swallowing all errors."""
    completed = []
    for task in tasks:
        try:
            result = execute_task(task)
            completed.append(result)
        except:
            pass
    return completed


def execute_task(task: dict) -> str:
    """Simulate task execution."""
    if not task.get("id"):
        raise ValueError("Task missing required 'id' field")
    time.sleep(0.01)
    return f"done:{task['id']}"
