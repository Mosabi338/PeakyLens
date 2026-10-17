"""Loads and saves settings (config.json) and API keys (.env).

Where do the files live?
- Running from source (python main.py): in the project folder.
- Packaged with PyInstaller: in %APPDATA%\\PeakyLens, because the folder that
  holds a packaged .exe is often read-only or temporary.
"""
import copy
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

APP_NAME = "PeakyLens"

# Every setting has a default, so the app still works if config.json is missing
# or was edited by hand and some keys were deleted.
DEFAULT_CONFIG = {
    "provider": "groq",
    "providers": {
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-20b",
            "api_key_env": "GROQ_API_KEY",
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-oss-20b",
            "api_key_env": "OPENROUTER_API_KEY",
        },
    },
    "hotkeys": {"explain": "Ctrl+Alt+E", "ask": "Ctrl+Alt+A"},
    "theme": "dark",
    "level": "intermediate",
    "timeout_seconds": 60,
}


def base_dir() -> Path:
    """Folder where config.json, .env, history.db and the log file live."""
    if getattr(sys, "frozen", False):  # True only inside a PyInstaller build
        folder = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        # This file is in backend/, so go up two levels to the project root.
        folder = Path(__file__).resolve().parent.parent
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def config_path() -> Path:
    return base_dir() / "config.json"


def env_path() -> Path:
    return base_dir() / ".env"


def _merge(defaults: dict, loaded: dict) -> dict:
    """Copy `defaults`, then overwrite with anything found in `loaded`.

    Nested dictionaries are merged key by key, so a config.json that only
    contains {"theme": "light"} still gets every other default.
    """
    result = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """Read config.json (or fall back to defaults) and load the .env keys."""
    load_dotenv(env_path(), override=True)

    loaded = {}
    path = config_path()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A broken file should never stop the app from starting.
            loaded = {}
    return _merge(DEFAULT_CONFIG, loaded)


def save_config(config: dict) -> None:
    config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")


def active_provider(config: dict) -> dict:
    """Return the settings of the provider currently selected (groq/openrouter)."""
    name = config["provider"]
    provider = dict(config["providers"][name])
    provider["name"] = name
    return provider


def get_api_key(config: dict) -> str:
    """Read the key from the environment variable named in the provider settings."""
    env_name = active_provider(config)["api_key_env"]
    return os.environ.get(env_name, "").strip()


def has_api_key(env_name: str) -> bool:
    """True if a non-empty key is currently loaded for this environment variable."""
    return bool(os.environ.get(env_name, "").strip())


def save_api_key(env_name: str, key: str) -> None:
    """Store the key in the .env file AND in the running process.

    - Writing to .env makes it survive restarts (the key is never hardcoded).
    - Setting os.environ makes it work immediately, with no restart needed.
    """
    key = key.strip()
    env_path().touch(exist_ok=True)  # make sure the file exists
    set_key(str(env_path()), env_name, key)
    os.environ[env_name] = key


if __name__ == "__main__":
    # Quick self-test:  python -m backend.config
    cfg = load_config()
    print("Folder:", base_dir())
    print("Provider:", active_provider(cfg))
    print("API key found:", bool(get_api_key(cfg)))