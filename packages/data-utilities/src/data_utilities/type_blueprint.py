# utilities/data_utilities/type_blueprint.py

from typing import Callable, Any, Optional
import pydantic_core
from pydantic import GetCoreSchemaHandler

class PydanticTypeBlueprint(str):
    """
    Base for creating Pydantic types with pluggable recognizers.

    Subclass this to define domain-specific normalized types.
    """
    __recognizers__: list[Callable[[Any], Optional[str]]] = []
    __default_error__: str = "Unrecognized input"

    @classmethod
    def register(cls, func):
        print("adding recognizer: ",func)
        cls.__recognizers__.append(func)
        return func

    @classmethod
    def normalize(cls, value):
        if value is None:
            return None

        for recognizer in cls.__recognizers__:
            try:
                out = recognizer(value)
                if out is not None:
                    return out
            except Exception:
                pass

        raise ValueError(f"{cls.__default_error__}: {value!r}")

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        def validate(value):
            return cls.normalize(value)

        return pydantic_core.core_schema.no_info_plain_validator_function(validate)
