from app.application.bus.outbox_service import _serialize_payload


def test_serialize_payload_replaces_non_finite_floats():
    payload = {
        "ok": 1.25,
        "pos_inf": float("inf"),
        "neg_inf": float("-inf"),
        "nan": float("nan"),
        "nested": {
            "items": [0.5, float("inf"), {"value": float("-inf")}],
        },
    }

    serialized = _serialize_payload(payload)

    assert serialized["ok"] == 1.25
    assert serialized["pos_inf"] is None
    assert serialized["neg_inf"] is None
    assert serialized["nan"] is None
    assert serialized["nested"]["items"][0] == 0.5
    assert serialized["nested"]["items"][1] is None
    assert serialized["nested"]["items"][2]["value"] is None
