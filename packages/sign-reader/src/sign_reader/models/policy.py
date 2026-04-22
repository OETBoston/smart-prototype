"""
A Policy object is a rule that allows or prohibits a particular set of users
from using a particular curb at a particular time or times.

Multiple Policy objects together define the full extent of regulations.

"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_serializer

from .rule import Rule
from .timespan import TimeSpan


class Policy(BaseModel):
    policy_id: str | None = None
    name: str | None = None
    description: str | None = None
    published_date: int | None = None
    priority: int | None = None
    rules: List[Rule] = Field(
        ...,
        description=(
            "One or more rules describing what activities are allowed/forbidden,"
            "and the user types to which these rules apply. "
            "Rules can be positive ('parking', 'loading') or negative ('no parking', 'no loading'). "  # noqa E501
            "If a sign says 'EV PARKING ONLY', this would be a negative rule with activity 'no parking' "  # noqa E501
            "and user_classes_except ['electric']."
        ),
    )

    @field_validator("rules", mode="after")
    @classmethod
    def sort_rules(cls, v: List[Rule]) -> List[Rule]:
        if not v:
            return v
        return sorted(
            v,
            key=lambda rule: (
                rule.activity,
                rule.max_stay or 0,
                rule.max_stay_unit,
                # rule.no_return or 0,
                # rule.no_return_unit,
                tuple(rule.user_classes or ()),
                tuple(rule.user_classes_except or ()),
            ),
        )

    time_spans: List[TimeSpan] = Field(
        description=("The times at which the curb rules are in effect."),
    )

    @field_validator("time_spans", mode="after")
    @classmethod
    def sort_time_spans(cls, v: Optional[List[TimeSpan]]) -> Optional[List[TimeSpan]]:
        if not v:
            return v

        return sorted(
            v,
            key=lambda ts: (
                # ts.start_date or 0,
                # ts.end_date or 0,
                tuple(ts.days_of_week or ()),
                # tuple(ts.days_of_month or ()),
                tuple(ts.weeks_of_month or ()),
                tuple(ts.months or ()),
                ts.time_of_day_start or "",
                ts.time_of_day_end or "",
                ts.designated_period or "",
                # ts.designated_period_except or False,
            ),
        )

    @model_serializer(when_used="json")
    def serialize_model(self) -> dict:
        data = dict()
        data["priority"] = self.priority
        data["rules"] = self.rules
        # data = {
        #     "rules": self.rules,
        # }

        if self.time_spans and any(
            ts.model_dump(exclude_none=True) for ts in self.time_spans
        ):
            data["time_spans"] = self.time_spans

        return data
