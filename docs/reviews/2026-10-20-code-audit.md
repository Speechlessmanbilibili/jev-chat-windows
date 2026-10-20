# 代码审查与精简建议

日期：2026-10-20（Asia/Shanghai）

基线：`883139ec185be2f868c59c0a5beccf7de1e770a4` / `v0.3.3`

本轮交付：代码审查、现有测试评估和调查留档；业务代码、测试及依赖配置保持原样。

## 判断先放在前面

值得激进精简。最需要处理的是“正常内容被过滤”“失败被补成正常结果”和“异常一直循环”这三类行为；单纯缩短代码排在后面呢。

推荐删除回复起草的关键词注入扫描、回声黑名单、逐行抢救解析和自动补齐请求，留下明确的模型输入、JSON 数组解析及候选去重。会话版本号、密钥隔离、Windows 指针声明、外部响应的必要校验和配置原子写入继续保留，它们对应具体的并发、权限和数据边界。

现有测试中，建议删除 6 个测试方法、合并 2 个方法到已有用例，余下 47 个方法保留或缩减断言。另有 8 处业务模块内自测，共 371 行；推荐删除这套分散入口，只将其中仍独有且有实际价值的检查归入现有测试。这里的 47 是本轮逐项处置后的数量，不是以后必须维持的指标哦。

## 审查范围与实际检查

- 运行源码：`main.py`、`app/`、`core/`，共 23 个 Python 文件、4,951 行，包含空行和注释。
- 自动化测试：7 个文件、55 个测试方法，逐项阅读；当前环境执行一次，55 项全部通过。
- 开发和构建：`tools/`、10 个 `probe_*.py`、`jev.spec`、`requirements.txt`、`build.bat`、本地发布脚本和 Release 工作流。
- 文档：README、旧接续说明及翻译表；核对生产调用、旧别名和自测入口的引用。
- 使用独立进程和模拟输入复现候选误过滤、拒答被解析成候选、OCR 漏消息、缺失排序默认推荐和测试配置泄漏。
- 本轮没有调用付费模型接口，也没有向真实聊天窗口执行填入。

## 发现与建议

优先级：P1 表示直接影响消息或回复正确性；P2 表示维护、错误处理和操作流程需要调整；P3 表示低风险清理。

### A01 / P1：关键词和回声过滤会删掉正常回复

位置：`core/draft.py:103—149`、`188—191`、`214—226`。

`_INJECT` 把“必须”“重复”“输出”等普通词视为注入迹象；`_sanitize()` 再按去标点后的子串过滤候选，并禁止重复对方最近说过的话。聊天中的确认、复述和礼貌呼应本来就经常需要这些形式。

已复现：对方说“明天必须八点到，别迟到”，候选“八点到”被删除；对方说“晚安”，候选“晚安”也被删除。`_norm()` 还会丢掉有语义的标点，例如技术名称之间的差别。

建议：删除 `_INJECT`、`_LAUGH`、`_suspects()`、`_her_recent()` 和基于消息子串的拒绝规则；候选仅做空白清理和文本去重。提示词保留清晰的角色、聊天内容边界与本次回复目标即可。对应自测中要求这些误杀规则成立的断言一并删除。

### A02 / P1：宽松解析把模型说明和拒答收成回复

位置：`core/draft.py:45—100`。

整体 JSON 失败后，解析器会逐行尝试 JSON、正则提取方括号内容，最后直接接收普通文本。`_clean()` 还擅自剥去引号、括号和句末句号，改变用户看到的内容。

已复现：输入“抱歉，我无法生成这些回复。”，返回一条候选“抱歉，我无法生成这些回复”。这段解析没有识别业务成功，只是从任意文本里捞出了非空字符串。

建议：只接受完整 JSON 字符串数组，可保留一次完整外层代码围栏处理；拒绝混合类型和数组外的说明。不再支持编号列表、每行一个数组、多个数组挤在一行等修补格式。删除只供自测使用的 `_parse_three()`，标点保留原样。

### A03 / P1：OCR 的全局历史兜底会整段漏掉新消息

位置：`app/ocr.py:159—190`，尤其是 `183—186`。

当前规则在连续序列无法对齐时，只要本帧任意一条消息匹配历史中的任意一条，就直接返回空列表。这把“画面里有旧消息”扩展成了“整帧都是旧消息”。

已复现：历史为 `[旧消息 A, 旧消息 B]`，下一帧为 `[旧消息 A, 全新消息 C]`，返回 `[]`。OCR 中间一条漏识别或聊天布局改变后，就会进入这种分支；新消息 C 没有入库，下一帧仍可能重复丢弃。

建议：删除任意交集即整帧丢弃的规则。用相邻画面中可定位的连续锚点判断增量，已确认的历史片段才整体跳过；锚点缺失时明确重新建立当前画面的基线。继续保留对重复消息数量和发言人的区分。

### A04 / P1：排序答案缺失后默认把第一条称为推荐

位置：`core/engine.py:54—64`、`app/overlay.py:1363—1373`。

引擎把不存在的 `best_reply` 补成空字典，把未知选项补成索引 0；UI 又把无效推荐索引补成 0。两层兜底最后都会生成一张“推荐回复”卡片。

