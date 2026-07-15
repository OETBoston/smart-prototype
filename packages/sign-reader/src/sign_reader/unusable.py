from sign_reader.models import (
    ImageExtended,
    PolicyExtended,
    RuleExtended,
    SignExtended,
    TimeSpan,
    Unusable,
)


def unusable_image() -> ImageExtended:
    # Define the unusable policy
    return ImageExtended(
        signs=[
            SignExtended(
                policy=PolicyExtended(
                    priority=98,
                    time_spans=[
                        TimeSpan(
                            days_of_week=[
                                "sun",
                                "mon",
                                "tue",
                                "wed",
                                "thu",
                                "fri",
                                "sat",
                            ],
                            time_of_day_end="00:00",
                            time_of_day_start="00:00",
                        )
                    ],
                    rules=[
                        RuleExtended(
                            activity=Unusable("unusable image"),
                        )
                    ],
                )
            )
        ]
    )
