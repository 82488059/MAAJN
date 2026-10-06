# MaaJNBJ 项目文档

本目录是 MaaJNBJ 的中文说明。内容根据仓库里的 `assets/interface.json`、`assets/resource/pipeline/`、`tools/` 和 `.github/workflows/` 整理，描述的是当前代码的实际行为。

`个性化配置.md` 是模板自带的说明，原文保留，没有改动。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [项目概览](项目概览.md) | 项目是什么、界面里有哪些任务、目录各自做什么 |
| [任务流程](任务流程.md) | 每条流水线的入口、节点链路、识别图、等待时间和异常分支 |
| [本地开发与调试](本地开发与调试.md) | 依赖、OCR 模型、连接模拟器、运行方式、schema 校验 |
| [发布流程](发布流程.md) | `check`、`install`、Mirror酱和 schema 同步这几条 GitHub Actions |
| [模板遗留与待改进](模板遗留与待改进.md) | 仍指向模板仓库的配置、未接入的流水线和未引用的资源 |
| [个性化配置](个性化配置.md) | 模板原有的 Issue 模板、编辑器插件和格式化说明 |

根目录的 [README.md](../../README.md) 仍是 MaaPracticeBoilerplate 模板的快速开始和 FAQ。
