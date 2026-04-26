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
class StoredAudioBridge:
    cache_path: str
    token: str
    advertise_host: str
    port: int = 27126
    bind_host: str = "0.0.0.0"


@dataclass
class StoredState:
    devices: list[StoredDevice] = field(default_factory=list)
    last_used_device: str | None = None
    client_user_id: str | None = None
    obsidian_bridge: StoredObsidianBridge | None = None
    audio_bridge: StoredAudioBridge | None = None


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
            return StoredState()
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            devices = [StoredDevice(**d) for d in data.get("devices", [])]
            bridge_data = data.get("obsidian_bridge")
            obsidian_bridge = None
            if isinstance(bridge_data, dict):
                try:
                    obsidian_bridge = StoredObsidianBridge(**bridge_data)
                except TypeError:
                    obsidian_bridge = None
            audio_bridge_data = data.get("audio_bridge")
            audio_bridge = None
            if isinstance(audio_bridge_data, dict):
                try:
                    audio_bridge = StoredAudioBridge(**audio_bridge_data)
                except TypeError:
                    audio_bridge = None
            return StoredState(
                devices=devices,
                last_used_device=data.get("last_used_device"),
                client_user_id=data.get("client_user_id"),
                obsidian_bridge=obsidian_bridge,
                audio_bridge=audio_bridge,
            )
        except (json.JSONDecodeError, KeyError):
            return StoredState()

    def save(self) -> None:
        state_dict = {
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
            "audio_bridge": (
                {
                    "cache_path": self.state.audio_bridge.cache_path,
                    "token": self.state.audio_bridge.token,
                    "advertise_host": self.state.audio_bridge.advertise_host,
                    "port": self.state.audio_bridge.port,
                    "bind_host": self.state.audio_bridge.bind_host,
                }
                if self.state.audio_bridge is not None
                else None
            ),
        }
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

    def get_audio_bridge(self) -> StoredAudioBridge | None:
        return self.state.audio_bridge

    def set_audio_bridge(self, bridge: StoredAudioBridge) -> None:
        self.state.audio_bridge = bridge
        self.save()

    def clear_audio_bridge(self) -> None:
        self.state.audio_bridge = None
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
