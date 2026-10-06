import json
import re

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


_SLASH = re.compile(r"(\d+)\s*[/／]\s*(\d+)")


def _ocr_text(reco) -> str:
    if reco is None or not getattr(reco, "hit", False):
        return ""
    best = getattr(reco, "best_result", None)
    if best is None:
        return ""
    return str(getattr(best, "text", "") or "")


def _parse_slash(text: str):
    m = _SLASH.search(text.replace(",", "").replace("，", "").replace(" ", ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_param(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(loaded, str):
        try:
            loaded = json.loads(loaded)
        except json.JSONDecodeError:
            return {}
    return loaded if isinstance(loaded, dict) else {}


@AgentServer.custom_action("钱袋_判定是否买金丝")
class MoneybagMaybeBuyGoldSilk(CustomAction):
    """进商店后读顶栏体力；>=min 买金丝钱袋，否则跳过直去赛季追赶买通宝。"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = _parse_param(argv.custom_action_param)
        min_stamina = int(param.get("min_stamina", 200))
        img = context.tasker.controller.post_screencap().wait().get()
        text = _ocr_text(context.run_recognition("钱袋_读体力", img))
        pair = _parse_slash(text)
        print(f"[钱袋_判定是否买金丝] raw={text!r} parsed={pair} min={min_stamina}")
        if pair is None:
            # 读不到体力：不盲买金丝，只买通宝
            context.override_next(argv.node_name, ["钱袋_滑侧栏找赛季"])
            return True
        total, _ = pair
        if total >= min_stamina:
            context.override_next(argv.node_name, ["钱袋_选金丝钱袋"])
        else:
            context.override_next(argv.node_name, ["钱袋_滑侧栏找赛季"])
        return True
