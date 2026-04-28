from google.genai.types import ThinkingLevel
from pydantic import BaseModel, Field, model_validator

# Useful Defaults for Sign Reader
_GEMINI_DEFAULTS = {
    "model": "gemini-3-flash-preview",
    "temperature": 0,
    "thinking_level": "low",
    "include_thoughts": False,
    "mock_ai": False,
}


class ModelOptions(BaseModel):
    """Base class for Configuring Multimodal Language Models.
    Implmentation is on a per-model basis.
    """

    ...


class GeminiOptions(ModelOptions):
    model: str = Field(default=_GEMINI_DEFAULTS["model"])
    temperature: float = Field(default=_GEMINI_DEFAULTS["temperature"], ge=0, le=2)
    thinking_level: ThinkingLevel | None = Field(
        default=_GEMINI_DEFAULTS["thinking_level"]
    )
    include_thoughts: bool | None = Field(default=_GEMINI_DEFAULTS["include_thoughts"])
    mock_ai: bool = Field(default=_GEMINI_DEFAULTS["mock_ai"])

    @model_validator(mode="after")
    def validate_thinking_level(self) -> "GeminiOptions":
        """Adjusts Thinking Levels based on Model Support"""
        model = self.model
        self.thinking_level = (
            None if self.thinking_level is None else ThinkingLevel(self.thinking_level)
        )

        # Thinking Level is only supported by Gemini 3+
        if model.startswith("gemini-2") and self.thinking_level:
            self.thinking_level = None
        # Gemini 3 Pro Models don't support "minimimal". Reset to Low.
        elif model.endswith("-pro") and self.thinking_level == ThinkingLevel.MINIMAL:
            self.thinking_level = ThinkingLevel.LOW

        return self
