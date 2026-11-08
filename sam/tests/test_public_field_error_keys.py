"""Round 5 (task 19.1): the public 422 carries BARE field keys (steering 39)."""

from __future__ import annotations

import pytest

from sam.members.domain._membership_errors import FieldError
from sam.members.handler import public_app
from sam.members.handler._http import _field_errors_array


def _err(code: str = "errors.validation.required") -> FieldError:
    return FieldError(code=code, detail="x")


@pytest.mark.parametrize(
    ("engine_key", "bare"),
    [
        ("personal.last_name", "last_name"),
        ("personal.email", "email"),
        ("personal.birth_date", "birth_date"),
        ("membership.membership_type", "membership_type"),
        ("overlay.region", "region"),
        ("overlay.magazine_pref", "magazine_pref"),
        ("consent", "consent"),
        ("unknown.group.deep_key", "deep_key"),
    ],
)
def test_public_field_key_maps_to_bare_key(engine_key, bare):
    assert public_app._public_field_key(engine_key) == bare


def test_public_errors_array_keeps_shape_and_bare_fields():
    arr = public_app._public_field_errors_array(
        {"personal.email": _err("errors.validation.invalidFormat"), "consent": _err()}
    )
    assert [e["field"] for e in arr] == ["email", "consent"]
    assert arr[0]["code"] == "errors.validation.invalidFormat"
    assert arr[0]["detail"] == "x"


def test_public_errors_array_dedupes_collapsed_keys_first_wins():
    arr = public_app._public_field_errors_array(
        {
            "personal.region": _err("errors.validation.required"),
            "overlay.region": _err("errors.validation.invalidFormat"),
        }
    )
    assert len(arr) == 1
    assert arr[0]["field"] == "region"
    assert arr[0]["code"] == "errors.validation.required"


def test_authenticated_array_keeps_dotted_keys():
    arr = _field_errors_array({"personal.email": _err()})
    assert arr[0]["field"] == "personal.email"
