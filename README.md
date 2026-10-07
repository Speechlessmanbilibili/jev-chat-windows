# JevChat Windows · OpenAI Decisions 版

JevChat Windows 是一个运行在 Windows 上的聊天意图分析工具。程序读取聊天窗口中可见的消息，通过本地 OCR 提取文字，再调用判断模型评估对方的意图、语气和对话紧张度。

首页以百分比展示各项意图和语气的体现程度。回复起草默认折叠；需要时展开并点击“生成回复”，即可获取最多三条候选，选择一条填入聊天输入框，检查和修改后自行发送。

本仓库由 [jev-chat/jev-chat-windows](https://github.com/jev-chat/jev-chat-windows) fork 而来，新增了 OpenAI Decisions API 支持，并保留 OpenRouter 和 TypeSafe 判断来源。

## 下载与运行

从 [Releases](https://github.com/Speechlessmanbilibili/jev-chat-windows/releases) 下载 Windows 压缩包，完整解压后运行 `jev-chat-windows.exe`。请保留程序旁的 `_internal` 文件夹。

运行要求：

- Windows 10 1903 或更高版本 / Windows 11，64 位系统。
- 已打开受支持的聊天客户端及聊天窗口。
- 可以访问所选模型服务的网络连接，以及相应的 API 密钥。

本地 OCR 使用随程序附带的模型。韩语 / 日语识别使用 Windows OCR，需在系统中安装对应语言的识别组件。

## 配置模型

打开程序的“设置”页，配置判断模型即可开始分析。回复起草设置为可选项，默认折叠。

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

程序向 `https://api.openai.com/v1/decisions` 提交聊天文字和判断题。每次新消息的分析使用一次请求，包含 18 道意图评分题、10 道语气评分题和一道紧张度评分题，类型均为 `score`。生成回复后的候选排序另用 `choice` 题。设置页的“获取模型”会检查 `gpt-6-luna` 的访问权限并提供该模型。接口说明见 [OpenAI Decisions 官方文档](https://developers.openai.com/api/docs/guides/decisions)。

### 回复起草

需要生成回复时，展开“回复起草设置（可选）”并配置起草来源。起草密钥独立使用 `LLM_API_KEY`。在设置页输入密钥并保存，或预先设置该环境变量：

```powershell
$env:LLM_API_KEY = "你的起草服务 API 密钥"
```

起草支持 DeepSeek、OpenRouter、OpenAI、Anthropic、Gemini，以及列表中的其他服务。自定义 OpenAI / Anthropic 兼容来源需要填写 Base URL 和模型名称。

所有起草来源均读取 `LLM_API_KEY`，包括选择 OpenAI 时。切换起草服务后，请确认密钥、模型和地址属于同一服务。

### 其他判断来源

选择 OpenRouter 或 TypeSafe 时，判断密钥使用 `JEV_API_KEY`。OpenRouter 默认模型为 `typesafe/jev-1.13`；TypeSafe 默认模型为 `jev-latest`。

旧版的 `OPENROUTER_API_KEY` 和 `DEEPSEEK_API_KEY` 仍分别作为 `JEV_API_KEY` 和 `LLM_API_KEY` 的兼容读取来源。已有配置中的服务选择会保留；首次运行默认选择 OpenAI Decisions。

![模型设置示例，使用合成数据](docs/ui_openai_models.png)

## 意图与语气评分

每个标签独立评估，界面默认展示程度最高的四项，点击“展开全部”可查看全部标签。缺失或拒答的项目显示“—”。

意图包括打招呼、闲聊、分享、询问信息、请求帮助、要求行动、提醒、催促、问责、追问解释、寻求关心、邀请、协商、确认、感谢、道歉、拒绝和结束话题。

语气包括友好、平静、关切、轻松、急切、不满、愤怒、讽刺、冷淡和犹豫。

意图与语气各使用五个有序等级，模型返回等级索引的加权平均分数 `score`，范围为 0–4。意图从“没有相关证据”到“非常明确的核心目的”；语气从“未体现”到“强烈”。显示值为 `score / 4 × 100`，四舍五入为整数。例如，`score = 3.42` 显示为 `86%`。

这些百分比表示体现程度。各项独立，多种意图可以同时获得较高评分，总和无需等于 100%。紧张度单独使用 0–9 的量表。

![意图与语气分析示例，使用合成数据](docs/ui_intent.png)

## 使用流程

1. 打开聊天客户端和需要辅助的会话。
2. 在设置页配置判断模型、关系背景和参考上下文条数，并保存。
3. 开启窗口采集，等待对方的新消息。
4. 查看意图、语气和紧张度。新消息到来后，分析自动更新。
5. 如需回复建议，展开起草区域，点击“生成回复”。展开操作只改变显示状态。
6. 选择候选并点击“填入”，在聊天输入框中检查内容，按需要修改并手动发送。

程序仅分析当前窗口可见、成功识别的上下文。聊天记录切换、文字过小、图片和表情包都可能影响 OCR 结果。可使用设置中的调试视图检查识别区域和文字。

群聊可以启用“指定回复对象”，选择本次要分析和回应的人。起草区域中候选的排序概率表示模型对各选项的相对判断。

各会话分别保存本次运行中的上下文和结果。新消息或分析对象变化后，旧候选立即失效；后台返回的过期结果会被丢弃。起草失败的提示显示在起草区域，已完成的意图与语气分析继续保留。

## 数据处理

- 窗口图像在内存中处理，本地 OCR 提取文字，截图不写入磁盘。
- 自动分析时，聊天文字会发送至你选择的判断服务；点击“生成回复”后，相关文字才会发送至起草服务。
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

使用合成对话进行实际 API 测试，需要配置判断密钥，会产生 API 用量：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.demo --cases
```

添加 `--draft` 可额外验证回复起草和排序，此时还需配置起草密钥。

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
| `core/intent.py` | 意图与语气标签、评分标准、百分比换算 |
| `core/questions.py` | 上下文整理和回复排序题 |
| `core/draft.py` / `core/llm.py` | 候选回复生成和模型接口适配 |
| `core/engine.py` | 判断、起草和排序的调用流程 |
| `tests/` | 接口契约、密钥隔离和引擎集成测试 |

## 许可证与致谢

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。原项目及相关组件的版权说明见 [NOTICE](NOTICE)。

感谢原项目作者与贡献者，以及 RapidOCR、ONNX Runtime、PySide6 和其他开源依赖的维护者。
