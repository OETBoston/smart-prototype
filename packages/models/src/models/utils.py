from pathlib import Path


def load_from_txt(path: Path | str) -> str:
    """Load a text file. Useful for reading in prompts and instructions
    Raises FileNotFound if path does not exist."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot find path to text file {path}")
    with open(path, "r") as f:
        text = f.read().strip()
    return text
