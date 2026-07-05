from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.email_models import UrgencyBand
from src.models.persona_models import PersonaProfile
from src.personas.loader import PersonaLoadError, load_personas


def test_loads_all_repo_personas() -> None:
    personas = load_personas()

    assert set(personas) == {"city_council", "consulting", "habitat", "prime_boilers"}
    consulting = personas["consulting"]
    assert consulting.display_name == "Consulting"
    assert "contract deadline" in consulting.urgency_definitions[UrgencyBand.CRITICAL]
    assert consulting.response_constraints


def test_urgency_keys_coerce_to_bands_and_keywords_lowercase() -> None:
    persona = PersonaProfile.model_validate(
        {
            "profile_id": "synthetic",
            "display_name": "Synthetic",
            "tone": "neutral",
            "urgency_definitions": {"critical": ["Blocker Word"]},
            "filing_taxonomy": "general.yaml",
        }
    )

    assert persona.urgency_definitions[UrgencyBand.CRITICAL] == ["blocker word"]


def test_unknown_urgency_band_key_rejected() -> None:
    with pytest.raises(ValidationError):
        PersonaProfile.model_validate(
            {
                "profile_id": "synthetic",
                "display_name": "Synthetic",
                "tone": "neutral",
                "urgency_definitions": {"panic": ["nope"]},
                "filing_taxonomy": "general.yaml",
            }
        )


def test_duplicate_profile_id_rejected(tmp_path: Path) -> None:
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(
            "profile_id: twin\ndisplay_name: Twin\ntone: neutral\nfiling_taxonomy: general.yaml\n",
            encoding="utf-8",
        )

    with pytest.raises(PersonaLoadError, match="duplicate profile_id 'twin'"):
        load_personas(tmp_path)


def test_directory_without_yaml_rejected(tmp_path: Path) -> None:
    with pytest.raises(PersonaLoadError, match="no persona YAML files"):
        load_personas(tmp_path)


def test_invalid_persona_error_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("profile_id: broken\n", encoding="utf-8")

    with pytest.raises(PersonaLoadError, match="broken.yaml"):
        load_personas(tmp_path)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    (tmp_path / "list.yaml").write_text("- just\n- a list\n", encoding="utf-8")

    with pytest.raises(PersonaLoadError, match="YAML mapping"):
        load_personas(tmp_path)
