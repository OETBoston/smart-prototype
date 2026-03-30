from datetime import datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError
from pprint import pprint
from pydantic import BaseModel, ConfigDict

from data_utilities.accessor import DataAccessor
from data_utilities.queries_and_contracts import (
    SimpleEntityModel,
    SimpleEntityFilter,
)


@pytest.mark.integration
class TestFilterBrittleness:

    @pytest.fixture(scope="class")
    def accessor(self):
        """Load DataAccessor using application config."""
        return DataAccessor(config_path=".env")

    @pytest.fixture(scope="class", autouse=True)
    def seed_data(self, accessor):
        """
        Ensure the database has the entities needed by these tests.
        No cleanup on purpose.
        """
        now = datetime.utcnow()
        unique = str(uuid4())
        target_id = f"{unique}-Target"

        rows = [
            # Existing ones
            SimpleEntityModel(
                id=target_id,
                type="Target",
                time=now,
                location="POINT(1 1)",
            ),
            SimpleEntityModel(
                id=f"{unique}-Extra",
                type="Extra",
                time=now,
                location="POINT(2 2)",
            ),

            # For type_contains="bike"
            SimpleEntityModel(
                id=f"{unique}-Bike",
                type="MountainBike",         # "bike" in .lower()
                time=now,
                location="POINT(3 3)",
            ),

            # For type_prefix="ab"
            SimpleEntityModel(
                id=f"{unique}-Prefix",
                type="absolutely",           # startswith("ab")
                time=now,
                location="POINT(4 4)",
            ),

            # For type_suffix="zz"
            SimpleEntityModel(
                id=f"{unique}-Suffix",
                type="fizzbuzz",             # endswith("zz")
                time=now,
                location="POINT(5 5)",
            ),

            # For id="123" minimal projection tests
            SimpleEntityModel(
                id="123",
                type="MinimalIdType",
                time=now,
                location="POINT(6 6)",
            ),

            # Optional: for time_suffix=":00"
            SimpleEntityModel(
                id=f"{unique}-At00",
                type="AtZeroSeconds",
                time=now.replace(second=0, microsecond=0),  # str(...) endswith(":00")
                location="POINT(7 7)",
            ),
        ]

        accessor.put(rows)

    # ---------------------------------------------
    # 1. Non-Match should raise immediatly
    # ---------------------------------------------
    def test_incorrect_fields_raise_errors(self, accessor):
        # SimpleEntityModel has "type", but NOT "nonsense"
        with pytest.raises(ValidationError) as exc:
            SimpleEntityFilter(nonsense_contains="foo")

        # Should not silently treat nonsense_contains as LIKE
        # Pydantic complains that the field doesn't exist
        msg = str(exc.value)
        assert "extra" in msg.lower() or "extra inputs" in msg.lower()
        assert "nonsense_contains" in msg

    # ---------------------------------------------
    # 2. LIKE transformation correctness
    # ---------------------------------------------
    def test_contains_suffix_generates_like_param(self, accessor):
        f = SimpleEntityFilter(type_contains="bike")

        results = accessor.get(SimpleEntityModel, f, limit=5)

        assert isinstance(results, list)
        assert len(results)<=1
        for entity in results:
            assert isinstance(entity, SimpleEntityModel)
            assert "bike" in entity.type.lower()

    # ---------------------------------------------
    # 4. Minimal projection: id + type only (at model level)
    # ---------------------------------------------
    def test_minimal_projection_id_and_type_only(self, accessor):
        f = SimpleEntityFilter(
            id="123",
            minimal=True,
            type_included=True,
        )

        results = accessor.get(SimpleEntityModel, f, limit=5)
        assert isinstance(results, list)

        for entity in results:
            assert isinstance(entity, SimpleEntityModel)

            # We expect id and type to be populated
            assert entity.id is not None
            assert entity.type is not None

            # And other fields should not be populated when we say "minimal"
            # (tweak these expectations if your hydration behaves differently)
            assert getattr(entity, "time", None) is None
            assert getattr(entity, "location", None) is None


    # ---------------------------------------------
    # 6. Prefix & suffix operators work and affect `type`
    # ---------------------------------------------
    def test_prefix_and_suffix(self, accessor):
        pf = SimpleEntityFilter(type_prefix="ab")
        sf = SimpleEntityFilter(type_suffix="zz")

        prefix_results = accessor.get(SimpleEntityModel, pf, limit=5)
        suffix_results = accessor.get(SimpleEntityModel, sf, limit=5)

        assert isinstance(prefix_results, list)
        assert isinstance(suffix_results, list)

        for entity in prefix_results:
            assert isinstance(entity, SimpleEntityModel)
            assert entity.type.startswith("ab")

        for entity in suffix_results:
            assert isinstance(entity, SimpleEntityModel)
            assert entity.type.endswith("zz")

    # ---------------------------------------------
    # 8. When minimal=True and id_include=True,
    #    only id should be populated (others unset)
    # ---------------------------------------------
    def test_minimal_only_id_included(self, accessor):
        f = SimpleEntityFilter(
            minimal=True,
            id_included=True, 
        )



        results = accessor.get(SimpleEntityModel, f, limit=5)
        assert isinstance(results, list)


        for entity in results:
            assert isinstance(entity, SimpleEntityModel)

            # Only id should be populated
            assert entity.id is not None

            # Everything else should look "not selected"
            assert getattr(entity, "type", None) is None
            assert getattr(entity, "time", None) is None
            assert getattr(entity, "location", None) is None

    # ---------------------------------------------
    # 9. When minimal=True and no fields referenced,
    #    it should still return raise an exception
    # ---------------------------------------------
    def test_minimal_empty_fallback(self, accessor):
        # minimal=True with no <field>_included=True is invalid
        with pytest.raises(ValueError):
            SimpleEntityFilter(minimal=True)

    def test_valid_suffix_for_short_field(self, accessor):
        # i_suffix is a legal filter (auto-generated)

        f = SimpleEntityModel.Filter(i_suffix="z")

        results = accessor.get(SimpleEntityModel, f, limit=2)

        assert isinstance(results, list)
        for entity in results:
            assert isinstance(entity, SimpleEntityModel)
            assert entity.i.endswith("z")


    def test_valid_suffix_for_compound_field(self, accessor):
        # time_type_prefix is legal
        f = SimpleEntityModel.Filter(time_type_prefix="abc")

        results = accessor.get(SimpleEntityModel, f, limit=2)

        assert isinstance(results, list)
        for entity in results:
            assert isinstance(entity, SimpleEntityModel)
            assert entity.time_type.startswith("abc")


    import pytest
    from pydantic import ValidationError

    def test_suffix_collision_prevented_for_time_substring(self):
        # "time_typ" is a substring of "time_type" but NOT a real field
        with pytest.raises(ValidationError) as exc:
            SimpleEntityModel.Filter(time_typ_suffix="zzz")

        msg = str(exc.value).lower()
        assert "extra inputs" in msg
        assert "time_typ_suffix" in msg

    def test_suffix_collision_prevented_for_i_substring(self):
        # "ix" looks like "i" plus one letter, but is NOT a real field
        with pytest.raises(ValidationError) as exc:
            SimpleEntityModel.Filter(ix_contains="foo")

        msg = str(exc.value).lower()
        assert "extra inputs" in msg
        assert "ix_contains" in msg

    def test_accessor_rejects_unknown_fields_even_if_pydantic_is_bypassed(self,accessor):
        # Construct an illegal filter instance without Pydantic validation
        class FilterIgnoreExtra(SimpleEntityModel.Filter):
            model_config = ConfigDict(extra="ignore")

        f = FilterIgnoreExtra.model_construct(
            **{
                "time_typ_suffix": "zzz"   # NOT a real field
            }
        )

        with pytest.raises(ValueError) as exc:
            accessor.get(SimpleEntityModel, f)

        msg = str(exc.value)
        assert "Unknown filter fields" in msg
        assert "time_typ" in msg
