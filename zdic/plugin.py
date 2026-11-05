"""汉典插件：三面共用一份声明（契约见 api-contract.md）。

  HTTP  GET /api/zdic   —— params 由宿主的 params.py 装配进端点签名
  MCP   zdic_lookup     —— 同一份 params 生成签名
  CLI   yhub zdic       —— faces.cli 生成 argparse（--json 与 HTTP 同一份 body）

抓取与解析在 `zdic_impl.py`：插件只允许 import 标准库、宿主已装的依赖和 `yhub.plugin_api`，
所以那份实现不能指望宿主提供（它原先住在宿主的 `yhub/cli/zdic.py`，宿主已不再分发）。
"""

from __future__ import annotations

import json
import pathlib
import sys

from yhub.plugin_api import ToolError, translator

# 插件目录不在 sys.path 上（宿主按文件路径加载 plugin.py），把自己的目录临时加进去，
# 模块名带插件前缀，避免与其它插件撞名。
_HERE = str(pathlib.Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import zdic_impl as _impl  # noqa: E402  (after the sys.path bootstrap)
from zdic_impl import ZdicError, lookup  # noqa: E402

# 人话全部走插件自己的 locales/（宿主在加载时注册成 `plugins.zdic.*`）
t = translator("zdic")


def _lookup(word: str, traditional: bool = False) -> dict:
    try:
        return lookup(word, traditional=traditional)
    except ZdicError as exc:
        raise ToolError(str(exc), hint=t("err.hint.network")) from exc


def _ready() -> bool:
    return True


def _zdic_route(q: str, traditional: bool = False) -> dict:
    # 形参的类型/描述由声明装配（apply_route_params），这里只留胶水语义：
    # 把 wire 名 q 翻译成实现里的 word。
    return {"ok": True, "result": _lookup(q, traditional=traditional)}


def _cli(words, traditional: bool, links: bool, json_out: bool) -> int:
    """``yhub zdic``：人话照旧；``--json`` 出与 GET /api/zdic 同一份 body
    （单字 = {"ok": true, "result": {...}}；多字 result 为数组——HTTP 面只收单字）。"""
    resolved = list(words) or _impl.stdin_words()
    if not resolved:
        # 与老行为一致：一个词都没有 → 打用法、退出码 2
        print("usage: yhub zdic [words ...]")
        return 2
    results, code = _impl.collect(resolved, traditional=traditional, links=links)
    if json_out:
        payload = results[0] if len(results) == 1 else results
        print(json.dumps({"ok": True, "result": payload}, ensure_ascii=False, indent=2))
        return code
    print("\n".join(_impl.render(r) for r in results))
    return code


# --------------------------------------------------------------------------- 三面入口
#
# plugin.json 的 faces 按这些名字引用 handler；视图函数只有一份，
# HTTP / MCP / CLI 三面共用（--json 与对应接口是同一份 body）。

zdic_route = _zdic_route
mcp_lookup = _lookup
cli_main = _cli


TOOL_META = {
    "ready": _ready,
    "status": lambda: "Ready",
}
