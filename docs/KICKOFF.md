# JevChat Windows — 开发接续说明

程序在 Windows 上通过窗口截图和本地 OCR 读取微信 / KakaoTalk 的可见消息，再分析意图、语气和紧张度。回复由用户点击后生成；程序只填入输入框，发送由用户操作。

## 数据和凭据

- 采集与调试画面在内存中处理，OCR 提取的上下文提交到所选判断来源。
- OpenAI 判断读取 `OPENAI_API_KEY`，其他云端判断读取 `JEV_API_KEY`，本地 LM Studio 可选认证读取 `LMSTUDIO_API_TOKEN`。起草统一读取独立的 `LLM_API_KEY`。
- 密钥保存到 Windows 用户环境变量。普通配置保存在被 Git 忽略的 `config.json`，启动时加载为快照，保存通过原子替换更新；读取失败时明确报错。
- 采集使用 Windows Graphics Capture，文字识别使用 RapidOCR / Windows OCR。填入前重新检查当前会话标题和输入区域，随后粘贴文字。

## 当前结构

| 文件 | 职责 |
| --- | --- |
| `main.py` | 会话状态、后台任务与版本校验；新消息和配置变化使旧结果失效 |
| `app/worker.py` | 独立进程采集、识别和按会话增量对齐；故障停止并上报原因 |
| `app/capture.py` / `app/ocr.py` | WGC 画面、区域定位、发言人识别和消息去重 |
| `app/overlay.py` / `app/settings_panel.py` / `app/widgets.py` | 主界面、设置页和可复用控件 |
| `core/intent.py` | 18 项意图、10 项语气和 1 项紧张度的独立评分题 |
| `core/engine.py` | `analyze(messages, relationship)` 构建状态；`generate_replies(analysis)` 使用同一状态起草和排序 |
| `core/jev_client.py` | OpenAI / OpenRouter / TypeSafe / LM Studio 判断来源路由 |
| `core/draft.py` / `core/llm.py` | 一轮起草及三种生成协议；接受完整 JSON 字符串数组 |

分析是一次 29 题请求；起草是一次独立请求；两条及以上候选另发一次排序请求。排序失败保留平级候选并显示提示，单条候选直接展示。多标签分数互相独立，展示百分比是程度。

## 开发与验证

使用 Python 3.12，安装 `requirements.txt`。源码入口是 `python -X utf8 main.py`；工具通过模块运行，例如 `python -X utf8 -m tools.demo`。

- 自动化验证：`python -X utf8 -m unittest discover -s tests -v`。测试使用独立配置。
- 合成界面预览：`python -X utf8 -m tools.preview_ui --state draft`。
- 本地决策评估：`python -X utf8 -m tools.evaluate_decisions --output docs/evaluations/local.json`。场景和高低标签阈值预先固定，结果保留完整答案和请求耗时。
- 构建统一由 `tools/build_release.ps1` 执行；`build.bat` 和 GitHub 工作流调用同一入口。完整分发 onedir 文件夹。

审查记录见 `docs/reviews/2026-10-20-code-audit.md`；旧探针和原始实现保留在 Git 历史中。
