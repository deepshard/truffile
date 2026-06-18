from __future__ import annotations

from dataclasses import dataclass
from typing import Any


HIGH_RISK_DOMAINS = {
    "alarm_control_panel",
    "cover",
    "lock",
}
HIGH_RISK_WORDS = {
    "alarm",
    "arm",
    "disarm",
    "door",
    "garage",
    "gate",
    "lock",
    "script",
    "security",
    "unlock",
}
BROAD_TARGET_WORDS = {
    "all",
    "any",
    "every",
    "everything",
    "everywhere",
    "home",
    "house",
    "whole",
}
SAFE_CONTROL_DOMAINS = {
    "button",
    "fan",
    "input_boolean",
    "light",
    "media_player",
    "scene",
    "switch",
}


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    message: str
    requires_confirmation: bool = False


def _text(*parts: Any) -> str:
    return " ".join(str(part).lower() for part in parts if part is not None)


def _has_any(value: str, words: set[str]) -> bool:
    return any(word in value for word in words)


def _confirmed(confirm: bool, confirmation_text: str) -> bool:
    return confirm and confirmation_text.strip().lower() in {"confirm", "confirmed", "yes"}


def check_turn_on_off(
    *,
    action: str,
    name: str | None = None,
    area: str | None = None,
    domain: str | None = None,
    confirm: bool = False,
    confirmation_text: str = "",
) -> SafetyDecision:
    target = _text(name, area, domain)
    domain_value = (domain or "").strip().lower()
    high_risk = domain_value in HIGH_RISK_DOMAINS or _has_any(target, HIGH_RISK_WORDS)

    if high_risk:
        if not _confirmed(confirm, confirmation_text):
            return SafetyDecision(
                allowed=False,
                message=(
                    "This looks safety-sensitive. Ask the user to perform or explicitly confirm this action in "
                    "Home Assistant before changing locks, covers, garage doors, gates, alarms, or security devices."
                ),
                requires_confirmation=True,
            )
        if any(word in target for word in {"unlock", "disarm", "garage", "gate"}):
            return SafetyDecision(
                allowed=False,
                message="Unlocking, opening garage/gate covers, or disarming alarms is blocked by this app.",
                requires_confirmation=True,
            )

    if high_risk and _has_any(target, BROAD_TARGET_WORDS):
        return SafetyDecision(
            allowed=False,
            message="Broad safety-sensitive actions such as all locks, all covers, or the whole security system are blocked.",
            requires_confirmation=True,
        )

    if domain_value == "scene" and not _confirmed(confirm, confirmation_text):
        return SafetyDecision(
            allowed=False,
            message="Scenes can trigger many devices. Ask the user for explicit confirmation before running a scene.",
            requires_confirmation=True,
        )

    if action == "turn_on" and domain_value == "script":
        return SafetyDecision(
            allowed=False,
            message="Scripts are blocked because they can perform broad or safety-sensitive actions.",
            requires_confirmation=True,
        )

    return SafetyDecision(allowed=True, message="Allowed.")


def check_cover_position(
    *,
    name: str,
    position: int,
    confirm: bool = False,
    confirmation_text: str = "",
) -> SafetyDecision:
    if position < 0 or position > 100:
        return SafetyDecision(False, "Cover position must be between 0 and 100.")

    target = _text(name)
    if _has_any(target, {"garage", "gate", "door"}):
        return SafetyDecision(
            False,
            "Changing garage, gate, or door covers is blocked by this app.",
            requires_confirmation=True,
        )

    if not _confirmed(confirm, confirmation_text):
        return SafetyDecision(
            False,
            "Changing a cover can move physical equipment. Ask the user for explicit confirmation first.",
            requires_confirmation=True,
        )

    return SafetyDecision(True, "Allowed.")


def check_climate_temperature(temperature: float) -> SafetyDecision:
    if temperature > 45:
        if 50 <= temperature <= 85:
            return SafetyDecision(True, "Allowed.")
        return SafetyDecision(False, "Fahrenheit setpoints must be between 50 and 85.")

    if 10 <= temperature <= 30:
        return SafetyDecision(True, "Allowed.")
    return SafetyDecision(False, "Celsius setpoints must be between 10 and 30.")
