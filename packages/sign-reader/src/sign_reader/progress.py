from rich.console import RenderableType
from rich.progress import BarColumn, SpinnerColumn, Task
from rich.progress_bar import ProgressBar
from rich.text import Text


class ConditionalSpinner(SpinnerColumn):
    """Only renders for tasks with use_spinner=True."""

    def render(self, task: Task) -> RenderableType:
        if task.fields.get("use_spinner"):
            return super().render(task)
        return Text("")  # blank for bar tasks


class ConditionalBar(BarColumn):
    """Only renders for tasks with use_spinner=False (or unset)."""

    # Ignoring the override that allows RenderableType
    def render(self, task: Task) -> ProgressBar | RenderableType:  # type: ignore[override]
        if not task.fields.get("use_spinner"):
            return super().render(task)
        return Text("")
