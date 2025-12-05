# utilities/data_utilities/auto_filters.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Type, get_args, get_origin, Union, List

from pydantic import BaseModel
from pydantic.config import ConfigDict


def _unwrap_optional(tp: Any) -> tuple[Any, bool]:
    """
    If tp is Optional[T] / Union[T, None], return (T, True).
    Otherwise return (tp, False).
    """
    origin = get_origin(tp)
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return tp, False


def create_filter_model(entity_cls: Type[BaseModel]) -> Type[BaseModel]:
    """
    Dynamically generates a Pydantic Filter model for the given entity_cls.

    - Includes filter fields for every entity field (exact, range, etc.).
    - Adds minimal: bool flag for projection control.
    """

    annotations: Dict[str, Any] = {}
    defaults: Dict[str, Any] = {}

    for name, field in entity_cls.model_fields.items():
        base_type, _ = _unwrap_optional(field.annotation)

        # --- 1. exact match ---
        annotations[name] = base_type | None
        defaults[name] = None

        # included flag (for projection)
        annotations[f"{name}_included"] = bool | None
        defaults[f"{name}_included"] = None

        # --- 2. string operators ---
        if base_type is str:
            for suffix in ("_contains", "_prefix", "_suffix"):
                annotations[f"{name}{suffix}"] = str | None
                defaults[f"{name}{suffix}"] = None

        # --- 3. numeric operators ---
        if base_type in (int, float):
            for suffix in ("_min", "_max", "_gt", "_lt", "_gte", "_lte"):
                annotations[f"{name}{suffix}"] = base_type | None
                defaults[f"{name}{suffix}"] = None

        # --- 4. datetime operators ---
        if base_type is datetime:
            annotations[f"{name}_after"] = datetime | None
            defaults[f"{name}_after"] = None

            annotations[f"{name}_before"] = datetime | None
            defaults[f"{name}_before"] = None

    # --- 5. minimal flag ---
    annotations["minimal"] = bool | None
    defaults["minimal"] = None

    filter_name = f"{entity_cls.__name__}Filter"

    namespace = {
        "__annotations__": annotations,
        "model_config": ConfigDict(extra="forbid"),
        **defaults,
    }

    return type(filter_name, (BaseModel,), namespace)



def with_auto_filter(entity_cls: Type[BaseModel]) -> Type[BaseModel]:
    """
    Class decorator that attaches an auto-generated `Filter`
    model to the entity class.
    """
    # Note: Use a more specific type hint if possible in a real project
    entity_cls.Filter = create_filter_model(entity_cls)  # type: ignore[attr-defined]
    return entity_cls