from typing import Literal

from pydantic import BaseModel, Field, model_validator

_GEMINI_DEFAULTS = {
    "model": "gemini-3-flash-preview",
    "temperature": 0,
    "thinking_level": None,
    "include_thoughts": False,
}


class ModelConfig(BaseModel):
    """Base class for Configuring Multimodal Language Models.
    Implmentation is on a per-model basis.
    """

    ...


class GeminiModelConfig(ModelConfig):
    model: str = Field(default=_GEMINI_DEFAULTS["model"])
    temperature: float = Field(default=_GEMINI_DEFAULTS["temperature"])
    thinking_level: Literal["minimal", "low", "medium", "high", "dynamic"] | None = (
        Field(default=_GEMINI_DEFAULTS["thinking_level"])
    )
    include_thoughts: bool | None = Field(default=_GEMINI_DEFAULTS["include_thoughts"])
    system_instructions: str

    @model_validator(mode="after")
    def validate_thinking_level(self) -> "GeminiModelConfig":
        """Adjusts Thinking Levels based on Model Support"""
        model = self.model
        thinking_level = self.thinking_level

        # Thinking Level is only supported by Gemini 3+
        if model.startswith("gemini-2") and thinking_level:
            self.thinking_level = None
        # Gemini 3 Pro Models don't support "minimimal". Reset to Low.
        elif model.endswith("-pro") and thinking_level == "minimal":
            self.thinking_level = "low"

        return self
