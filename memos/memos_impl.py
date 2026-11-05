"""Memos HTTP client (self-contained).

Moved out of the host (`yhub/cli/memos.py`, no longer shipped) into this plugin: a plugin may
import only the stdlib, the host's dependencies and `yhub.plugin_api`, so the client lives here.

Credentials stay in the host config root's `.env` (`YHUB_MEMOS_INSTANCE` / `YHUB_MEMOS_TOKEN`),
so the plugin follows `YHUB_SETTINGS_FILE` / `YHUB_CONFIG_DIR` like the host does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from getpass import getpass
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

def _config_dir() -> Path:
    """The host's config root: parent of `YHUB_SETTINGS_FILE` > `YHUB_CONFIG_DIR` > ~/.config/yhub."""
    explicit = os.environ.get("YHUB_SETTINGS_FILE", "").strip()
    if explicit:
        parent = Path(explicit).expanduser().parent
        if str(parent):
            return parent
    raw = os.environ.get("YHUB_CONFIG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config" / "yhub"


CONFIG_DIR = _config_dir()
CONFIG_ENV_PATH = CONFIG_DIR / ".env"
INSTANCE_KEY = "YHUB_MEMOS_INSTANCE"
TOKEN_KEY = "YHUB_MEMOS_TOKEN"


@dataclass
class MemosConfig:
    instance: str
    token: str


def _read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{key}={value}" for key, value in values.items())
    path.write_text(f"{body}\n", encoding="utf-8")


def _get_credentials() -> tuple[str, str, Path]:
    env = _read_env_file(CONFIG_ENV_PATH)
    instance = env.get(INSTANCE_KEY, "").strip().rstrip("/")
    token = env.get(TOKEN_KEY, "").strip()
    if instance and token:
        return instance, token, CONFIG_ENV_PATH
    return instance, token, CONFIG_ENV_PATH


def load_config() -> MemosConfig:
    instance, token, _ = _get_credentials()
    if not instance or not token:
        raise RuntimeError(
            "Memos auth is not configured. Run `yhub memos auth` first."
        )
    return MemosConfig(instance=instance, token=token)


def cmd_auth() -> int:
    instance = input("Memos instance URL (e.g. https://demo.usememos.com): ").strip()
    if not instance:
        print("Instance URL is required.")
        return 1

    instance = instance.rstrip("/")
    account_hint = f"{instance}/setting#my-account"
    print(f"Get your token from: {account_hint}")
    token = getpass("Memos token: ").strip()

    if not token:
        print("Token is required.")
        return 1

    env = _read_env_file(CONFIG_ENV_PATH)
    env[INSTANCE_KEY] = instance
    env[TOKEN_KEY] = token
    _write_env_file(CONFIG_ENV_PATH, env)

    print(f"Saved memos auth config to {CONFIG_ENV_PATH}")
    return 0


def cmd_new(content: str) -> int:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(str(exc))
        return 1

    url = f"{config.instance}/api/memos"
    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
    }
    payload = {"content": content}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        print(f"Failed to connect to memos API: {exc}")
        return 1

    if response.status_code >= 400:
        print("Failed to create memo.")
        print(f"Status: {response.status_code}")
        print(response.text)
        return 1

    print("Memo created successfully.")
    try:
        data = response.json()
        memo_id = data.get("name") or data.get("id")
        if memo_id is not None:
            print(f"Memo id: {memo_id}")
    except ValueError:
        pass

    return 0


def _parse_memo_datetime(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None

    # Handle RFC3339 timestamps ending with Z.
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"

    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone()
    return dt.astimezone()


def _normalize_content_line(content: str) -> str:
    return " ".join(content.replace("\n", " ").split())


def _fetch_all_memos(config: MemosConfig) -> tuple[list[dict], str | None]:
    url = f"{config.instance}/api/memos"
    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
    }

    all_memos: list[dict] = []
    page_token = ""

    while True:
        params = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20,
            )
        except requests.RequestException as exc:
            return [], f"Failed to connect to memos API: {exc}"

        if response.status_code >= 400:
            return (
                [],
                f"Failed to list memos. Status: {response.status_code}\n{response.text}",
            )

        try:
            data = response.json()
        except ValueError:
            return [], "Failed to parse memos API response as JSON."

        if isinstance(data, list):
            all_memos.extend(item for item in data if isinstance(item, dict))
            break

        if not isinstance(data, dict):
            return [], "Unexpected memos API response format."

        page_items = data.get("memos", [])
        if isinstance(page_items, list):
            all_memos.extend(item for item in page_items if isinstance(item, dict))

        next_page_token = data.get("nextPageToken") or ""
        if not next_page_token:
            break
        page_token = str(next_page_token)

    return all_memos, None


def cmd_list(day_label: str) -> int:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(str(exc))
        return 1

    all_memos, error = _fetch_all_memos(config)
    if error is not None:
        print(error)
        return 1

    today = datetime.now().date()
    if day_label == "today":
        target_date = today
    elif day_label == "yesterday":
        target_date = today - timedelta(days=1)
    else:
        print("Unsupported time option. Use: today or yesterday")
        return 1

    filtered_rows: list[tuple[datetime, str]] = []
    for memo in all_memos:
        create_time_raw = str(memo.get("createTime", ""))
        create_time = _parse_memo_datetime(create_time_raw)
        if create_time is None or create_time.date() != target_date:
            continue

        content = str(memo.get("content", ""))
        content_line = _normalize_content_line(content)
        filtered_rows.append((create_time, content_line))

    filtered_rows.sort(key=lambda item: item[0])

    for created_at, content in filtered_rows:
        time_text = created_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{time_text} {content}")

    return 0