已复现：排序返回 `answers={}`、`refused=[best_reply]` 时，结果为 `best_index=0`、`best_reply=甲`、`scores=[0,0,0]`。OpenAI 全部拒答路径会先抛错；这个样例覆盖其他适配器或不完整响应进入引擎后的行为。

建议：有效排序才能产生推荐索引；缺失排序时平等展示候选并说明排序失败，或直接将排序失败交给起草区域。引擎输出建立明确契约后，删除 UI 的第二次索引修补。

### A05 / P2：配置读取失败静默回默认值，会改变服务选择

位置：`app/settings.py:38—68`、`79—102`、`187—218`。

`_read()` 将权限错误、损坏 JSON 和文件不存在合并处理。之后任意单项保存会按这些默认值重新拼接整份配置；原有模型来源、关系背景等配置可能被覆盖。

已复现：模拟 `PermissionError` 后，读取结果变为 `openai` 和 `romantic partners`，没有告知用户读取失败。

建议：只有首次启动的文件不存在使用默认配置；损坏和不可读文件显示具体错误，并暂停覆盖该文件。读取、类型处理、默认值在一个加载入口完成，业务访问器直接读取已加载配置。

### A06 / P2：配置访问反复读盘，锁和读取粒度不匹配

位置：`app/settings.py:30—56`、`79—102`、`177—243`；`app/overlay.py:814—831`。

每个字段访问器都重新打开 JSON。读取模型又读取来源；构建一次 options、保存一次单项开关、刷新一次设置页都会重复读同一份文件。`RLock` 只包住保存和 options，常规访问器仍是分散读取。

建议：启动加载一次配置，保存成功后替换内存配置；每个后台任务取得一次不可变快照。无需文件监控、热重载框架或更复杂的锁，当前 UI 本身就是设置的唯一常规写入口。

### A07 / P2：宽泛异常捕获让持续故障循环运行

位置：`main.py:311—354`、`app/worker.py:59—62`、`117—124`、`app/ocr.py:23—33`。

主循环捕获所有异常后只打印堆栈；正式 GUI 构建没有控制台。采集循环捕获所有异常后继续，固定故障可以每 50 ms 再发生一次。Windows OCR 初始化的所有失败还会被统一改写为“缺少语言组件”，并缓存失败状态。

建议：网络/SDK 在线程边界转成任务失败，临时图像不合格跳过本帧，采集器或 OCR 初始化失败直接停止该次采集并显示真实原因。删除底层重复包装和永久失败缓存，避免错误名称失真。更新检查的预期网络失败可以安静返回，它属于可选功能。

### A08 / P2：回复目标的过期检查和数据整理重复

位置：`main.py:128—134`、`165—180`、`340—345`；`core/engine.py:38—50`；`core/draft.py:177—181`。

生产入口起草时使用分析保存的 `_messages` 和 `_options`，完成后又按会话 `rev` 丢弃过期任务；引擎仍重新比较 `reply_target` 和 `analyzed_text`，起草函数还保留自行重建目标的备用路径。

建议：消息进入系统时统一一种结构，一次构建分析状态并显式传递目标；会话调度层统一负责过期任务。删除引擎重复的旧目标比较和起草函数的备用目标构建。`_rev` 随结果保存后没有生产读取方，也应删除。目标存在性校验保留在状态构建入口。

### A09 / P2：重试次数偏重，旧请求长期占着会话分析

位置：`core/jev_client.py:135—185`；`core/openai_decisions.py:114—115`；`core/llm.py:90—92`；`main.py:150—155`。

OpenRouter 最多发起 4 次请求，退避为 1、2、4 秒。按每次 30 秒等待估算，4 次请求加退避是约 127 秒；期间新消息只更新 pending，旧请求仍占用该会话分析。自动补齐候选还可能另发一轮带 SDK 重试的起草请求。

建议：自动分析至多重试一次，并在开始下一次请求前检查任务是否已经过期。用户主动起草保持一次业务请求，SDK 的连接恢复职责留给 SDK。删除 OpenRouter 循环之后实际上到不了的最终兜底异常。无需再叠一套通用重试装饰器。

### A10 / P2：候选补齐失败被吞掉，同时放大延迟

位置：`core/draft.py:213—227`。

第一次得到 1～2 条候选后，再带着原始模型输出追问补齐；第二次任何 `JevError` 被吞掉，最后按部分成功返回。用户看不出额外请求是否失败，且等待时间、成本都增加。

建议：删除补齐请求和这处 `except JevError`。一次请求返回几条有效候选就展示几条；格式错误直接提示重新生成。排序只在至少两条有效候选时执行。

### A11 / P2：测试未完整隔离用户配置

位置：`tests/test_runtime.py:12—23`、`96—102`。

这组测试模拟了 UI、线程和队列，但仍读取真实设置中的起草来源、模型和地址。

已复现：为读取器提供 `draft_provider=custom_openai`、空地址，单独执行 `test_repeated_click_does_not_start_duplicate_draft`，因前置配置检查而没有启动线程，断言失败。默认环境下该用例通过。

建议：在公共 fixture 中一次提供完整合成配置快照；删除每个用例零散补默认设置的做法。这个用例本身有作用，修测试环境即可。

### A12 / P2：填入检查反复核对缓存，缺少即时会话识别

位置：`main.py:59—70`、`app/overlay.py:1042—1046`、`app/fill.py:55—110`。

