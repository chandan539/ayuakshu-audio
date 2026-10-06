"""Voice delivery sliders and design presets."""

from fastapi.testclient import TestClient

from app.tts.delivery import delivery_settings, detect_language, style_from_prompt


def test_delivery_endpoints():
    creative = delivery_settings(0.0, 0.2)
    robust = delivery_settings(1.0, 0.9)
    assert creative["temperature"] > robust["temperature"]
    assert robust["cfg_weight"] > creative["cfg_weight"]
    assert 0.2 < delivery_settings(0.6, 0.75)["exaggeration"] < 0.8


def test_detect_language():
    assert detect_language("नमस्ते दुनिया") == "hi"
    assert detect_language("Hello there") == "en"


def test_preset_overrides_prompt_energy():
    style = style_from_prompt("quick excited host", preset_id="calm")
    assert style["stability"] >= 0.8
    assert style["name"] == "Calm narrator"


def test_design_voice_copies_reference(client: TestClient):
    from pathlib import Path

    root_voice = Path(__file__).resolve().parents[2] / "voices" / "test.wav"
    if not root_voice.is_file():
        import pytest

        pytest.skip("reference voice missing")
    created = client.post(
        "/voices",
        json={"name": "Base", "language": "hi", "source_audio": str(root_voice)},
    )
    assert created.status_code == 200, created.text
    base_id = created.json()["id"]
    designed = client.post(
        "/voices/design",
        json={
            "base_voice_id": base_id,
            "preset_id": "news",
            "prompt": "",
        },
    )
    assert designed.status_code == 200, designed.text
    body = designed.json()
    assert body["voice"]["metadata"]["designed"] is True
    assert body["delivery"]["stability"] >= 0.8
    assert Path(body["voice"]["reference_audio"]).is_file()
