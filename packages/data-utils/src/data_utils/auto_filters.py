# utilities/data_utils/auto_filters.py

from __future__ import annotations

import logging
from datetime import datetime
from types import UnionType
from typing import Any, Dict, Type, Union, get_args, get_origin

from pydantic import BaseModel, model_validator
from pydantic.config import ConfigDict

logger = logging.getLogger("auto_filter")
logger.addHandler(logging.NullHandler())


def _unwrap_optional(tp):
    origin = get_origin(tp)

    # typing.Union[str, None]
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True

    # PEP 604 union: str | None  → origin is types.UnionType
    if origin is UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True

    return tp, False


def create_filter_model(entity_cls: Type[BaseModel]) -> Type[BaseModel]:
    annotations: Dict[str, Any] = {}
    defaults: Dict[str, Any] = {}

    logger.debug(f"\n\n=== Building filter for {entity_cls.__name__} ===")

    for name, field in entity_cls.model_fields.items():
        logger.debug(f"\nField: {name}")
        logger.debug(f"  Raw annotation: {field.annotation!r}")

        base_type, optional = _unwrap_optional(field.annotation)

        logger.debug(f"  Unwrapped base_type: {base_type!r}")
        logger.debug(f"  optional?: {optional}")

        # --- 1. exact match ---
        annotations[name] = base_type | None
        defaults[name] = None
        logger.debug(f"  -> Added exact match field: {name}: {annotations[name]}")

        # included flag
        annotations[f"{name}_included"] = bool | None
        defaults[f"{name}_included"] = None
        logger.debug(f"  -> Added included flag field: {name}_included")

        # --- 2. string operators ---
        if base_type == str:
            logger.debug(f"  -> STRING FIELD DETECTED for {name}, adding suffix ops!")
            for suffix in ("_contains", "_prefix", "_suffix"):
                op_name = f"{name}{suffix}"
                annotations[op_name] = str | None
                defaults[op_name] = None
                logger.debug(f"     Added string op: {op_name}")
        else:
            logger.debug(f"  -> NOT a string field (base_type={base_type!r})")

        # --- 3. numeric ---
        if base_type in (int, float):
            logger.debug(f"  -> NUMERIC FIELD DETECTED for {name}, adding numeric ops!")
            for suffix in ("_min", "_max", "_gt", "_lt", "_gte", "_lte"):
                op_name = f"{name}{suffix}"
                annotations[op_name] = base_type | None
                defaults[op_name] = None
                logger.debug(f"     Added numeric op: {op_name}")

        # --- 4. datetime ---
        if base_type == datetime:
            logger.debug(
                f"  -> DATETIME FIELD DETECTED for {name}, adding datetime ops!"
            )
            annotations[f"{name}_after"] = datetime | None
            defaults[f"{name}_after"] = None
            logger.debug(f"     Added datetime op: {name}_after")

            annotations[f"{name}_before"] = datetime | None
            defaults[f"{name}_before"] = None
            logger.debug(f"     Added datetime op: {name}_before")

    # minimal flag
    annotations["minimal"] = bool | None
    defaults["minimal"] = None
    logger.debug("Added minimal flag")

    filter_name = f"{entity_cls.__name__}Filter"
    logger.debug(f"=== Finished filter model: {filter_name} ===\n\n")

    namespace = {
        "__annotations__": annotations,
        "model_config": ConfigDict(extra="forbid"),
        **defaults,
    }

    # Validator: minimal=True requires at least one included field
    @model_validator(mode="after")
    def _validate_minimal(self):
        if getattr(self, "minimal", False):
            included_fields = [
                name
                for name in entity_cls.model_fields
                if getattr(self, f"{name}_included", None)
            ]
            if not included_fields:
                raise ValueError(
                    f"{filter_name}: minimal=True requires at least one <field>_included=True"
                )
        return self

    namespace["_validate_minimal"] = _validate_minimal

    return type(filter_name, (BaseModel,), namespace)


def with_auto_filter(entity_cls: Type[BaseModel]) -> Type[BaseModel]:
    """
    Class decorator that attaches an auto-generated `Filter`
    model to the entity class.
    """
    # Note: Use a more specific type hint if possible in a real project
    entity_cls.Filter = create_filter_model(entity_cls)  # type: ignore[attr-defined]
    return entity_cls
