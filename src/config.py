import json
import os
import sys
from pathlib import Path

CONFIG_FILE_NAME = "skyrim_coop_config.json"

DEFAULT_CONFIG = {
    "game_path": "",
    "nexus_api_key": "8D2tCOWStyJ0D3GtWlr3cx/VWPtYzX6vz4IhprBbLbDkcRaA4b3L--OFhvg5WzCbhO9tsc--4dcpXLz3EqlKAv3kHDw05Q==",
    "github_repo": "SkyrimTogether/SkyrimTogetherReborn",
    "bundle_url": "",
    "installed_version": "",
    "server_port": 10578,
    "last_ip": "127.0.0.1",
    "theme": "dark",
}

def get_app_dir() -> Path:
    """Returns the base directory of the running script or exe."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILE_NAME

def load_config() -> dict:
    config_path = get_config_path()
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception:
            pass
    return config

def save_config(config: dict) -> None:
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")