UI 的 `_current`、主调度的 `state[chat]` 和实际填入的 hwnd 都来自异步采集缓存。微信在同一个窗口中切换会话后，到下一次 OCR 更新前，这些缓存仍可能全部指向旧会话；前台 hwnd 检查只能确认微信窗口，没有确认当前会话。

建议：将填入前的窗口、目标会话和坐标校验收敛为一次明确检查，或在会话切换尚未确认时停用填入。保留操作系统层面的激活结果检查；复制按钮则无需跟随填入一起禁用，浏览历史时允许复制更顺手呢。

### A13 / P3：业务模块自测占 371 行，测试入口分裂

| 位置 | 自测行数 | 建议 |
| --- | ---: | --- |
| `core/jev_client.py:235—366` | 132 | 删除分散入口；其中独有的 TypeSafe 映射和 OpenRouter 请求形状按需合入适配器测试 |
| `core/llm.py:201—314` | 114 | 删除假 SDK 的大量参数搬运断言，保留已有真实 SDK 契约测试 |
| `core/draft.py:230—258` | 29 | 随严格 JSON 解析删除历史格式抢救和注入黑名单断言 |
| `core/providers.py:79—101` | 23 | 删除来源表常量、默认值和列表顺序的自证断言 |
| `app/update.py:44—74` | 31 | 需要保留的版本比较/网络失败用例归入统一测试入口 |
| `app/chatapps.py:71—86` | 16 | 保留有实际像素依据的分类案例，删除单纯查字典/常量相等断言 |
| `app/ocr_windows.py:110—128` | 19 | 坐标与分段案例归入现有 OCR 测试 |
| `app/i18n.py:392—398` | 7 | 删除选定字符串相等和非空遍历自测 |

`tools/build_release.ps1:28—29` 单独运行 `core.draft`，其余模块自测又没有统一执行。删除重复命令，测试只保留 `unittest discover` 一个入口。

### A14 / P3：为脚本直跑而保留的兼容分支、旧别名和旧题型

位置：`core/` 多处 `try relative import / except ImportError`；`app/capture.py:93—95`；`app/ocr_windows.py:27—31`；`app/settings.py:175`；`core/openai_decisions.py:23—26`、`69—71`。

推荐统一 `python -m` 入口，删除相对导入失败后再猜路径的分支。`find_wechat_hwnd()` 没有生产调用方，`available()` 没有调用方；`has_key` 的调用可直接统一为 `has_jev_key`。当前产品判断题全是 `score`，排序为 `choice`；`noul/predicate` 主要留在旧探针和自测中，可随旧题型实验清理。

消息结构同样收敛：入口处理 tuple/dict 的差异，后续 `_line()`、`_suspects()`、`_her_recent()`、`build_state()` 不再分别猜结构。

### A15 / P3：旧探针重复维护正式实现，题目预期已经过时

位置：`probe/`；`tools/preview_ui.py:22—24`；`docs/KICKOFF.md:21—58`。

`probe_ocr_live.py` 和 `probe_ocr_speed.py` 各有一套窗口发现、区域定位和 OCR 逻辑；这些副本缺少正式实现后续的修复。UIA/PrintWindow/通知实验属于早期路线验证，不应再和运行源码一起维护。三个 Laya 探针仍按旧 7 题及旧意图标签描述预期，其中两个脚本在导入时就加载模型和推理。

建议：删除已经完成使命的旧探针，以 Git 历史保留实验过程。后续本地模型评估使用当前 29 道评分题和候选排序；保留一个可显式运行的评估入口即可。删除预览工具中的作者机器绝对路径，完全使用合成图。接续文档更新成当前架构或归档，避免继续按“待建 tkinter 窗口”“7 道题”指导开发。

### A16 / P3：翻译表含重复键和旧 UI 文案

位置：`app/i18n.py:93—121`、`180—199`、`265—318`。

“推荐回复”和“填入”各出现两次；旧版 true_intent/best_action 文字和多段旧设置提示已无当前运行源码引用。

建议：删除重复键、旧题型标签和替换前的整句文案。动态标签按当前 `INTENTS`、`TONES`、来源名称和诊断词汇核对，避免简单用文本搜索批量删错。

### A17 / P2：依赖兼容与打包范围没有共同基线

位置：`requirements.txt:9—15`、`core/openai_decisions.py:116—120`、`jev.spec:10—36`。

当前本机 SDK：OpenAI `3.26.0`、Anthropic `1.11.0`、TypeSafe `0.7.2`、Google GenAI `2.28.0`。依赖配置只给 OpenAI `>=2.0`，其余多数没有版本边界；代码又为早期 SDK 保留 `hasattr(client, decisions)` 兼容分支。打包按完整 SDK `collect_all()`，并重复枚举可被常规导入分析发现的本项目模块。

建议：明确一组支持的 SDK 版本，固定发布构建依赖；随后删除过旧 SDK 的备用请求分支。按真实数据资源、动态模块和已有 hooks 缩小收集范围。SOCKS 模块、OCR 模型与必要 DLL 的显式收集保留，变更打包范围时实际启动产物一次。

### A18 / P3：构建入口与少量局部代码可以直接收敛

位置：`build.bat:14—18`、`tools/build_release.ps1:25—40`、`.github/workflows/release.yml:32—49`；`app/overlay.py:966—976`。

