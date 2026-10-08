# MAAYY

**MAAYY** 是面向《燕云十六声》的 MuMu / Adb 自动化项目，基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 构建。

仓库地址：<https://github.com/82488059/MAAYY>

> **MaaFramework** 是基于图像识别的自动化框架，详见其仓库说明。

## 文档

中文说明与任务专文见：[docs/zh_cn/README.md](./docs/zh_cn/README.md)

任务细节请阅读对应专文，本文不展开。

## 开发准备

1. 克隆本仓库：

    ```bash
    git clone https://github.com/82488059/MAAYY.git
    ```

2. 从 [MaaFramework Releases](https://github.com/MaaXYZ/MaaFramework/releases) 下载并解压到 `deps/`。

3. 下载 OCR 资源 [ppocr_v5.zip](https://download.maafw.xyz/MaaCommonAssets/OCR/ppocr_v5/ppocr_v5-zh_cn.zip)，解压到 `assets/resource/model/ocr/`（需含 `det.onnx`、`keys.txt`、`rec.onnx`）。该目录已由 `.gitignore` 忽略，发版时由 workflow 自动配置。

4. 按业务修改 `assets` 等资源后开发调试；更多见中文文档中的本地开发说明。

## 发版

打 tag 并推送即可触发 CI 发版（仓库需已开启 Actions 的读写权限）：

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 鸣谢

本项目由 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 驱动。