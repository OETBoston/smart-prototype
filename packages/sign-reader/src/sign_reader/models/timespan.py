"""TimeSpan model definition for parking sign policy schedules.

https://github.com/openmobilityfoundation/curb-data-specification/tree/main/curbs#time-span

A Time Span defines a period of time (that may occur once or repeatedly) during which a
given regulation applies.

When multiple fields are combined, all criteria must be met in order for a given
Time Span to apply. For instance, the following Time Span represents 10AM to 1PM on
Mondays and Tuesdays:

{
  "days_of_week": ["mon", "tue"],
  "time_of_day_start": "10:00",
  "time_of_day_end": "13:00"
}
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_serializer
from typing_extensions import Annotated


class TimeSpan(BaseModel):
    # CURRENTLY NOT IMPLEMENTED FOR BOSTON CDS
    # start_date: Optional[int] = Field(
    #     default=None,
    #     description=(
    #         "The earliest point in time that this TimeSpan could apply (inclusive), "
    #         "represented as a timestamp in milliseconds since Unix epoch. "
    #         "If unspecified, the Time Span applies to all matching periods arbitrarily "  #noqa E501
    #         "far in the past."
    #     ),
    # )

    # CURRENTLY NOT IMPLEMENTED FOR BOSTON CDS
    # end_date: Optional[int] = Field(
    #     default=None,
    #     description=(
    #         "The latest point in time that this TimeSpan could apply (exclusive), "
    #         "represented as a timestamp in milliseconds since Unix epoch. "
    #         "If unspecified, the Time Span applies to all matching periods arbitrarily " # noqa E501
    #         "far in the future."
    #     ),
    # )

    days_of_week: List[Literal["sun", "mon", "tue", "wed", "thu", "fri", "sat"]] = (
        Field(
            description=(
                "List of days of the week when this policy applies. "
                "TUESDAY AND THURSDAY means days_of_week ['tue', 'thu'] "
                "EXCEPT SUNDAY means days_of_week ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'] "  # noqa E501
            ),
        )
    )

    @field_validator("days_of_week", mode="after")
    @classmethod
    def sort_days_of_week(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        order = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
        sorted_days = sorted(v, key=lambda day: order.index(day))
        # Drop if full week
        # if sorted_days == order:
        #     return None
        return sorted_days

    # NOT IMPLMENTED FOR BOSTON CDS
    # days_of_month: Optional[List[Annotated[int, Field(ge=1, le=31)]]] = Field(
    #     default=None,
    #     description=(
    #         "List of days of the month this policy applies as an integer (1-31) "
    #         "For example, [1, 15] would indicate the policy only applies on "
    #         "the 1st and 15th days of the month."
    #     ),
    # )

    # @field_validator("days_of_month", mode="after")
    # @classmethod
    # def sort_days_of_month(cls, v: Optional[List[int]]) -> Optional[List[int]]:
    #     if v is None:
    #         return v
    #     return sorted(v)

    weeks_of_month: Optional[List[Annotated[int, Field(ge=1, le=5)]]] = Field(
        default=None,
        description=(
            "List of weeks of the month when this Time Span applies, "
            "specified as integers (1-5), to represent ordinal weeks. "
            "E.g. '2' would be the 2nd week of the month."
        ),
    )

    @field_validator("weeks_of_month", mode="after")
    @classmethod
    def sort_weeks_of_month(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return v
        return sorted(v)

    months: Optional[List[Annotated[int, Field(ge=1, le=12)]]] = Field(
        default=None,
        description="If specified, this policy only applies only during these months "
        "(1=January, 12=December).",
    )

    @field_validator("months", mode="after")
    @classmethod
    def sort_months(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return v
        sorted_months = sorted(v)
        # Drop if full year
        if sorted_months == list(range(1, 13)):
            return None
        return sorted_months

    time_of_day_start: str = Field(
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description=(
            "The 24-hour local time that this policy starts to apply (inclusive), "
            "formatted as HH:MM. "
        ),
    )

    time_of_day_end: str = Field(
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description=(
            "The 24-hour local time that this policy stops applying (exclusive), "
            "formatted as HH:MM. "
        ),
    )

    designated_period: Optional[
        List[Literal["snow emergency", "holidays", "game days", "school days"]]
    ] = Field(
        default=None,
        description=(
            "If specified, this policy only applies on these general types of days."
        ),
    )

    # CURRENTLY NOT IMPLEMENTED FOR BOSTON CDS
    # designated_period_except: Optional[bool] = Field(
    #     default=None,
    #     description=(
    #         "If specified, this policy does NOT apply on these general types of days. " # noqa E501
    #     ),
    # )

    @model_serializer(when_used="json")
    def serialize_model(self) -> dict:
        data = {
            # "start_date": self.start_date,
            # "end_date": self.end_date,
            "days_of_week": self.days_of_week,
            # "days_of_month": self.days_of_month,
            "weeks_of_month": self.weeks_of_month,
            "months": self.months,
            "time_of_day_start": self.time_of_day_start,
            "time_of_day_end": self.time_of_day_end,
            "designated_period": self.designated_period,
            # "designated_period_except": self.designated_period_except,
        }

        return {
            k: v
            for k, v in data.items()
            if v is not None and (not isinstance(v, list) or len(v) > 0)
        }
