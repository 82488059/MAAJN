import json
import re
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


_SLASH = re.compile(r"(\d+)\s*[/／]\s*(\d+)")

_TIER_RECIPES = {
    "淬": ["淬火油", "淬水蜡", "淬毒散"],
    "三级": ["积火脂·三级", "积水蜡·三级", "积毒锭·三级"],
    "二级": ["积火脂·二级", "积水蜡·二级", "积毒锭·二级"],
}

_QUEUE: list[str] = []
_QUEUE_I = 0
_LIST_ROI = (20, 90, 680, 560)
_MAX_SCROLL_PAGES = 6


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


def _norm_sep(name: str) -> str:
    for sep in (".", "．", "・", "•"):
        name = name.replace(sep, "·")
    return name.strip()


def _name_variants(name: str) -> list[str]:
    """
    生成 OCR expected：只输出 ^全名$ 锚定式。
    禁止裸子串，否则「淬火油」会命中「淬火油·灼焰」等基础→高阶误匹配。
    """
    stem = _norm_sep(name)
    raw = [stem]
    for sep in (".", "．", "・", "•"):
        raw.append(stem.replace("·", sep))
    if "·" in stem:
        raw.append(stem.replace("·", "："))
        raw.append(stem.replace("·", ":"))
    seen = set()
    out = []
    for item in raw:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(f"^{item}$")
    return out


def _text_is_exact_recipe(text: str, name: str) -> bool:
    """标题/列表文案是否与目标配方全名一致（归一分隔符后）。"""
    a = _norm_sep(text).replace(" ", "")
    b = _norm_sep(name).replace(" ", "")
    return bool(a) and a == b