三处分别拼构建/复制资源流程，CI 少复制 `docs/ui_draft.png`，本地批处理只生成目录而没有统一测试/完整 ZIP。设置保存中还保留只遍历一个元素的循环。

建议：三个入口调用同一个构建实现，入口仅传版本/输出位置；删除单元素循环。`Overlay` 的设置页/模型获取和主页面可以分开文件维护，先拆清职责即可，无需引入事件总线或新的框架。

## 55 个测试方法的逐项处置

下表里的“删”针对重复覆盖或只维持冗余实现的用例；“缩”表示保留同一个测试方法，精简断言；所有建议均未实施哦。

| 文件 | 方法 | 处置与原因 |
| --- | --- | --- |
| `test_decisions.py` | `test_question_conversion_preserves_criteria_and_order` | 缩：保留题目转换，随 A14 去掉旧 predicate 分支 |
| 同上 | `test_response_mapping_by_name_and_refusal` | 保留：外部协议按名称映射与拒答 |
| 同上 | `test_invalid_and_missing_answers_fail` | 保留并接收格式错误子用例：统一一张外部响应边界表 |
| 同上 | `test_sdk_http_contract_and_retry` | 缩：保留实际 SDK 的 URL/请求体/认证；去掉对 SDK 自带重试次数的复测 |
| 同上 | `test_http_error_is_redacted` | 保留：已保存/未保存密钥都需在截断前脱敏 |
| 同上 | `test_only_decisions_models_are_offered` | 保留：专用判断来源的模型目录契约 |
| 同上 | `test_engine_uses_converted_judgment_and_ranking` | 保留：分析与排序的主链路，接收重复隔离断言 |
| 同上 | `test_luna_http_contract_and_legacy_model_compatibility` | 保留：真实 SDK 参数差异有实际兼容价值 |
| 同上 | `test_invalid_config_types_use_defaults` | 缩：保留字段类型处理；读取失败与首次默认值按 A05 分开 |
| 同上 | `test_provider_key_isolation_and_no_draft_fallback` | 保留：产品明确的凭据职责 |
| 同上 | `test_save_does_not_copy_official_key_to_draft` | 保留：持久化入口，区别于运行时读取隔离 |
| `test_intent.py` | `test_fractional_scores_and_invalid_values` | 保留：百分比舍入和有效值边界 |
| 同上 | `test_multiple_labels_stay_independent_and_missing_is_unknown` | 保留：独立程度评分的显示语义 |
| 同上 | `test_analysis_never_invokes_drafting` | 删：引擎主链路测试已经检查分析阶段不调用起草 |
| 同上 | `test_analysis_failure_does_not_generate_blind_replies` | 删：分析没有起草调用，异常自然传播，重复验证隔离 |
| 同上 | `test_partial_refusal_is_visible_as_unknown` | 保留：转换后的缺失值与显示语义衔接 |
| 同上 | `test_draft_failure_preserves_analysis` | 删：主调度层已有失败后保留判断结果的用例 |
| 同上 | `test_group_quote_matches_selected_target` | 删：共享目标用例已覆盖所选群成员的目标文本 |
| 同上 | `test_target_outside_context_fails_before_request` | 保留：真实上下文截断边界 |
| 同上 | `test_reply_target_is_shared_by_analysis_drafting_and_ranking` | 保留：三阶段的目标一致性 |
| 同上 | `test_changed_target_waits_for_new_analysis_before_drafting` | 删：随 A08 删除引擎重复过期检查，调度层版本用例继续覆盖 |
| `test_runtime.py` | `test_analysis_starts_without_draft_key` | 保留：主程序启动分析的前置条件 |
| 同上 | `test_new_messages_discard_inflight_draft` | 删：真实 Qt 的新消息/过期起草用例完整覆盖这条路径 |
| 同上 | `test_other_chat_draft_is_cached_without_overwriting_screen` | 保留：后台会话的结果归属 |
| 同上 | `test_draft_error_preserves_judgment` | 保留：失败后的实际调度状态与 UI 路由 |
| 同上 | `test_target_change_invalidates_old_results` | 保留：切换对象后的待处理任务 |
| 同上 | `test_each_chat_keeps_its_own_pending_analysis` | 保留：不同会话的 pending 隔离 |
| 同上 | `test_missing_draft_key_only_affects_draft_region` | 保留：起草前置失败的 UI 位置 |
| 同上 | `test_own_reply_stops_showing_obsolete_analysis_as_loading` | 保留：己方回复后的请求状态 |
| 同上 | `test_repeated_click_does_not_start_duplicate_draft` | 保留并修 fixture：用户配置泄漏已经复现 |
| 同上 | `test_old_analysis_cannot_clear_new_request_busy_state` | 保留：旧任务不得清掉新任务的忙状态 |
| 同上 | `test_exited_capture_process_is_released_for_restart` | 保留：采集进程退出后的生命周期 |
| `test_overlay_runtime.py` | `test_new_message_during_drafting_keeps_only_fresh_analysis` | 保留：使用真实控件检查主链路，代替重复 Mock 用例 |
| 同上 | `test_cached_candidates_cannot_fill_another_chat_and_keep_original_index` | 保留：切换会话和推荐重排后的按钮索引 |
| `test_overlay_settings.py` | `test_score_panels_and_expansion_do_not_generate` | 缩：保留展开无网络副作用和按钮行为，减少对固定标签数量的复刻 |
| 同上 | `test_only_judgment_key_is_needed_to_save` | 合入下方 optional draft 用例，以一个参数表覆盖起草未配置/未填完 |
| 同上 | `test_provider_switch_and_draft_isolation` | 缩：保留来源切换的密钥选择，减少重复默认模型常量断言 |
| 同上 | `test_incomplete_optional_draft_does_not_block_judgment_settings` | 保留并接收上方场景 |
| 同上 | `test_model_fetch_discards_results_after_switching_away_and_back` | 保留：异步请求版本不是静态属性验证 |
| 同上 | `test_model_fetch_error_redacts_unsaved_key` | 保留：后台线程到可见 UI 的脱敏入口 |
| `test_reliability.py` | `test_chat_area_separates_composer_across_dpi_and_window_sizes` | 缩：保留标明输入区位置的合成样例，删去仅复刻 120 px 估算公式的断言 |
| 同上 | `test_voice_hint_filter_keeps_identical_text_inside_a_message_bubble` | 保留：面板提示与真实聊天文字的语义区分 |
| 同上 | `test_capture_detects_title_change_when_messages_are_identical` | 保留：正文相同的会话切换 |
| 同上 | `test_message_alignment_preserves_repetitions_and_sender_changes` | 保留：现有例子有价值，A03 的修复应在这里调整覆盖 |
| 同上 | `test_ocr_ignores_outside_boxes_and_restores_trimmed_coordinates` | 保留：OCR 坐标属于外部边界 |
| 同上 | `test_windows_ocr_respects_size_limit_and_closes_bitmap` | 保留：系统图像上限与资源释放 |
| 同上 | `test_fill_stops_before_input_when_foreground_activation_fails` | 保留：真正执行输入前的系统边界 |
| 同上 | `test_fill_uses_swapped_primary_mouse_button` | 保留：主鼠标键设置和禁止回车的产品约定 |
| 同上 | `test_failed_settings_replace_preserves_original_file` | 缩：保留替换失败后原文件完整；末尾字段类型断言合入配置测试 |
| 同上 | `test_invalid_candidates_and_truncated_output_are_rejected` | 缩：按严格 JSON 契约检查，继续保留输出截断的真实业务分支 |
| 同上 | `test_invalid_decisions_shapes_raise_readable_errors` | 合入 `test_invalid_and_missing_answers_fail`，同一入口同一类错误 |
| `test_llm_compatibility.py` | `test_anthropic_real_sdk_accepts_requests_with_and_without_thinking` | 保留：真实 SDK 的参数签名与请求序列化 |
| 同上 | `test_gemini_retries_explicit_budget_error_and_caches_per_endpoint` | 保留：成功兼容路径与地址隔离 |
| 同上 | `test_gemini_does_not_retry_unrelated_errors` | 保留：错误分流，防止误触发第二次业务请求 |
| 同上 | `test_failed_gemini_retry_does_not_cache_compatibility` | 保留：失败不应污染后续请求状态 |

