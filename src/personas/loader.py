"""Load persona YAML files into typed `PersonaProfile` models.

Personas carry the urgency keyword definitions that drive deterministic
classification; a malformed file must fail loudly, not classify silently.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.models.persona_models import PersonaProfile

PERSONAS_DIR = Path(__file__).resolve().parent


class PersonaLoadError(ValueError):
    """Raised when persona YAML files are missing, malformed, or collide."""


def load_personas(directory: Path | None = None) -> dict[str, PersonaProfile]:
    """Return personas keyed by profile_id from `*.yaml` files in the directory."""
    personas_dir = directory or PERSONAS_DIR
    paths = sorted(personas_dir.glob("*.yaml"))
    if not paths:
        msg = f"no persona YAML files found in {personas_dir}"
        raise PersonaLoadError(msg)
    personas: dict[str, PersonaProfile] = {}
    for path in paths:
        persona = _load_persona_file(path)
        if persona.profile_id in personas:
            msg = f"duplicate profile_id '{persona.profile_id}' in {path.name}"
            raise PersonaLoadError(msg)
        personas[persona.profile_id] = persona
    return personas


def _load_persona_file(path: Path) -> PersonaProfile:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path.name} must contain a YAML mapping"
        raise PersonaLoadError(msg)
    try:
        return PersonaProfile.model_validate(payload)
    except ValidationError as exc:
        msg = f"{path.name} is not a valid persona: {exc}"
        raise PersonaLoadError(msg) from exc