def _unique(seq: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _read_qty_pair(context: Context):
    """返回 (当前, 上限, 数量框, 说明)。只用流水线节点，避免 post_recognition 卡住。"""
    img = context.tasker.controller.post_screencap().wait().get()
    reco = context.run_recognition("天工_读数量", img)
    q_text = _ocr_text(reco)
    qty_box = _reco_hit_box(reco)
    qty_pair = _parse_slash(q_text)
    if qty_pair is None:
        return None, None, qty_box, f"OCR失败 qty={q_text!r}"
    cur, limit = qty_pair
    return cur, limit, qty_box, f"cur={cur} limit={limit} qty={q_text!r}"


def _craftable_limit(context: Context):
    cur, limit, _box, detail = _read_qty_pair(context)
    if limit is None:
        return None, detail
    if limit <= 0:
        return 0, detail
    return limit, detail


def _click_max_by_template(context: Context) -> bool:
    """模板识别「最大」再点中心，不盲点坐标。"""
    img = context.tasker.controller.post_screencap().wait().get()
    reco = context.run_recognition("天工_点最大", img)
    box = _reco_hit_box(reco)
    if box is None:
        print("[天工_算量并输入] 最大模板未命中")
        return False
    print(f"[天工_算量并输入] 最大模板 box={list(box)}")
    _click_box(context, box)
    return True


def _set_qty_to_max(context: Context, craft_qty: int) -> tuple[bool, str]:
    """只模板点「最大」。未涨到 ≥2 则失败（禁止小键盘/坐标盲点）。"""
    for attempt in range(2):
        if not _click_max_by_template(context):
            break
        time.sleep(0.2)
        cur, limit, _box, detail = _read_qty_pair(context)
        print(f"[天工_算量并输入] 点最大#{attempt + 1} {detail}")
        if cur is not None and limit is not None and cur >= 2:
            return True, f"最大按钮成功 {detail}"
    cur, limit, _box, detail = _read_qty_pair(context)
    return False, f"最大未生效 {detail}"


def _input_qty(context: Context, craft_qty: int, fail_node: str, submit_node: str, node_name: str) -> bool:
    ok, detail = _set_qty_to_max(context, craft_qty)
    if not ok:
        print(f"[天工_算量并输入] {detail} -> {fail_node}")
        context.override_next(node_name, [fail_node])
        return True
    print(f"[天工_算量并输入] 改数量 {detail} -> {submit_node}")
    context.override_next(node_name, [submit_node])
    return True


def _apply_recipe_override(context: Context, name: str) -> None:
    """覆盖列表/标题 OCR expected；缺材料取消后进队列下一项。"""
    expected = _name_variants(name)
    context.override_pipeline(
        {
            "天工_点配方": {"expected": expected},
            "天工_读标题": {"expected": expected},
            "天工_缺材料点取消": {"next": ["天工_队列下一项"]},
        }
    )


def _reco_hit_box(reco):
    if reco is None or not getattr(reco, "hit", False):
        return None
    best = getattr(reco, "best_result", None)
    if best is None:
        return None
    box = getattr(best, "box", None)
    if box is None or len(box) < 4:
        return None
    return box


def _reco_exact_list_box(reco, name: str):
    """只点列表里全名完全一致的项，避免基础名点到高阶。"""
    if reco is None or not getattr(reco, "hit", False):
        return None
    candidates = []
    best = getattr(reco, "best_result", None)
    if best is not None:
        candidates.append(best)
    for key in ("filterd_results", "filtered_results", "all_results"):
        for r in getattr(reco, key, None) or []:
            candidates.append(r)
    for r in candidates:
        text = str(getattr(r, "text", "") or "")
        box = getattr(r, "box", None)
        if box is None or len(box) < 4:
            continue
        if int(box[0]) >= 700:
            continue
        if _text_is_exact_recipe(text, name):
            return box
    return None


def _title_is_recipe(context: Context, name: str, img) -> bool:
    """右侧详情标题是否已是当前配方（全名精确；禁止子串当成已选中）。"""
    reco = context.run_recognition("天工_读标题", img)
    return _text_is_exact_recipe(_ocr_text(reco), name)


def _click_box(context: Context, box) -> None:
    x = int(box[0] + box[2] / 2)
    y = int(box[1] + box[3] / 2)
    context.tasker.controller.post_click(x, y).wait()
    time.sleep(0.45)


def _scroll_list(context: Context, down: bool) -> None:
    ctrl = context.tasker.controller
    if down:
        ctrl.post_swipe(340, 500, 340, 200, 400).wait()
    else:
        ctrl.post_swipe(340, 200, 340, 500, 400).wait()
    time.sleep(0.45)


def _find_click_recipe(context: Context, name: str) -> bool:
    """
    找当前配方并点选。
    - 右侧标题已是该项：视为找到，绝不翻页。
    - 列表命中：点一次即返回，不再为该项继续滑。
    - 限次下翻仍没有：只回翻实际下翻次数后 False（交给队列下一项）。
    """
    _apply_recipe_override(context, name)
    img = context.tasker.controller.post_screencap().wait().get()
    if _title_is_recipe(context, name, img):
        print(f"[天工_找并点配方] 已在详情 {name}，不翻页")
        return True

    scrolled = 0
    for page in range(_MAX_SCROLL_PAGES):
        if page > 0:
            img = context.tasker.controller.post_screencap().wait().get()
            if _title_is_recipe(context, name, img):
                print(f"[天工_找并点配方] page={page} 详情已是 {name}，停止翻页")
                return True
        reco = context.run_recognition("天工_点配方", img)
        box = _reco_exact_list_box(reco, name)
        if box is not None:
            print(f"[天工_找并点配方] page={page} 精确点 {name} box={list(box)}")
            _click_box(context, box)
            # 点完核对右侧标题，防止误点高阶
            time.sleep(0.25)
            after = context.tasker.controller.post_screencap().wait().get()
            if _title_is_recipe(context, name, after):
                return True
            got = _norm_sep(_ocr_text(context.run_recognition("天工_读标题", after)))
            print(f"[天工_找并点配方] 点后标题是 {got!r}，不是 {name}，继续找")
        else:
            print(f"[天工_找并点配方] page={page} 未见精确名 {name}，下翻")
        _scroll_list(context, down=True)
        scrolled += 1

    for _ in range(scrolled):
        _scroll_list(context, down=False)
    print(f"[天工_找并点配方] 未找到 {name}，跳过（队列下一项）")
    return False


# checkbox 各 case 用独立节点 enabled=true（勿写 custom_action_param：MFA 整段替换只会剩最后一项）
_SELECT_FLAG_NODES = [
    "天工_勾选_tier淬",
    "天工_勾选_tier三级",
    "天工_勾选_tier二级",
    "天工_勾选_淬火油灼焰",
    "天工_勾选_淬火油焚烬",
    "天工_勾选_淬水蜡渊渟",
    "天工_勾选_淬水蜡浩溟",
    "天工_勾选_淬毒散鸩炎",
    "天工_勾选_淬毒散凝煞",
    "天工_勾选_淬火油",
    "天工_勾选_淬水蜡",
    "天工_勾选_淬毒散",
    "天工_勾选_积火脂三级",
    "天工_勾选_积水蜡三级",
    "天工_勾选_积毒锭三级",
    "天工_勾选_积火脂二级",
    "天工_勾选_积水蜡二级",
    "天工_勾选_积毒锭二级",
]


def _recipes_from_checkbox_param(param: dict) -> list[str]:
    """从 param 字典建队列。键：tier_* / 配方全名 / recipes 列表。"""
    picked: list[str] = []
    for key in ("淬", "三级", "二级"):
        if param.get(f"tier_{key}"):
            picked.extend(_TIER_RECIPES[key])
    extras = []
    for key, value in param.items():
        if not isinstance(key, str) or key.startswith("tier_"):
            continue
        if not value:
            continue
        if key.startswith("积") or key.startswith("淬") or "·" in key:
            extras.append(_norm_sep(key))
    order = (
        list(_TIER_RECIPES["淬"])
        + list(_TIER_RECIPES["三级"])
        + list(_TIER_RECIPES["二级"])
    )
    for name in order:
        if name in extras and name not in picked:
            picked.append(name)
    for name in sorted(extras):
        if name not in picked:
            picked.append(name)
    recipes = param.get("recipes")
    if isinstance(recipes, list):
        for name in recipes:
            n = _norm_sep(str(name))
            if n and n not in picked:
                picked.append(n)
    tier = str(param.get("tier") or "").strip()
    if tier in _TIER_RECIPES:
        for name in _TIER_RECIPES[tier]:
            if name not in picked:
                picked.append(name)
    return _unique(picked)


def _recipes_from_enabled_flags(context: Context) -> list[str]:
    """读流水线里各勾选标记节点的 enabled（含 interface override 合并结果）。"""
    param: dict = {}
    enabled_nodes: list[str] = []
    for node in _SELECT_FLAG_NODES:
        data = context.get_node_data(node) or {}
        if not data.get("enabled"):
            continue
        enabled_nodes.append(node)
        attach = data.get("attach") or {}
        tier = attach.get("tier")
        if tier in _TIER_RECIPES:
            param[f"tier_{tier}"] = True
        recipe = attach.get("recipe")
        if isinstance(recipe, str) and recipe:
            param[_norm_sep(recipe)] = True
    print(f"[天工_开始多选队列] enabled_flags={enabled_nodes}")
    return _recipes_from_checkbox_param(param)


@AgentServer.custom_action("天工_算量并输入")
class TiangongCalcAndInput(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        craft_qty, detail = _craftable_limit(context)
        print(f"[天工_算量并输入] {detail} -> qty={craft_qty}")
        if craft_qty is None or craft_qty <= 1:
            print("[天工_算量并输入] 不可炼/OCR失败 -> 天工_队列下一项")
            context.override_next(argv.node_name, ["天工_队列下一项"])
            return True
        return _input_qty(
            context, craft_qty, "天工_队列下一项", "天工_点提交", argv.node_name
        )


@AgentServer.custom_action("天工_耗尽则退出")
class TiangongExitIfDepleted(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # 结算刚关可能遮挡数量栏：OCR 失败先短等再读一次，勿直接跳队列
        craft_qty, detail = _craftable_limit(context)
        if craft_qty is None:
            time.sleep(0.5)
            craft_qty, detail = _craftable_limit(context)
        print(f"[天工_耗尽则退出] {detail} -> qty={craft_qty}")
        if craft_qty is None:
            print("[天工_耗尽则退出] OCR仍失败，再试算量并输入")
            context.override_next(argv.node_name, ["天工_算量并输入"])
        elif craft_qty <= 1:
            # 当前材料炼完：始终进队列下一项（由队列节点决定是否还有下一项）
            print("[天工_耗尽则退出] 材料耗尽 -> 天工_队列下一项")
            context.override_next(argv.node_name, ["天工_队列下一项"])
        else:
            context.override_next(argv.node_name, ["天工_算量并输入"])
        return True


@AgentServer.custom_action("天工_找并点配方")
class TiangongFindAndClick(CustomAction):
    """找当前队列配方；材料不足/找不到 → 队列下一项（直到最后一项），禁止为缺材料项继续翻页。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not _QUEUE or _QUEUE_I >= len(_QUEUE):
            context.override_next(argv.node_name, ["天工_退出界面"])
            return True
        name = _QUEUE[_QUEUE_I]
        print(f"[天工_找并点配方] 当前 {_QUEUE_I + 1}/{len(_QUEUE)} {name}")
        found = _find_click_recipe(context, name)
        if not found:
            print(f"[天工_找并点配方] 未找到 {name} -> 队列下一项")
            context.override_next(argv.node_name, ["天工_队列下一项"])
            return True
        # 已找到：只看能不能炼；材料不足直接下一项，不再翻列表
        craft_qty, detail = _craftable_limit(context)
        print(f"[天工_找并点配方] 已找到 {name} {detail} qty={craft_qty}")
        if craft_qty is None or craft_qty <= 1:
            print(
                f"[天工_找并点配方] 材料不足，换下一项 "
                f"({_QUEUE_I + 1}/{len(_QUEUE)} -> 下一项)"
            )
            context.override_next(argv.node_name, ["天工_队列下一项"])
            return True
        context.override_next(argv.node_name, ["天工_算量并输入"])
        return True


@AgentServer.custom_action("天工_开始多选队列")
class TiangongStartMultiQueue(CustomAction):
    """按勾选标记节点建队列；全部项跑完才退出界面。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global _QUEUE, _QUEUE_I
        recipes = _recipes_from_enabled_flags(context)
        # 兼容旧 custom_action_param（单选时尚可用；多选会被 MFA 替换只剩最后一项）
        if not recipes:
            param = _parse_param(argv.custom_action_param)
            recipes = _recipes_from_checkbox_param(param)
            if recipes:
                print(f"[天工_开始多选队列] fallback custom_action_param={param}")
        if not recipes:
            print("[天工_开始多选队列] 未勾选材料 -> 退出")
            context.override_next(argv.node_name, ["天工_退出界面"])
            return True
        _QUEUE = recipes
        _QUEUE_I = 0
        print(f"[天工_开始多选队列] queue={_QUEUE} ({len(_QUEUE)}项)")
        _apply_recipe_override(context, _QUEUE[0])
        context.override_next(argv.node_name, ["天工_找并点配方"])
        return True


@AgentServer.custom_action("天工_队列下一项")
class TiangongQueueNext(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        global _QUEUE_I, _QUEUE
        if not _QUEUE:
            context.override_next(argv.node_name, ["天工_退出界面"])
            return True
        _QUEUE_I += 1
        if _QUEUE_I >= len(_QUEUE):
            print("[天工_队列下一项] 队列结束 -> 退出界面")
            _QUEUE = []
            _QUEUE_I = 0
            context.override_next(argv.node_name, ["天工_退出界面"])
            return True
        name = _QUEUE[_QUEUE_I]
        print(f"[天工_队列下一项] -> {name} ({_QUEUE_I + 1}/{len(_QUEUE)})")
        _apply_recipe_override(context, name)
        context.override_next(argv.node_name, ["天工_找并点配方"])
        return True
