"""Memos 适配器（第三方插件）：HTTP 调用与分页在 `memos_impl.py`（随插件分发）。

插件只允许 import 标准库、宿主已装的依赖和 `yhub.plugin_api`，所以这份实现不能指望宿主提供
（它原先住在宿主的 `yhub/cli/memos.py`，宿主已不再分发）。
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta

import requests
from fastapi import Query
from pydantic import BaseModel

from yhub.plugin_api import ToolError, translator

# 插件目录不在 sys.path 上（宿主按文件路径加载 plugin.py）
_HERE = str(pathlib.Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from memos_impl import (  # noqa: E402  (after the sys.path bootstrap)
    CONFIG_ENV_PATH,
    INSTANCE_KEY,
    TOKEN_KEY,
    _fetch_all_memos,
    _normalize_content_line,
    _parse_memo_datetime,
    _read_env_file,
    _write_env_file,
    _get_credentials,
    load_config,
    cmd_auth,
    cmd_new,
    cmd_list as cmd_list_memos,
)

# 人话全部走插件自己的 locales/（宿主在加载时注册成 `plugins.memos.*`）
t = translator("memos")


def is_configured() -> bool:
    instance, token, _ = _get_credentials()
    return bool(instance and token)


def config_summary() -> dict:
    instance, token, path = _get_credentials()
    return {
        "configured": bool(instance and token),
        "instance": instance,
        "config_path": str(path),
        "token_set": bool(token),
    }


def save_auth(instance: str, token: str) -> dict:
    instance = (instance or "").strip().rstrip("/")
    token = (token or "").strip()
    if not instance or not token:
        raise ToolError(t("err.need_both"))
    if not instance.startswith(("http://", "https://")):
        raise ToolError(t("err.need_scheme"))

    env = _read_env_file(CONFIG_ENV_PATH)
    env[INSTANCE_KEY] = instance
    env[TOKEN_KEY] = token
    _write_env_file(CONFIG_ENV_PATH, env)
    return {"configured": True, "instance": instance, "config_path": str(CONFIG_ENV_PATH)}


def _target_date(day: str):
    today = datetime.now().date()
    if day == "today":
        return today
    if day == "yesterday":
        return today - timedelta(days=1)
    if day == "all":
        return None
    try:
        return datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(t("err.bad_day", day=day), hint=t("err.hint.day"))


def list_memos(day: str = "today", limit: int = 100) -> dict:
    if not is_configured():
        raise ToolError(t("err.not_configured"), hint=t("err.hint.configure"))

    try:
        config = load_config()
    except RuntimeError as exc:
        raise ToolError(str(exc))

    target = _target_date(day)
    memos, error = _fetch_all_memos(config)
    if error is not None:
        raise ToolError(error, hint=t("err.hint.check_instance"))

    items = []
    for memo in memos:
        created = _parse_memo_datetime(str(memo.get("createTime", "")))
        if created is None:
            continue
        if target is not None and created.date() != target:
            continue
        items.append(
            {
                "id": memo.get("name") or memo.get("id") or "",
                "time": created.strftime("%Y-%m-%d %H:%M:%S"),
                "content": str(memo.get("content", "")),
                "preview": _normalize_content_line(str(memo.get("content", ""))),
                "visibility": memo.get("visibility", ""),
                "tags": memo.get("tags") or [],
            }
        )

    items.sort(key=lambda x: x["time"], reverse=True)
    return {
        "day": day,
        "count": len(items),
        "total_fetched": len(memos),
        "items": items[:limit],
    }


def create_memo(content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise ToolError(t("err.empty_content"))

    if not is_configured():
        raise ToolError(t("err.not_configured"), hint=t("err.hint.configure"))

    try:
        config = load_config()
    except RuntimeError as exc:
        raise ToolError(str(exc))

    url = f"{config.instance}/api/memos"
    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
    }
    payload = {"content": content, "visibility": "PRIVATE"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        raise ToolError(t("err.request_failed", reason=exc))

    if resp.status_code >= 400:
        raise ToolError(
            t("err.create_failed", status=resp.status_code),
            hint=resp.text[:200] if resp.text else t("err.hint.network_or_token"),
        )

    try:
        data = resp.json()
    except ValueError:
        data = {}
    return {
        "id": data.get("name") or data.get("id") or "",
        "content": content,
        "time": data.get("createTime", ""),
    }


def _memos_config_get() -> dict:
    return {"ok": True, "config": config_summary()}


def _memos_config_save(payload) -> dict:
    return {"ok": True, "config": save_auth(payload.instance, payload.token)}


def _memos_list(day: str = "today", limit: int = 100) -> dict:
    return {"ok": True, **list_memos(day=day, limit=limit)}


def _memos_create(payload) -> dict:
    return {"ok": True, "memo": create_memo(payload.content)}


# ---- CLI 面 -----------------------------------------------------------------


def _cli_auth() -> int:
    return cmd_auth()


def _cli_new(content: list[str]) -> int:
    text = " ".join(content).strip()
    if not text:
        print("Memo content must not be empty.")
        return 1
    return cmd_new(text)


def _cli_list(day: str, json_out: bool = False):
    if json_out:
        return {"ok": True, **list_memos(day=day, limit=100)}
    return cmd_list_memos(day)


TOOL_META = {
    "ready": lambda: is_configured(),
    "status": lambda: config_summary()["instance"] or t("status.unconfigured"),
}
