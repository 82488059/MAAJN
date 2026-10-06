import json
import re
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


# 1280×720；列 1024/1090/1158，行 236/308/380/452（手机式 123 上排）
_KEYPAD = {
    "1": (1024, 236),
    "2": (1090, 236),
    "3": (1158, 236),
    "4": (1024, 308),
    "5": (1090, 308),
    "6": (1158, 308),
    "7": (1024, 380),
    "8": (1090, 380),
    "9": (1158, 380),
    "0": (1090, 452),
    "bs": (1024, 452),
    "ok": (1158, 452),
}
_QTY_BOX = (1090, 505)
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


def _craftable(context: Context, cost: int):
    """返回 (可炼数量或 None 表示 OCR 失败, 说明字符串)。"""
    img = context.tasker.controller.post_screencap().wait().get()
    s_text = _ocr_text(context.run_recognition("炼药_读体力", img))
    q_text = _ocr_text(context.run_recognition("炼药_读数量", img))
    stamina = _parse_slash(s_text)
    qty_pair = _parse_slash(q_text)
    if stamina is None or qty_pair is None:
        return None, f"OCR失败 stamina={s_text!r} qty={q_text!r}"
    total, _ = stamina
    _, limit = qty_pair
    if cost <= 0 or limit <= 0:
        return 0, f"total={total} cost={cost} limit={limit}"
    return min(total // cost, limit), f"total={total} cost={cost} limit={limit}"


@AgentServer.custom_action("炼药_算量并输入")
class AlchemyCalcAndInput(CustomAction):
    """读改数量前体力与数量上限，算 min(floor(总÷需), 上限)，小键盘输入后点确认。"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = _parse_param(argv.custom_action_param)
        cost = int(param.get("cost", 15))
        if cost <= 0:
            context.override_next(argv.node_name, ["炼药_安全退出"])
            return True

        craft_qty, detail = _craftable(context, cost)
        print(f"[炼药_算量并输入] {detail} -> qty={craft_qty}")
        if craft_qty is None or craft_qty <= 0:
            context.override_next(argv.node_name, ["炼药_安全退出"])
            return True

        ctrl = context.tasker.controller
        ctrl.post_click(*_QTY_BOX).wait()
        time.sleep(0.35)

        for _ in range(3):
            ctrl.post_click(*_KEYPAD["bs"]).wait()
            time.sleep(0.12)

        for ch in str(craft_qty):
            pt = _KEYPAD.get(ch)
            if pt is None:
                context.override_next(argv.node_name, ["炼药_安全退出"])
                return True
            ctrl.post_click(*pt).wait()
            time.sleep(0.12)

        ctrl.post_click(*_KEYPAD["ok"]).wait()
        time.sleep(0.35)

        context.override_next(argv.node_name, ["炼药_点提交"])
        return True


@AgentServer.custom_action("炼药_耗尽则退出")
class AlchemyExitIfDepleted(CustomAction):
    """结算关掉后复查体力/数量上限；可炼为 0 则退出界面，否则继续算量输入（循环）。"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = _parse_param(argv.custom_action_param)
        cost = int(param.get("cost", 15))
        craft_qty, detail = _craftable(context, cost)
        print(f"[炼药_耗尽则退出] {detail} -> qty={craft_qty}")
        # OCR 失败也退出，避免停在炼药界面空转
        if craft_qty is None or craft_qty <= 0:
            context.override_next(argv.node_name, ["炼药_退出界面"])
        else:
            context.override_next(argv.node_name, ["炼药_算量并输入"])
        return True


@AgentServer.custom_action("炼药_判定买钱袋")
class AlchemyMaybeBuyMoneybag(CustomAction):
    """退出炼药界面后进买钱袋；是否买金丝由钱袋_判定是否买金丝按体力决定。"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        print("[炼药_判定买钱袋] -> 买钱袋")
        context.override_next(argv.node_name, ["买钱袋"])
        return True
