from typing import Literal, Optional

from pydantic import BaseModel, Field, model_serializer

from .policy import Policy


class Sign(BaseModel):
    policy: Policy
    arrow: Optional[Literal["left", "right", "both", "none"]] = Field(
        default="none",
        description=(
            "Optional arrow direction on the sign. Allowed values are 'left', 'right', "
            "'both', or 'none'."
        ),
    )

    @model_serializer(when_used="json")
    def sort_model(self) -> dict:
        return {"arrow": self.arrow, "policy": self.policy}
