import json

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


def _param(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recent_nodes(detail, limit: int = 20) -> list[str]:
    nodes = getattr(detail, "nodes", None) or []
    names: list[str] = []
    for n in nodes[-limit:]:
        name = getattr(n, "name", None)
        if name:
            names.append(str(name))
    return names


@AgentServer.custom_action("打印失败节点")
class PrintFailureNode(CustomAction):
    """失败收工时打印当前节点，并尽量带上最近走过的节点链，方便对照日志。"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = _param(argv.custom_action_param)
        reason = str(param.get("reason", "") or "").strip()
        node = argv.node_name or "?"
        entry = getattr(argv.task_detail, "entry", None) or "?"
        recent = _recent_nodes(argv.task_detail, int(param.get("limit", 20) or 20))
        # 也试一下 tasker 侧最新节点，防止 task_detail.nodes 为空
        latest = None
        try:
            latest = context.tasker.get_latest_node(entry)
        except Exception:
            latest = None
        latest_name = getattr(latest, "name", None) if latest is not None else None

        print("=" * 60, flush=True)
        print(f"[失败节点] node={node}", flush=True)
        if reason:
            print(f"[失败节点] reason={reason}", flush=True)
        print(f"[失败节点] entry={entry}", flush=True)
        if latest_name:
            print(f"[失败节点] latest={latest_name}", flush=True)
        if recent:
            print("[失败节点] recent=" + " -> ".join(recent), flush=True)
        else:
            print("[失败节点] recent=(空)", flush=True)
        print("=" * 60, flush=True)
        # soft/continue=true：只打日志仍走 next（如炼药无对话收工续一条龙）
        # 默认 False：当前节点记失败，任务以 Failed 收工；勿再接 OCR 哨兵以免 error handling loop
        soft = bool(param.get("soft") or param.get("continue"))
        return soft
