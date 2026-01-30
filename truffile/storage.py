import json
import platformdirs
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class StoredDevice:
    name: str
    token: str


@dataclass
class StoredState:
    devices: list[StoredDevice] = field(default_factory=list)
    last_used_device: str | None = None
    client_user_id: str | None = None


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
            return StoredState(
                devices=devices,
                last_used_device=data.get("last_used_device"),
                client_user_id=data.get("client_user_id"),
            )
        except (json.JSONDecodeError, KeyError):
            return StoredState()

    def save(self) -> None:
        state_dict = {
            "devices": [{"name": d.name, "token": d.token} for d in self.state.devices],
            "last_used_device": self.state.last_used_device,
            "client_user_id": self.state.client_user_id,
        }
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
