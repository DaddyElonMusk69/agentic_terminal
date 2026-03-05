from app.application.automation.pipeline import _resolve_template_id


def test_resonance_refresh_uses_new_resonance_template_when_unset():
    template_map = {
        "new_resonance": 101,
        "resonance_increase": 202,
    }

    resolved = _resolve_template_id("resonance_refresh", template_map)

    assert resolved == 101


def test_resonance_refresh_prefers_own_template_when_set():
    template_map = {
        "new_resonance": 101,
        "resonance_refresh": 303,
    }

    resolved = _resolve_template_id("resonance_refresh", template_map)

    assert resolved == 303


def test_resolve_template_id_returns_none_without_mapping():
    assert _resolve_template_id("resonance_refresh", None) is None
