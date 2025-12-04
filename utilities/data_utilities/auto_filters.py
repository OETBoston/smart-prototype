# utilities/data_utilities/auto_filters.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Type, get_args, get_origin, Union

from pydantic import BaseModel
from pydantic.config import ConfigDict  # or from pydantic import ConfigDict in v2.5+


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

    - Includes exact-match fields for every entity field
    - Adds suffix-based filter fields depending on the underlying type:
        * str:     _contains, _prefix, _suffix
        * int/float: _min, _max, _gt, _lt, _gte, _lte
        * datetime:  _after, _before
        * bool/other: exact match only
    """

    annotations: Dict[str, Any] = {}
    defaults: Dict[str, Any] = {}

    for name, field in entity_cls.model_fields.items():
        base_type, _ = _unwrap_optional(field.annotation)

        # --- 1. exact match ---
        annotations[name] = base_type | None
        defaults[name] = None

        # --- 2. string operators ---
        if base_type is str:
            annotations[f"{name}_contains"] = str | None
            defaults[f"{name}_contains"] = None

            annotations[f"{name}_prefix"] = str | None
            defaults[f"{name}_prefix"] = None

            annotations[f"{name}_suffix"] = str | None
            defaults[f"{name}_suffix"] = None

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

        # --- 5. booleans & everything else ---
        # get exact match only (already added). No extra suffixes.

    filter_name = f"{entity_cls.__name__}Filter"

    namespace: Dict[str, Any] = {
        "__annotations__": annotations,
        "model_config": ConfigDict(extra="forbid"),
    }
    namespace.update(defaults)

    filter_cls = type(filter_name, (BaseModel,), namespace)
    return filter_cls




def with_auto_filter(entity_cls: Type[BaseModel]) -> Type[BaseModel]:
    """
    Class decorator that attaches an auto-generated `Filter`
    model to the entity class.
    """
    entity_cls.Filter = create_filter_model(entity_cls)  # type: ignore[attr-defined]
    return entity_cls
