# JevChat Windows · OpenAI Decisions 版

JevChat Windows 是一个运行在 Windows 上的聊天回复辅助工具。程序读取聊天窗口中可见的消息，通过本地 OCR 提取文字，再调用判断模型分析对方意图、对话紧张度和适合的回应方式。语言模型据此生成最多三条候选回复，判断模型为候选排序。

你可以选择一条建议填入聊天输入框，检查和修改后自行发送。

本仓库由 [jev-chat/jev-chat-windows](https://github.com/jev-chat/jev-chat-windows) fork 而来，新增了 OpenAI Decisions API 支持，并保留 OpenRouter 和 TypeSafe 判断来源。

## 下载与运行

从 [Releases](https://github.com/Speechlessmanbilibili/jev-chat-windows/releases) 下载 Windows 压缩包，完整解压后运行 `jev-chat-windows.exe`。请保留程序旁的 `_internal` 文件夹。

运行要求：

- Windows 10 1903 或更高版本 / Windows 11，64 位系统。
- 已打开受支持的聊天客户端及聊天窗口。
- 可以访问所选模型服务的网络连接，以及相应的 API 密钥。

本地 OCR 使用随程序附带的模型。韩语 / 日语识别使用 Windows OCR，需在系统中安装对应语言的识别组件。

## 配置模型

打开程序的“设置”页，分别配置判断模型和回复起草模型。

| 用途 | 默认来源 | 默认模型 | 密钥环境变量 |
| --- | --- | --- | --- |
| 意图判断与候选排序 | OpenAI Decisions | `gpt-6-luna` | `OPENAI_API_KEY` |
| 回复起草 | DeepSeek | `deepseek-flash` | `LLM_API_KEY` |

### OpenAI Decisions

在判断来源中选择“OpenAI Decisions”。程序直接读取 `OPENAI_API_KEY`，包括进程环境变量和 Windows 当前用户的持久环境变量。已经设置该变量时，可将设置页的密钥输入框留空。

也可以在设置页输入密钥并保存；程序会写入 Windows 用户环境变量 `OPENAI_API_KEY`。

PowerShell 中，为当前会话设置密钥：

```powershell
$env:OPENAI_API_KEY = "你的 OpenAI API 密钥"
```

持久保存到当前用户环境：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 OpenAI API 密钥", "User")
```

程序向 `https://api.openai.com/v1/decisions` 提交聊天文字和判断题，使用 `predicate`、`choice` 和 `score` 三类题目。设置页的“获取模型”会检查 `gpt-6-luna` 的访问权限并提供该模型。接口说明见 [OpenAI Decisions 官方文档](https://developers.openai.com/api/docs/guides/decisions)。

### 回复起草

起草密钥独立使用 `LLM_API_KEY`。在设置页输入起草来源的密钥并保存，或预先设置该环境变量：

```powershell
$env:LLM_API_KEY = "你的起草服务 API 密钥"
```

起草支持 DeepSeek、OpenRouter、OpenAI、Anthropic、Gemini，以及列表中的其他服务。自定义 OpenAI / Anthropic 兼容来源需要填写 Base URL 和模型名称。

所有起草来源均读取 `LLM_API_KEY`，包括选择 OpenAI 时。切换起草服务后，请确认密钥、模型和地址属于同一服务。

### 其他判断来源

选择 OpenRouter 或 TypeSafe 时，判断密钥使用 `JEV_API_KEY`。OpenRouter 默认模型为 `typesafe/jev-1.13`；TypeSafe 默认模型为 `jev-latest`。

旧版的 `OPENROUTER_API_KEY` 和 `DEEPSEEK_API_KEY` 仍分别作为 `JEV_API_KEY` 和 `LLM_API_KEY` 的兼容读取来源。已有配置中的服务选择会保留；首次运行默认选择 OpenAI Decisions。

![模型设置示例，使用合成数据](docs/ui_openai_models.png)

## 使用流程

1. 打开聊天客户端和需要辅助的会话。
2. 在设置页配置模型、关系背景和参考上下文条数，并保存。
3. 开启窗口采集，等待对方的新消息。
4. 查看意图分析和候选回复，选择“填入”。
5. 在聊天输入框中检查内容，按需要修改并手动发送。

程序仅分析当前窗口可见、成功识别的上下文。聊天记录切换、文字过小、图片和表情包都可能影响 OCR 结果。可使用设置中的调试视图检查识别区域和文字。

群聊可以启用“指定回复对象”，选择本次要回应的人。候选排序中的概率表示模型对选项的相对判断，紧张度范围为 0–9。

## 数据处理

- 窗口图像在内存中处理，本地 OCR 提取文字，截图不写入磁盘。
- 聊天文字会发送至你选择的判断和起草服务，用于分析及生成回复。
- 密钥保存在进程环境变量 / Windows 用户环境中，普通设置保存在程序目录下的 `config.json`。
- 聊天内容保存在本次运行的内存中，关闭程序后清除。
- 程序只执行填入操作，发送由用户完成。
- 启动时默认检查本 fork 的 GitHub Release；可在设置中关闭。

使用前请确认你有权读取相关聊天内容，并按自己的需求选择模型服务。

## 从源码运行

使用 Python 3.11 或 3.12。RapidOCR 1.4 系列依赖 Python 3.13 以下版本。

```powershell
git clone https://github.com/Speechlessmanbilibili/jev-chat-windows.git
cd jev-chat-windows
python -X utf8 -m venv .venv
.\.venv\Scripts\python.exe -X utf8 -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 main.py
```

在已有项目目录中开发时，从创建虚拟环境的步骤开始即可。

运行测试：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

使用合成聊天数据预览界面：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.preview_ui --state settings
```

使用合成对话进行实际 API 测试，需要配置判断和起草密钥，会产生 API 用量：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.demo
```

## 打包

在 Windows 中安装依赖后执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pip install pyinstaller
.\.venv\Scripts\python.exe -X utf8 -m PyInstaller --noconfirm --clean jev.spec
```

构建结果位于 `dist/jev-chat-windows/`。分发时应包含整个目录，以及 `LICENSE`、`NOTICE` 和本 README。仓库中的 GitHub Actions 工作流也提供 Windows 构建。

## 项目结构

| 目录 / 文件 | 用途 |
| --- | --- |
| `app/` | 窗口采集、OCR、界面、填入、设置与更新检查 |
| `core/openai_decisions.py` | OpenAI Decisions 请求与响应转换 |
| `core/jev_client.py` | 判断来源路由及错误处理 |
| `core/questions.py` | 意图判断题、排序题及判断摘要 |
| `core/draft.py` / `core/llm.py` | 候选回复生成和模型接口适配 |
| `core/engine.py` | 判断、起草和排序的调用流程 |
| `tests/` | 接口契约、密钥隔离和引擎集成测试 |

## 许可证与致谢

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。原项目及相关组件的版权说明见 [NOTICE](NOTICE)。

感谢原项目作者与贡献者，以及 RapidOCR、ONNX Runtime、PySide6 和其他开源依赖的维护者。
