import json
import platformdirs
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class StoredDevice:
    name: str
    token: str


@dataclass
class StoredObsidianBridge:
    vault_path: str
    token: str
    advertise_host: str
    port: int = 27125
    bind_host: str = "0.0.0.0"


@dataclass
class StoredState:
    devices: list[StoredDevice] = field(default_factory=list)
    last_used_device: str | None = None
    client_user_id: str | None = None
    obsidian_bridge: StoredObsidianBridge | None = None
    hidden_convo_threads: dict[str, list[int]] = field(default_factory=dict)


def get_storage_dir() -> Path:
    dir_path = Path(platformdirs.user_data_dir("truffile"))
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


class StorageService:
    def __init__(self):
        self.storage_dir = get_storage_dir()
        self.state_file = self.storage_dir / "state.json"
        self.state = self._load_state()

    def _load_state(self) -> StoredState:
        if not self.state_file.exists():
            self._unknown_state = {}
            return StoredState()
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            known_keys = {
                "devices",
                "last_used_device",
                "client_user_id",
                "obsidian_bridge",
                "hidden_convo_threads",
            }
            self._unknown_state = {
                key: value for key, value in data.items() if key not in known_keys
            }
            devices = [StoredDevice(**d) for d in data.get("devices", [])]
            bridge_data = data.get("obsidian_bridge")
            obsidian_bridge = None
            if isinstance(bridge_data, dict):
                try:
                    obsidian_bridge = StoredObsidianBridge(**bridge_data)
                except TypeError:
                    obsidian_bridge = None
            return StoredState(
                devices=devices,
                last_used_device=data.get("last_used_device"),
                client_user_id=data.get("client_user_id"),
                obsidian_bridge=obsidian_bridge,
                hidden_convo_threads=self._parse_hidden_convo_threads(
                    data.get("hidden_convo_threads", {})
                ),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            self._unknown_state = {}
            return StoredState()

    @staticmethod
    def _parse_hidden_convo_threads(value) -> dict[str, list[int]]:
        if not isinstance(value, dict):
            return {}
        parsed: dict[str, list[int]] = {}
        for key, thread_ids in value.items():
            if not isinstance(key, str) or not isinstance(thread_ids, list):
                continue
            safe_ids: list[int] = []
            for thread_id in thread_ids:
                try:
                    normalized = int(thread_id)
                except (TypeError, ValueError):
                    continue
                if normalized not in (0, -1) and normalized not in safe_ids:
                    safe_ids.append(normalized)
            parsed[key] = sorted(safe_ids)
        return parsed

    def save(self) -> None:
        state_dict = dict(getattr(self, "_unknown_state", {}))
        state_dict.update({
            "devices": [{"name": d.name, "token": d.token} for d in self.state.devices],
            "last_used_device": self.state.last_used_device,
            "client_user_id": self.state.client_user_id,
            "obsidian_bridge": (
                {
                    "vault_path": self.state.obsidian_bridge.vault_path,
                    "token": self.state.obsidian_bridge.token,
                    "advertise_host": self.state.obsidian_bridge.advertise_host,
                    "port": self.state.obsidian_bridge.port,
                    "bind_host": self.state.obsidian_bridge.bind_host,
                }
                if self.state.obsidian_bridge is not None
                else None
            ),
            "hidden_convo_threads": self.state.hidden_convo_threads,
        })
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state_dict, f, indent=4)

    def get_token(self, device_name: str) -> str | None:
        for device in self.state.devices:
            if device.name == device_name:
                return device.token
        return None

    def has_token(self, device_name: str) -> bool:
        token = self.get_token(device_name)
        return token is not None and len(token) > 0

    def set_token(self, device_name: str, token: str) -> None:
        for device in self.state.devices:
            if device.name == device_name:
                device.token = token
                self.save()
                return
        self.state.devices.append(StoredDevice(name=device_name, token=token))
        self.save()

    def set_last_used(self, device_name: str) -> None:
        self.state.last_used_device = device_name
        self.save()

    def remove_device(self, device_name: str) -> bool:
        for i, device in enumerate(self.state.devices):
            if device.name == device_name:
                self.state.devices.pop(i)
                if self.state.last_used_device == device_name:
                    self.state.last_used_device = None
                self.save()
                return True
        return False

    def clear_all(self) -> None:
        self.state = StoredState()
        self.save()

    def list_devices(self) -> list[str]:
        return [d.name for d in self.state.devices]

    def get_obsidian_bridge(self) -> StoredObsidianBridge | None:
        return self.state.obsidian_bridge

    def set_obsidian_bridge(self, bridge: StoredObsidianBridge) -> None:
        self.state.obsidian_bridge = bridge
        self.save()

    def clear_obsidian_bridge(self) -> None:
        self.state.obsidian_bridge = None
        self.save()

    @staticmethod
    def _convo_hide_key(device_name: str, user_id: str) -> str:
        device = device_name.strip()
        user = user_id.strip()
        if not device or not user:
            raise ValueError("device name and authenticated user id are required")
        return f"{device}::{user}"

    def hidden_convo_thread_ids(self, device_name: str, user_id: str) -> set[int]:
        key = self._convo_hide_key(device_name, user_id)
        return {int(value) for value in self.state.hidden_convo_threads.get(key, [])}

    def hide_convo_thread(self, device_name: str, user_id: str, thread_id: int) -> None:
        normalized = int(thread_id)
        if normalized in (0, -1):
            raise ValueError("Main and system threads cannot be hidden")
        key = self._convo_hide_key(device_name, user_id)
        hidden = self.hidden_convo_thread_ids(device_name, user_id)
        hidden.add(normalized)
        self.state.hidden_convo_threads[key] = sorted(hidden)
        self.save()

    def restore_convo_thread(self, device_name: str, user_id: str, thread_id: int) -> None:
        normalized = int(thread_id)
        key = self._convo_hide_key(device_name, user_id)
        hidden = self.hidden_convo_thread_ids(device_name, user_id)
        hidden.discard(normalized)
        if hidden:
            self.state.hidden_convo_threads[key] = sorted(hidden)
        else:
            self.state.hidden_convo_threads.pop(key, None)
        self.save()

    def app_id_for_device(self, name: str) -> str | None:
        """Return the in-container APP_ID for `name`, else None.

        Set by `truffile.cli.in_container` injection at startup. On a normal
        LAN dev machine `_in_container_info` is never set and this always
        returns None — TruffleClient receives `app_id=None` and behaves
        identically to today.
        """
        info = getattr(self, "_in_container_info", None)
        if info is None:
            return None
        if getattr(info, "device_name", None) != name:
            return None
        return getattr(info, "app_id", None) or None
