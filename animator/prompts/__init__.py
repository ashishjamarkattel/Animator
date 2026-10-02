"""Every LLM prompt the package sends, as editable text templates.

Templates use str.format placeholders, e.g. {idea}. Code that fills them lives
next to the call that sends them, in animator/gemini/.
"""
from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return the template `prompts/<name>.txt` without surrounding whitespace."""
    return files(__package__).joinpath(f"{name}.txt").read_text(encoding="utf-8").strip()
