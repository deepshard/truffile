from __future__ import annotations

import unittest
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(REPO_ROOT))

from config import DEFAULT_MCP_PATH, HomeAssistantConfig, normalize_base_url, normalize_mcp_path
from safety import check_climate_temperature, check_cover_position, check_turn_on_off


class TestHomeAssistantConfig(unittest.TestCase):
    def test_normalizes_base_url_and_mcp_path(self) -> None:
        config = HomeAssistantConfig(
            base_url=normalize_base_url(" https://ha.example.test:8123/ "),
            token="token",
            mcp_path=normalize_mcp_path("api/mcp"),
        )

        self.assertEqual(config.base_url, "https://ha.example.test:8123")
        self.assertEqual(config.mcp_path, DEFAULT_MCP_PATH)
        self.assertEqual(config.mcp_url, "https://ha.example.test:8123/api/mcp")

    def test_rejects_invalid_base_url(self) -> None:
        with self.assertRaises(ValueError):
            normalize_base_url("homeassistant.local:8123")


class TestHomeAssistantSafety(unittest.TestCase):
    def test_blocks_unconfirmed_lock_action(self) -> None:
        decision = check_turn_on_off(action="turn_on", name="front door lock", domain="lock")

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)

    def test_blocks_unlock_even_with_confirmation(self) -> None:
        decision = check_turn_on_off(
            action="turn_on",
            name="unlock front door",
            domain="lock",
            confirm=True,
            confirmation_text="confirm",
        )

        self.assertFalse(decision.allowed)

    def test_blocks_garage_cover_position(self) -> None:
        decision = check_cover_position(
            name="garage door",
            position=50,
            confirm=True,
            confirmation_text="confirm",
        )

        self.assertFalse(decision.allowed)

    def test_allows_confirmed_non_garage_cover(self) -> None:
        decision = check_cover_position(
            name="living room blinds",
            position=30,
            confirm=True,
            confirmation_text="confirm",
        )

        self.assertTrue(decision.allowed)

    def test_blocks_extreme_climate_setpoints(self) -> None:
        self.assertFalse(check_climate_temperature(90).allowed)
        self.assertFalse(check_climate_temperature(5).allowed)

    def test_allows_safe_light_action(self) -> None:
        decision = check_turn_on_off(action="turn_on", name="kitchen lights", domain="light")

        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
