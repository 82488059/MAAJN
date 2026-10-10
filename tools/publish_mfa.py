"""将 assets + agent 发布到 MFAAvalonia 目录（interface.json + resource/base + agent）。"""
import argparse
import shutil
import sys
from pathlib import Path

try:
    import jsonc
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments'.\n"
        f"Install: {sys.executable} -m pip install json-with-comments"
    ) from e

from configure import configure_ocr_model

ROOT = Path(__file__).parent.parent.resolve()
ASSETS = ROOT / "assets"
AGENT = ROOT / "agent"
DEFAULT_MFA = Path("E:/repos/MFAAvalonia")


def publish_mfa(mfa_dir: Path) -> None:
    if not mfa_dir.is_dir():
        print(f"MFAAvalonia 目录不存在: {mfa_dir}")
        sys.exit(1)

    configure_ocr_model()

    base_dir = mfa_dir / "resource" / "base"
    base_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(ASSETS / "resource", base_dir, dirs_exist_ok=True)

    agent_dst = mfa_dir / "agent"
    agent_dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "main.py",
        "alchemy_action.py",
        "tiangong_action.py",
        "moneybag_action.py",
        "debug_action.py",
        "my_action.py",
        "my_reco.py",
    ):
        src = AGENT / name
        if src.is_file():
            shutil.copy2(src, agent_dst / name)

    with open(ASSETS / "interface.json", encoding="utf-8") as f:
        interface = jsonc.load(f)

    # MFAAvalonia 约定资源在 resource/base
    interface["resource"] = [
        {
            "name": "官服",
            "path": ["{PROJECT_DIR}/resource/base"],
        }
    ]

    with open(mfa_dir / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)

    # 避免 MFA 误载 resource/pipeline（仅 sample）导致入口节点缺失、任务瞬间失败
    stale_pipeline = mfa_dir / "resource" / "pipeline"
    if stale_pipeline.is_dir():
        sample_only = sorted(p.name for p in stale_pipeline.glob("*.json")) == ["sample.json"]
        if sample_only or not any(stale_pipeline.glob("medicine_task.json")):
            shutil.rmtree(stale_pipeline)
            print(f"  已删除过期目录: {stale_pipeline}")

    print(f"已发布到: {mfa_dir}")
    print(f"  interface.json (resource → {{PROJECT_DIR}}/resource/base)")
    print(f"  resource/base/ (pipeline, image, model)")
    agent_files = ", ".join(p.name for p in sorted(agent_dst.glob("*.py")))
    print(f"  agent/ ({agent_files})")
    print("任务:", [t["name"] for t in interface.get("task", [])])
    print("\n请重启 MFAAvalonia.exe 以重载 interface.json，资源选「官服」后连接开始。")
    print("跑自动炼药/自动买钱/一条龙前需: python -m pip install maafw==5.8.1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发布 MAAJN 资源到 MFAAvalonia")
    parser.add_argument(
        "mfa_dir",
        nargs="?",
        default=str(DEFAULT_MFA),
        help=f"MFAAvalonia 目录，默认 {DEFAULT_MFA}",
    )
    publish_mfa(Path(parser.parse_args().mfa_dir).resolve())
