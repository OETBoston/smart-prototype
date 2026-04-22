"""
A rule defines who is allowed to do what, and for how long, on a curb, per the policy.
"""

from typing import List, Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from .enums import Activity, Purposes, UserClass


class Rule(BaseModel):
    activity: Activity = Field(
        ...,
        description=("The activity that is forbidden or permitted by this regulation."),
    )

    max_stay: Optional[int] = Field(
        default=None,
        description=(
            "A time limit placed on the activity. 2 HOUR PARKING means max_stay is 2"
        ),
    )

    # In CDS v1.1, other values (second through year) are permitted.
    # For on-street use cases, we limit allowable values to minute/hour.
    max_stay_unit: Optional[Literal["minute", "hour"]] = Field(
        default=None,
        description=(
            "Unit of time associated a maximum stay (e.g. hour or minute)."
            "Never include unless max_stay is defined."
        ),
    )

    # no_return: Optional[int] = Field(
    #     default=0,
    #     description=(
    #         "The length of time (in units of no_return_unit) that a user must "
    #         "vacate before being allowed to return for another stay. Defaults to 0."
    #     ),
    # )

    # no_return_unit: Optional[
    #     Literal["minute", "hour"]
    # ] = Field(
    #     default=None,
    #     description="The Unit of Time associated with the no_return value.",
    # )

    purposes: Optional[List[Purposes]] = Field(
        ..., description=("The purposes to which this rule applies.")
    )

    @field_validator("purposes", mode="after")
    @classmethod
    def sort_purposes(cls, v: List[Purposes] | None) -> List[Purposes] | None:
        if v is None:
            return v
        enum_position_map = {member: i for i, member in enumerate(Purposes)}
        return sorted(v, key=lambda x: enum_position_map.get(x))

    user_classes: Optional[List[UserClass]] = Field(
        default=None,
        description=(
            "List of types of user to which this rule applies."
            "Almost always a single type of vehicle."
        ),
    )

    @field_validator("user_classes", mode="after")
    @classmethod
    def sort_user_classes(
        cls, v: Optional[List[UserClass]]
    ) -> Optional[List[UserClass]]:
        if v is None:
            return v
        enum_position_map = {member: i for i, member in enumerate(UserClass)}
        return sorted(v, key=lambda x: enum_position_map.get(x))

    user_classes_except: Optional[List[UserClass]] = Field(
        default=None,
        description=(
            "A list of types of users who are explicitly exempted from this rule."
        ),
    )

    @field_validator("user_classes_except", mode="after")
    @classmethod
    def sort_user_classes_except(
        cls, v: Optional[List[UserClass]]
    ) -> Optional[List[UserClass]]:
        if v is None:
            return v
        member_order = {member: i for i, member in enumerate(UserClass)}
        return sorted(v, key=lambda x: member_order.get(x))

    @model_validator(mode="after")
    def convert_minutes_to_hours(self) -> "Rule":
        # Convert max_stay if needed
        if self.max_stay is not None and self.max_stay != 0:
            if self.max_stay % 60 == 0 and self.max_stay_unit == "minute":
                self.max_stay = self.max_stay // 60
                self.max_stay_unit = "hour"
        # Convert no_return if needed
        # if self.no_return is not None and self.no_return != 0:
        #     if self.no_return % 60 == 0 and self.no_return_unit == "minute":
        #         self.no_return = self.no_return // 60
        #         self.no_return_unit = "hour"
        return self

    @model_serializer(when_used="json")
    def serialize_model(self) -> dict:
        data = {
            "activity": self.activity,
            "max_stay": self.max_stay,
            "max_stay_unit": self.max_stay_unit,
            # "no_return": self.no_return,
            # "no_return_unit": self.no_return_unit,
            "purposes": self.purposes,
            "user_classes": self.user_classes,
            "user_classes_except": self.user_classes_except,
        }

        if self.max_stay is None:
            data.pop("max_stay", None)
            data.pop("max_stay_unit", None)

        # if self.no_return is None or self.no_return == 0:
        #     data.pop("no_return", None)
        #     data.pop("no_return_unit", None)

        if not self.purposes:
            data.pop("purposes", None)

        for field in ["user_classes", "user_classes_except"]:
            if not data.get(field):  # Catches both None and []
                data.pop(field, None)

        return data