## 推荐实施顺序

1. 修正 A01—A05：候选正确性、OCR 消息完整性、排序成功语义和配置读失败处理。
2. 整理 A06—A12：配置单次加载、任务状态归属、错误出口和填入时机；直接删除补齐与重复过期检查。
3. 删除 371 行分散自测及 6 个重复方法，完成 2 处用例合并；只在现有用例中调整真正受到修改影响的场景。
4. 清理旧探针、旧题型、翻译键、导入兜底和未使用字段，再统一构建入口及依赖基线。

没有必要为每次删分支新增一层测试来“保护删除”。保留下来的用例检查接口契约、并发状态和用户实际操作，范围就足够清楚啦。

## 近期专用决策模型与本机部署评估

调查时间：2026-10-20。以下选择围绕专用决策模型、LM Studio 和现有 D 盘模型目录展开；本轮仅调查，没有下载权重、升级应用或改动模型服务。

### 推荐：Decision 3.0 的 d3-mini / Q8_0

首选 `vllm-sr/d3-mini`，使用 `ggml-org/vllm-d3-mini-GGUF` 提供的 `vllm-d3-mini-Q8_0.gguf`。这是专门输出选项概率与评分的决策模型，采用 Qwen3.5-4B 底座，完整模型为 4.54B 参数，许可为 Apache-2.0。它适合接下本项目的意图、语气、紧张度和候选排序呢。[模型卡](https://huggingface.co/vllm-sr/d3-mini)

Q8_0 主权重为约 5.16 GB，视觉投影文件另计；本项目继续使用 OCR 后的文字即可。llama.cpp 的原生 D3 支持 PR #30383 已于 2026-10-12 合并，GGUF 使用 `/v1/systemone` 接口。[权重文件](https://huggingface.co/ggml-org/vllm-d3-mini-GGUF/tree/main)、[原生支持 PR](https://github.com/ggml-org/llama.cpp/pull/30383)

### 本机实际配置

| 项目 | 本轮读取结果 |
| --- | --- |
| CPU | AMD Ryzen 7 9700X，8 核 / 16 线程 |
| 内存 | 32 GB 级别，系统报告总物理内存约 31.2 GiB |
| GPU | NVIDIA GeForce RTX 5080，16 GB 级别显存；`nvidia-smi` 报告总计 16,303 MiB，调查时空闲 13,542 MiB |
| 系统 | Windows 11，版本 10.0.26300 |
| D 盘空间 | 调查时约 286 GiB 可用 |
| LM Studio | 用户更新后复查为 `0.4.26`；本地服务器开启，端口 `1234`，没有已加载模型 |
| 选中运行时 | `llama.cpp-win-x86_64-nvidia-cuda12-avx2@2.61.0` |
| 模型目录 | `D:\LM_Studio_models`，与 LM Studio 的 `downloadsFolder` 一致 |
| 全局默认上下文 | 32,768 tokens |

目录中已有 Qwythos 9B Q8_0、Gemma 4 E4B Q4_K_M、DeepSeek R1 Distill Qwen 14B Q4_K_M、Qwen3.8 27B Q4_K_M 和 Qwen3 Embedding 等文件。当前 LM Studio 索引中的模型清单与磁盘文件清单有差别；本轮分别读取了两者。

硬件足以运行 d3-mini Q8_0。推荐先全 GPU 加载，给此模型单独设置 4,096～8,192 tokens 上下文，按当前聊天任务需要调整；无需继承全局 32K 设置。这个内存选择是按模型文件大小与聊天输入规模作出的部署估算，实际显存占用要在加载后读取。

现有 9B Q8 主权重约 9.53 GB，与 d3-mini Q8 主权重合计约 14.69 GB，另有运行缓冲和桌面显存占用。更合适的组合是本地 d3-mini 判断、现有云端来源起草；需要两个模型同时常驻时，再评估 d3-nano 或缩小起草模型的显存占用。

### LM Studio 更新后的接口核对

用户已将应用更新至 `0.4.26`，运行路径为 `D:\Program Files\LM Studio\LM Studio.exe`。复查时先将本地服务恢复到 `127.0.0.1:1234`，使用指定不存在模型、空问题集合的合成请求检查路由，没有加载模型或执行推理。

`/v1/systemone` 返回 HTTP 400，错误为至少需要一道题；`/v1/decisions` 返回 HTTP 400，错误为 questions 应是数组。这两条响应均进入各自接口的参数校验，更新后的应用已经提供决策 API 路由。

官方更新说明列出 `0.4.26 Build 4` 加入这两个接口，与本机观察一致。当前仍选中 CUDA 12 的 `2.61.0` 运行时，后续可直接进入权重加载和实际推理验证。[LM Studio 更新说明](https://lmstudio.ai/changelog/lmstudio)

官方 System One 文档要求指定已加载的决策模型，并提交 `state` 与按题目 ID 组织的 `questions`；支持 `noul`、`choice`、`score`。[接口文档](https://lmstudio.ai/docs/developer/jev-compat/systemone)

建议的模型文件位置为：

```text
D:\LM_Studio_models\ggml-org\vllm-d3-mini-GGUF\vllm-d3-mini-Q8_0.gguf
```

这是后续部署位置建议，本轮没有创建目录或下载文件。

### 候选比较

| 专用模型 | 近期依据与部署文件 | 对当前项目的推荐 |
| --- | --- | --- |
| Decision 3.0 / d3-mini | 10 月上旬模型；原生支持 10 月 12 日合并。Q8_0 主权重约 5.16 GB，Apache-2.0 | 首选，4B 级别在能力和本机资源间更合适 |
| Decision 3.0 / d3-nano | 同系列 2.21B 参数，包含视觉编码器，Apache-2.0；有 ggml-org GGUF | 更适合小显存占用、需要与其他模型常驻的方案 |
| Liquid d1-3B | 10 月 7 日官方发布；官方 Q8_0 主权重约 2.87 GB，LFM Open License；原生支持 PR #30110 已合并 | 第二候选，体积更小，适合低延迟判断 |
| H2O-Lightning-4B | 10 月发布并持续更新；Q8_0 主权重约 4.48 GB，Apache-2.0 | 能力值得对照评估；原生支持 PR #30361 在本轮核对时仍开放，当前 LM Studio 部署路线更曲折，优先级排后 |

来源：[d3-mini GGUF](https://huggingface.co/ggml-org/vllm-d3-mini-GGUF)、[d3-nano](https://huggingface.co/vllm-sr/d3-nano)、[Liquid 发布说明](https://www.liquid.ai/blog/d1-open)、[d1 文件列表](https://huggingface.co/LiquidAI/d1-3B-GGUF/tree/main)、[d1 原生支持](https://github.com/ggml-org/llama.cpp/pull/30110)、[H2O GGUF](https://huggingface.co/h2oai/h2o-lightning-4b-gguf)、[H2O 原生支持状态](https://github.com/ggml-org/llama.cpp/pull/30361)。

模型仓库创建时间与正式发布时间分开记录：Hugging Face API 显示 d3-mini/d3-nano 仓库于北京时间 2026-10-11 创建，d3-mini GGUF 仓库于 10 月 12 日创建。模型参数名中的 3B / 4B 是产品规格名称，表内文件大小采用发布页的十进制 GB。

### 能力判断与项目适配

Decision 3.0 的同版 Jev Decision Index 0.3.2 文本榜中，d3-mini 为 52.6，d3-nano 为 38.9；mini 在公开套件为 54.9。这些是模型卡记录的榜单/测评指数，用于比较同口径任务；本项目需要进一步关注中文短句、群聊指代和五级评分。[mini 测评](https://huggingface.co/vllm-sr/d3-mini)、[nano 测评](https://huggingface.co/vllm-sr/d3-nano)

Liquid d1-3B 官方报告的是另一版 Decision Index 0.2.1，指数为 48.57；官方 RTX 4090 单题热启动延迟为 8 ms。它与上面的 0.3.2 指数分别记录，硬件延迟也保留原测试条件。[Liquid 官方结果](https://www.liquid.ai/blog/d1-open)

对本项目，专用模型的优势是直接返回 5 个等级的分布、加权分数和候选选择，减少生成长文本再解析的路径。18 项意图与 10 项语气仍然独立评分，不能改成一个互斥的 28 类选择题；紧张度继续单独使用 10 个有序等级。候选排序再提交一道 2～3 选项的 choice 题即可。

一次分析共 29 道题。单题的公开毫秒数据与整次聊天分析分别计时；评估时记录从提交 29 题到拿齐结果的完整耗时。中文基础来自 Qwen 底座，这让 d3-mini 更值得作为当前项目的第一候选；中文聊天的具体分数和排序质量应直接用当前题目比较。

Laya 是已有开源路线，仓库也保留了旧探针。其多语言模型卡明确记录 ordinal score 较弱，SST-5 为 0.282，并存在等级位置偏差；本项目的主要工作恰好是 29 道评分题，所以这次排在 D3 和 d1 后面。[Laya 多语言模型卡](https://huggingface.co/convaiinnovations/laya-multilingual)

10 月 9 日发布的 Microsoft-Decision-1 也属于专用决策模型，官方提供 Microsoft Foundry / OpenRouter 服务；本轮本机部署清单采用上面已有可下载权重的模型。[微软发布说明](https://commandline.microsoft.com/microsoft-decision-1-model-foundry/)

本轮完成的是资料核对、硬件读取与部署路径评估，没有加载新权重执行中文能力测评。推荐后续只用一组小型、带人工判断的中文场景对照 mini、d1 和现有判断服务，重点包括“普通催促/问责”“玩笑/讽刺”“简短消息/冷淡”、群聊对象及引用转述；把这组材料作为模型选型评估保留，业务单元测试继续专注代码行为哦。

### 接入本项目需要修改的位置

当前判断来源只有 OpenAI、OpenRouter、TypeSafe；自定义 Base URL 仅存在于回复起草设置。源码根目录没有 `config.json`，因此这里按源码配置能力评估，没有套用其他安装目录的用户设置。

推荐增加一个明确的“LM Studio 本地决策”判断来源，配置模型 ID 和本地地址，走 `http://127.0.0.1:1234/v1/systemone`。沿用现有题目与结果字典，保留现有云端来源。该来源按本地服务的认证设置处理令牌；当前强制“有云端判断密钥才能分析/保存”的前置条件需要一起改。

这条路线只替换判断与排序的请求目的地。OCR、群聊目标选择和起草服务职责继续沿用当前设计；新增来源可以直接修改从上游继承的路由和设置实现，无需为了保留旧结构额外包一层兼容壳。

## 2026-10-20 授权实施后的落实记录

本节记录用户批准精简、修复和本地模型部署后的结果；前面的审查结论保留为实施前快照。

### 代码和测试

- 候选解析只接受完整 JSON 字符串数组，可带一层 JSON 围栏；清理首尾空白并按原文去重，保留句号、引号和语气符号。删除逐行抢救、关键词注入过滤、复读黑名单、自动补齐请求和 `_parse_three`。
- 分析、起草和排序共享一次构建的聊天状态。主调度层负责会话版本校验，删除 `_messages`、`_options`、`_rev` 等重复状态以及引擎内再次构建上下文的路径。
- 排序失败和单条候选使用 `best_index=None`。失败保留平级候选与“候选已生成，排序未完成，请自行选择。”提示。浏览历史会话时允许复制，填入仍受当前会话约束。
- OCR 对齐仅跳过匹配的已知前缀，修复历史 `[A,B]` 与当前 `[A,C]` 重叠时漏掉新消息 C。保留重复消息、群聊发言人和 OCR 抖动的连续匹配。
- 删除 Windows OCR 初始化失败的永久标记；初始化和采集故障显示实际原因并停止，不再每 50 ms 重复抛错。填入前重新采集会话标题和输入区，防止同一窗口切换会话后使用旧缓存。
- 配置改为启动时的内存快照，文件不存在时使用默认设置；文件损坏和读取失败明确报错。原子替换成功后再更新内存配置，测试通过临时目录隔离真实配置。
- 云端判断与起草的自动网络重试关闭，保留 Gemini 明确拒绝关闭思考时的一次参数兼容请求。OpenAI 使用固定版本 SDK 的 Decisions 资源。
- 删除 8 个业务模块的内联自测、11 个旧探针文件及直接运行模块的导入兼容路径。主界面拆分为 `overlay.py`、`settings_panel.py` 和 `widgets.py`，清理废弃翻译和私有截图路径。
- 固定当前通过验证的依赖和 Python 3.12 构建环境；本地批处理与 GitHub 工作流统一调用 `tools/build_release.ps1`，SDK 仅收集所需模块，保留 OCR 数据、证书、SOCKS 和 Windows DLL 处理。

业务运行代码共从 4,951 行减至 4,266 行，净减 685 行，包含拆分后的两个新增界面模块。测试从 55 项调整为 52 项：删除 6 项重复方法、合并 2 项重叠方法，增加 5 项本地接口和配置行为验证。测试源码增加 92 行，新增内容用于真实 HTTP/SDK 契约和故障场景。

验证结果：52 项自动化测试通过；Ruff 的 F821 / F401 检查通过；Windows onedir 构建成功，打包程序的合成界面预览运行成功。补充验证了 Windows 中文 OCR 初始化、韩文单词分段坐标、会话变更时停止填入，以及真实设置页获取本地模型并完成 29 题分析。

### 文案落实

| 原状态或文字 | 当前行为与文字 |
| --- | --- |
| 排序失败仍突出第一条“推荐回复” | 所有候选平级显示“候选 1 / 2 / 3”，说明“排序未完成” |
| 所有分析来源统一要求密钥 | 本地来源显示“认证令牌（可选）”和“令牌可选” |
| 分析密钥说明同时罗列所有来源 | 按当前来源显示简短提示；本地为“连接本地服务；未启用认证时，令牌可留空。” |
| 候选保留方式修改原有标点 | 显示起草服务返回的原文标点，仅清理首尾空白 |

### D3-mini Q8_0 部署

- 权重目录：`D:/LM_Studio_models/ggml-org/vllm-d3-mini-GGUF/`。
- 主权重：`vllm-d3-mini-Q8_0.gguf`，5,157,835,232 字节，SHA-256 `f9f99be46b7ce1e5a5f09ed620de89106447646b34f7d2993e7563b48feb2858`。
- 视觉投影：`mmproj-vllm-d3-mini-BF16.gguf`，675,569,280 字节，SHA-256 `56c2ef9f10da54543b4670a1a466befc723b58da408322dd32fb42450d4170da`。
- 两个文件均核对 Hugging Face LFS 摘要及 GGUF 文件头。仓库版本为 `e7230e2309c186c80182fbeed6fef70680b20c64`。
- LM Studio 0.4.26，CUDA 12 运行时 2.61.0，RTX 5080 全 GPU 加载；服务为 `127.0.0.1:1234`，加载标识为 `d3-mini`。
- 上下文、Evaluation Batch Size、Physical Batch Size 均为 8192，Flash Attention 和 GPU KV 缓存开启。默认物理批大小 512 触发了非因果注意力断言；调整后完整 29 题请求成功。
- 已保存该模型专属默认参数，并完成卸载、CLI 重载和配置回读；模板位于 `tools/lmstudio-d3-mini.defaults.json`。首次加载 4.33 秒，配置保存后的重载 3.16 秒；CLI 报告模型占用 5.43 GiB。推理后设备总显存约 9.1 GiB，剩余约 6.5 GiB，数值包含桌面和其他应用。
- 本工作目录的忽略配置已选择 LM Studio / `d3-mini`。模型权重、个人配置和凭据不进入本次 Git 提交。

### 中文实测与选型结论

场景全部为合成聊天。预先固定高标签至少 2.5/4、低标签最多 1.5/4；每轮分析使用全部 29 道题，排序单独提交一道三选一。原组 12 个场景重复两轮，另用 8 个新增场景验证调整后的评分范围。

| 评估 | 标签判定 | 候选排序 | 完整分析中位数 / P95 | 排序中位数 / P95 |
| --- | --- | --- | --- | --- |
| 原评分说明，12 场景 × 2 | 78/88 | 24/24 | 1,182 / 1,226 ms | 207 / 228 ms |
| 明确唯一目标消息后，12 场景 × 2 | 86/88 | 24/24 | 1,133 / 1,197 ms | 210 / 223 ms |
| 新增 8 场景，1 轮 | 26/27 | 8/8 | 1,114 / 1,156 ms | 205 / 212 ms |

中位数与 P95 的分析统计排除每组首个请求。每组首次完整分析分别为 1,238 / 1,316 / 1,443 ms，均在模型已加载后测量。两轮重复用于观察输出和耗时，场景数仍为 12。

原说明在指定小李时混入了小王的愤怒与问责。将题目改为“chat.reply_target 是唯一评分对象；其他人的情绪、意图不计入目标消息”后，小李的信息询问从 2.34 升至约 2.99，愤怒从 1.68 降至约 0.07；新增家庭群和道歉场景也通过。

仍存在的能力短板是含蓄不满：反话中的不满评分约 2.44，低于预设的 2.5；“没事，你忙你的吧。我已经等了两个小时了。”的不满为 1.88。反话本身能识别，回复排序也能选出承认等待与迟到的候选，情绪强度给得偏温和。

推荐在本机使用 d3-mini Q8_0 承担日常意图、语气评分及候选排序，按需调用现有云端起草服务。20 个合成场景覆盖常规事务、问责、群聊、引用、混合语言和情感表达；情绪程度由用户结合原话判断。

原始结果保存在 `docs/evaluations/2026-10-20-d3-mini-q8_0.json`、`2026-10-20-d3-mini-q8_0-target-scope.json`、`2026-10-20-d3-mini-q8_0-holdout.json`。复测工具为 `tools/evaluate_decisions.py`，场景和阈值随代码进入 Git。
