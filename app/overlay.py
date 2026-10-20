# -*- coding: utf-8 -*-
"""浅色置顶回复助手：回复建议和独立设置页。发送始终由用户确认。"""
from datetime import datetime
from math import isfinite
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QSizeGrip, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, FluentIcon as FIF, HyperlinkButton, IndeterminateProgressBar, PlainTextEdit, PrimaryPushButton, PushButton, ScrollArea, SwitchButton, Theme, TransparentToolButton, setCustomStyleSheet, setTheme, setThemeColor
from app import i18n, settings
from app.version import VERSION
from core import jev_client
from core.intent import ratings
from app.i18n import T, bind
from app.widgets import _MUTED, _GREEN, _FitCombo, _label, _tlabel, _tool, _Surface, _TitleBar, _MainWindow, _ReplyCard, _RatingsPanel
from app.settings_panel import SettingsPanel

_LOG_LINES = 300
class Overlay(SettingsPanel):
    def __init__(self, on_fill, on_toggle_capture=None, on_target_change=None, result_of=None,
                 on_toggle_debug=None, on_language_changed=None, on_generate=None,
                 on_analysis_settings_changed=None):
        """result_of(会话名) → 那个会话上次的结果或 None；切着看别的会话时用它把旧结果放回来。
        on_target_change(会话名, 人名) → 用户在群里挑了回复对象。
        on_toggle_debug(开不开) → 开关调试视图那个独立窗口。"""
        self.app = QApplication.instance() or QApplication([])
        i18n.reload()
        setTheme(Theme.LIGHT)
        setThemeColor(_GREEN, save=False)
        self.on_fill = on_fill
        self.on_toggle_capture = on_toggle_capture
        self.on_target_change = on_target_change
        self.on_toggle_debug = on_toggle_debug
        self.on_language_changed = on_language_changed
        self.on_generate = on_generate
        self.on_analysis_settings_changed = on_analysis_settings_changed
        self.result_of = result_of
        self.cands = []
        self.cards = []
        self._busy = False
        self._current = False
        self._result = None
        self._draft_busy = False
        self._compact = None  # 断点模式：None 保证 _relayout 第一次调用必定生效
        self._pageLayouts = []
        self._hintLabels = []
        self.feeds = {}  # {会话名: [(who, name, text, timestamp)]}，换语言只重画说话人标签
        self._feed_entries = []
        self.counts = {}  # {会话名: 消息条数}
        self.hers = {}  # {会话名: 对方最近一句}
        self.targets = {}  # {会话名: ([发言人], 当前回复对象)}
        self._chat = ""  # 微信当前开着的会话
        self._shown = ""  # 界面上正在看的会话（浏览时和上面不一样）
        self.win = _MainWindow(self._relayout)
        self.win.setObjectName("assistantWindow")
        self.win.setWindowTitle("JevChat-Windows")
        self.win.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.win.setStyleSheet(
            "QWidget#assistantWindow { background: #f5f7f6; border: 1px solid #dce3de; border-radius: 14px; }"
        )
        self.win.setMinimumWidth(320)
        self.win.setMaximumWidth(640)
        outer = QVBoxLayout(self.win)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        header = _TitleBar(self.win)
        title = QHBoxLayout(header)
        title.setContentsMargins(18, 12, 10, 10)
        title.setSpacing(8)
        name = _label("Jev", 20, "#233c2f", True)
        name.setFixedWidth(40)
        name.setAttribute(Qt.WA_TransparentForMouseEvents)
        title.addWidget(name)
        self.subtitle = _label("JevChat-Windows", 12, _MUTED)
        self.subtitle.setAttribute(Qt.WA_TransparentForMouseEvents)
        title.addWidget(self.subtitle, 1)
        self.captureSwitch = SwitchButton(header)
        bind(self.captureSwitch, "采集中", "setOnText")
        bind(self.captureSwitch, "已暂停", "setOffText")
        bind(self.captureSwitch, "开启或暂停采集", "setToolTip")
        bind(self.captureSwitch, "开启或暂停采集", "setAccessibleName")
        self.captureSwitch.setChecked(True)
        self.captureSwitch.checkedChanged.connect(self._capture_toggled)
        title.addWidget(self.captureSwitch)
        self.settingsButton = _tool(FIF.SETTING, "设置", self.open_settings, header)
        title.addWidget(self.settingsButton)
        title.addWidget(_tool(FIF.REMOVE, "最小化", self.win.showMinimized, header))
        title.addWidget(_tool(FIF.CLOSE, "关闭助手", self.win.close, header))
        outer.addWidget(header)
        self.updateBar = QWidget(self.win)
        update_row = QHBoxLayout(self.updateBar)
        update_row.setContentsMargins(18, 4, 8, 4)
        update_row.setSpacing(8)
        self.updateLabel = _label("", 12, _GREEN, True)
        update_row.addWidget(self.updateLabel, 1)
        self.updateLink = bind(HyperlinkButton("", "", self.updateBar), "查看更新")
        self.updateLink.setFixedHeight(24)
        update_row.addWidget(self.updateLink)
        closeUpdate = TransparentToolButton(FIF.CLOSE, self.updateBar)
        closeUpdate.setFixedSize(20, 20)
        bind(closeUpdate, "关闭更新提示", "setToolTip")
        bind(closeUpdate, "关闭更新提示", "setAccessibleName")
        closeUpdate.clicked.connect(lambda: self.updateBar.hide())
        update_row.addWidget(closeUpdate)
        self.updateBar.setFixedHeight(32)
        self.updateBar.hide()
        outer.addWidget(self.updateBar)
        self.pages = QStackedWidget(self.win)
        outer.addWidget(self.pages, 1)
        self._build_home()
        self._build_settings()
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 9, 8, 8)
        footer.addWidget(_tlabel(lambda: f"{T('仅填入输入框 · 请手动发送')} · v{VERSION}", 11, _MUTED), 1)
        grip = QSizeGrip(self.win)
        grip.setFixedSize(16, 16)
        footer.addWidget(grip, 0, Qt.AlignBottom)
        outer.addLayout(footer)
        screen = self.app.primaryScreen().availableGeometry()
        self.win.setMinimumHeight(min(360, screen.height() - 32))
        self.win.resize(min(440, screen.width() - 32), min(820, screen.height() - 48))
        self.win.move(screen.right() - self.win.width() - 20, screen.top() + 24)
        self._relayout(self.win.width(), self.win.height())  # resizeEvent 补不到构造时这一次
        self.set_status("等待新消息" if settings.analysis_ready() else "需要配置模型",
                        "idle" if settings.analysis_ready() else "warning")
        self.win.show()

    def _scroll_page(self):
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("pageContent")
        content.setStyleSheet("QWidget#pageContent { background: transparent; }")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 8, 20, 12)
        layout.setSpacing(14)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        self._pageLayouts.append(layout)
        return scroll, layout

    def _relayout(self, w, h):
        """宽度跨过断点才重新摆布局（省事）；高度每次都重算，反正只是设个定高。"""
        compact = w < 400
        if compact != self._compact:
            self._compact = compact
            self._apply_compact(compact)
        self.feed.setFixedHeight(max(100, min(240, int(h * 0.25))))

    def _apply_compact(self, compact):
        """紧凑/常规两套间距和可见性；断点没变时不会被调用。"""
        self.subtitle.setVisible(not compact)
        bind(self.captureSwitch, lambda: "" if self._compact else T("采集中"), "setOnText")
        bind(self.captureSwitch, lambda: "" if self._compact else T("已暂停"), "setOffText")
        for label in self._hintLabels:
            label.setVisible(not compact)
        self.referenceNote.setVisible(bool(self.cands) and not compact)
        self._sync_model_fields()
        margins = (12, 8, 12, 12) if compact else (20, 8, 20, 12)
        for layout in self._pageLayouts:
            layout.setContentsMargins(*margins)
        for card in self.cards:
            card.set_compact(compact)

    def _build_home(self):
        self.home, body = self._scroll_page()
        heading = QHBoxLayout()
        heading.addWidget(_tlabel("意图与语气", 23, "#24382d", True), 1)
        self.updated = _label("", 11, _MUTED)
        self.updated.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        heading.addWidget(self.updated)
        body.addLayout(heading)
        chat_row = QHBoxLayout()
        chat_row.setSpacing(8)
        prefix = _tlabel("当前会话", 12, _MUTED)
        prefix.setFixedWidth(56)
        chat_row.addWidget(prefix)
        self.chatBox = _FitCombo()
        bind(self.chatBox, "尚未识别到会话", "setPlaceholderText")
        bind(self.chatBox, "当前会话", "setAccessibleName")
        bind(self.chatBox, "跟随聊天窗口中的当前会话，也可以切换查看其他会话的记录和分析。", "setToolTip")
        self.chatBox.currentIndexChanged.connect(self._on_chat_selected)
        chat_row.addWidget(self.chatBox, 1)
        self.chatFollow = _label("", 11, _MUTED)
        self.chatFollow.setFixedWidth(52)
        self.chatFollow.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        chat_row.addWidget(self.chatFollow)
        body.addLayout(chat_row)
        self.targetRow = QWidget()  # 只有开了「群聊指定回复对象」且这个会话是群聊才露出来
        target_row = QHBoxLayout(self.targetRow)
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(8)
        target_prefix = _tlabel("回复对象", 12, _MUTED)
        target_prefix.setFixedWidth(56)
        target_row.addWidget(target_prefix)
        self.targetBox = _FitCombo()
        bind(self.targetBox, "回复对象", "setAccessibleName")
        bind(self.targetBox, "选择要分析和回复的人，默认跟随最近发言的人。", "setToolTip")
        self.targetBox.currentIndexChanged.connect(self._on_target_selected)
        target_row.addWidget(self.targetBox, 1)
        self.atCheck = bind(CheckBox(""), "添加 @姓名")
        self.atCheck.setChecked(True)
        bind(self.atCheck, "在回复开头加上“@姓名 ”，作为普通文字填入。", "setToolTip")
        target_row.addWidget(self.atCheck)
        self.targetRow.hide()
        body.addWidget(self.targetRow)
        self.status = _label("", 12, _MUTED)
        body.addWidget(self.status)
        self.progress = IndeterminateProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.hide()
        body.addWidget(self.progress)
        self.context = QWidget()
        context_box = QVBoxLayout(self.context)
        context_box.setContentsMargins(0, 0, 0, 0)
        context_box.setSpacing(5)
        context_box.addWidget(_tlabel("对方最新消息", 11, _MUTED))
        self.latest = _label("", 14, "#42574a")
        self.latest.setTextInteractionFlags(Qt.TextSelectableByMouse)
        context_box.addWidget(self.latest)
        self.context.hide()
        body.addWidget(self.context)

        self.insight = _Surface()
        insight_box = QVBoxLayout(self.insight)
        insight_box.setContentsMargins(14, 12, 14, 12)
        insight_box.setSpacing(7)
        row = QHBoxLayout()
        self.insightTitle = _tlabel("分析摘要", 12, _MUTED)
        row.addWidget(self.insightTitle, 1)
        self.tension = _label("", 11)
        self.tension.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.tension)
        insight_box.addLayout(row)
        self.summary = _label("", 14, "#304c3c", True)
        insight_box.addWidget(self.summary)
        self.intent = _label("", 12, _MUTED)
        insight_box.addWidget(self.intent)
        bind(self.intent, "各项独立评分，百分比表示对应意图或语气的体现程度。")
        self.insight.hide()
        body.addWidget(self.insight)
        self.intentPanel = _RatingsPanel("意图", "intent", _GREEN)
        self.tonePanel = _RatingsPanel("语气", "tone", "#b67b25")
        self.intentPanel.hide()
        self.tonePanel.hide()
        body.addWidget(self.intentPanel)
        body.addWidget(self.tonePanel)

        self.empty = _Surface()
        empty_box = QVBoxLayout(self.empty)
        empty_box.setContentsMargins(24, 36, 24, 36)
        empty_box.setSpacing(14)
        symbol = _label("…", 30, _GREEN, True)
        symbol.setAlignment(Qt.AlignCenter)
        empty_box.addWidget(symbol)
        self.emptyTitle = _tlabel("等待对方的新消息", 17, "#304c3c", True)
        self.emptyTitle.setAlignment(Qt.AlignCenter)
        empty_box.addWidget(self.emptyTitle)
        self.emptyHint = _tlabel("保持聊天窗口打开，\n收到新消息后会自动分析意图与语气。", 13, _MUTED)
        self.emptyHint.setAlignment(Qt.AlignCenter)
        empty_box.addWidget(self.emptyHint)
        self.setupButton = bind(PrimaryPushButton(""), "前往设置")
        self.setupButton.clicked.connect(self.open_settings)
        self.setupButton.setVisible(not settings.analysis_ready())
        empty_box.addWidget(self.setupButton, 0, Qt.AlignHCenter)
        if not settings.analysis_ready():
            bind(self.emptyTitle, "先设置一下", "setText")
            bind(self.emptyHint, "设置关系背景和分析模型，就可以开始。\n需要回复建议时，再配置回复模型。", "setText")
        body.addWidget(self.empty)
        self.draftToggle = bind(PushButton(""), "展开回复起草")
        self.draftToggle.clicked.connect(self._toggle_draft)
        body.addWidget(self.draftToggle)
        self.draftContent = QWidget()
        draft_box = QVBoxLayout(self.draftContent)
        draft_box.setContentsMargins(0, 0, 0, 0)
        self.generateButton = bind(PrimaryPushButton(""), "生成回复")
        self.generateButton.clicked.connect(self._generate)
        draft_box.addWidget(self.generateButton)
        self.draftFeedback = _tlabel("点击“生成回复”，挑一句合适的再调整。", 12, _MUTED)
        draft_box.addWidget(self.draftFeedback)
        self.replyBox = QVBoxLayout()
        self.replyBox.setSpacing(10)
        draft_box.addLayout(self.replyBox)
        self.referenceNote = _tlabel("发送前看一遍，按你的习惯调整措辞。", 11, _MUTED)
        self.referenceNote.hide()
        draft_box.addWidget(self.referenceNote)
        self.draftContent.hide()
        self.generateButton.setEnabled(False)
        body.addWidget(self.draftContent)

        self.historyButton = bind(PushButton(FIF.HISTORY, ""), "聊天记录")
        self.historyButton.clicked.connect(self._toggle_history)
        bind(self.historyButton, "展开或收起聊天记录", "setAccessibleName")
        body.addWidget(self.historyButton)
        self.feed = PlainTextEdit()
        self.feed.setReadOnly(True)
        bind(self.feed, "识别到的聊天内容会显示在这里", "setPlaceholderText")
        self.feed.setMaximumBlockCount(_LOG_LINES)
        self.feed.setFixedHeight(160)
        self.feed.hide()
        body.addWidget(self.feed)
        self._history_title()
        body.addStretch(1)

    def _fill(self, index):
        if self._busy or not self._current or not 0 <= index < len(self.cands):
            return
        try:
            self.on_fill(self.cands[index])
        except Exception as e:
            # 状态栏保持友好文案；真实原因和压缩堆栈进聊天记录，认得出是哪一步炸的
            import traceback
            self.set_status("未能填入，请确认聊天窗口可用后重试，或复制回复。", "error")
            self.log(f"[填入失败] {type(e).__name__}: {e}")
            self.log(f"[填入失败堆栈] {' '.join(traceback.format_exc().split())[:300]}")
            return
        self.set_status("回复已填入，确认内容后手动发送。", "success")

    def _copy(self, index):
        if not 0 <= index < len(self.cands):
            return
        self.app.clipboard().setText(self.cands[index])
        self.set_status("回复已复制到剪贴板。", "success")

    def _capture_toggled(self, on):
        """用户自己拨的开关：界面先改，再通知父进程去开/停采集。"""
        self._capture_text(on)
        if self.on_toggle_capture:
            self.on_toggle_capture(on)

    def set_update(self, latest, url):
        """main.py 后台线程查到比当前新的版本才会调这个。只显示版本号和 Release 链接，别的什么都没有。"""
        bind(self.updateLabel, lambda: T("有新版本 v{version}").format(version=latest))
        self.updateLink.setUrl(url)
        self.updateBar.show()

    def set_capture(self, on, reason=""):
        """父进程回报的状态：只改界面，不回调（不然和父进程来回打架）。reason 为空用默认说明。"""
        self.captureSwitch.blockSignals(True)
        self.captureSwitch.setChecked(on)
        self.captureSwitch.blockSignals(False)
        self._capture_text(on, reason)

    def _capture_text(self, on, reason=""):
        """开关状态对应的状态行和空态文案。已有的候选不受影响，暂停了照样能填入/复制。"""
        configured = settings.analysis_ready()
        if not on:
            self.set_status(reason or "采集已暂停。", "warning")
        elif configured:
            self.set_status("等待新消息", "idle")
        else:
            self.set_status("请先配置分析模型及 API 密钥。", "warning")
        if self._busy or self._result:
            return
        if not on:
            bind(self.emptyTitle, "采集已暂停", "setText")
            bind(self.emptyHint, "开启顶部采集开关，继续读取聊天消息。", "setText")
            self.setupButton.setVisible(not configured)
        else:
            self._empty_text()

    def set_busy(self, busy):
        self._busy = busy
        self.progress.setVisible(busy)
        if busy:
            self.invalidate_replies()
            self.progress.start()
            self.set_status("正在分析意图与语气…", "busy")
            if not self._result:
                bind(self.emptyTitle, "正在分析最新消息", "setText")
                bind(self.emptyHint, "正在参考前面的聊天，分析对方的意图与语气。", "setText")
                self.setupButton.hide()
        else:
            self.progress.stop()
            if not self._result:
                self._empty_text()
        for card in self.cards:
            card.set_available(self._current and not busy)
        self.generateButton.setEnabled(self._current and not busy and not self._draft_busy)

    def _empty_text(self):
        """空态卡片的默认文案，配好没配好两套说法。"""
        configured = settings.analysis_ready()
        bind(self.emptyTitle, "等待对方的新消息" if configured else "先设置一下")
        bind(self.emptyHint, "保持聊天窗口打开，\n收到新消息后会自动分析意图与语气。"
                            if configured else "设置关系背景和分析模型，就可以开始。\n需要回复建议时，再配置回复模型。")
        self.setupButton.setVisible(not configured)

    def invalidate_replies(self):
        self._current = False
        self._draft_busy = False
        self.cands = []
        self._clear_cards()
        self.referenceNote.hide()
        self.generateButton.setEnabled(False)
        bind(self.generateButton, "生成回复")
        if self._result:
            bind(self.updated, "上次分析", "setText")
        bind(self.draftFeedback, "等待最新分析完成后，可生成回复。")

    def _toggle_draft(self):
        opened = self.draftContent.isHidden()
        self.draftContent.setVisible(opened)
        bind(self.draftToggle, "收起回复起草" if opened else "展开回复起草")

    def _generate(self):
        if self.on_generate and self._current and not self._busy and not self._draft_busy:
            self.on_generate(self._shown)

    def set_draft_busy(self, busy, error=""):
        self._draft_busy = busy
        self.generateButton.setEnabled(self._current and not self._busy and not busy)
        bind(self.generateButton, "正在生成…" if busy else "生成回复")
        notice = (self._result or {}).get("draft_notice", "") if not busy else ""
        bind(self.draftFeedback, error or ("正在生成候选并排序…" if busy else notice or
             "点击“生成回复”，挑一句合适的再调整。"))
        color = "#b44832" if error else (_GREEN if busy else "#996819" if notice else _MUTED)
        qss = f"BodyLabel {{ color: {color}; background: transparent; }}"
        setCustomStyleSheet(self.draftFeedback, qss, qss)
        if busy:
            self.cands = []
            self._clear_cards()
        for card in self.cards:
            card.set_available(self._current and not busy and not self._busy)

    def set_status(self, text, kind="idle"):
        colors = {"idle": _MUTED, "busy": _GREEN, "success": _GREEN,
                  "warning": "#93611d", "error": "#b44832"}
        markers = {"idle": "●", "busy": "●", "success": "✓", "warning": "!", "error": "!"}
        qss = f"BodyLabel {{ color: {colors.get(kind, _MUTED)}; background: transparent; }}"
        setCustomStyleSheet(self.status, qss, qss)
        bind(self.status, lambda: f"{markers.get(kind, '●')}  {text() if callable(text) else T(text)}")
        if kind == "error" and self._busy:
            self.set_busy(False)
        if kind == "error" and not self._result:
            bind(self.emptyTitle, "分析未完成", "setText")
            bind(self.emptyHint, "请按上方提示处理。收到新的对方消息后会再次尝试。", "setText")
            self.setupButton.setVisible(not settings.analysis_ready())

    def _toggle_history(self):
        self.feed.setVisible(self.feed.isHidden())
        self._history_title()

    def _history_title(self):
        action = "展开聊天记录" if self.feed.isHidden() else "收起聊天记录"
        count = self.counts.get(self._shown, 0)
        bind(self.historyButton, lambda: T(action) + (f" · {count}" if count else ""))

    @staticmethod
    def _log_text(entry):
        if isinstance(entry, str):  # 诊断信息保持原文
            return entry
        who, name, text, timestamp = entry
        speaker = (name or T("对方")) if who == "her" else T("我")
        return f"{timestamp}  {speaker}\n{text}\n"

    def _refresh_history_text(self):
        bar = self.feed.verticalScrollBar()
        position = bar.value()
        follow = position >= bar.maximum() - 4
        self.feed.setPlainText("\n".join(self._log_text(entry) for entry in self._feed_entries))
        bar.setValue(bar.maximum() if follow else position)

    def log(self, line, chat=None):
        """诊断信息按会话保留，显示时先执行密钥脱敏。"""
        chat = chat or self._shown
        if isinstance(line, str):
            entries = self.feeds.setdefault(chat, [])
            entries.append(jev_client.redact_secrets(line))
            del entries[:-_LOG_LINES]
            line = entries[-1]
        if chat != self._shown:
            return
        bar = self.feed.verticalScrollBar()
        follow = self.feed.isHidden() or bar.value() >= bar.maximum() - 4
        self._feed_entries.append(line)
        del self._feed_entries[:-_LOG_LINES]
        self.feed.appendPlainText(self._log_text(line))
        if follow:
            bar.setValue(bar.maximum())

    def log_message(self, who, text, name="", timestamp=None, chat=None):
        """按会话存一份；只有正在看的那个会往显示区里写。"""
        chat = chat or self._shown
        timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.counts[chat] = self.counts.get(chat, 0) + 1
        lines = self.feeds.setdefault(chat, [])
        lines.append((who, name, text, timestamp))
        del lines[:-_LOG_LINES]
        if who == "her":
            self.hers[chat] = text
        self._add_chat(chat)
        if chat != self._shown:
            return
        self.log(lines[-1])
        if who == "her":
            self._show_latest(text)
        self._history_title()

    def _show_latest(self, text):
        self.latest.setText(text if len(text) <= 120 else text[:120] + "…")
        self.latest.setToolTip(text)
        self.context.show()

    def current_chat(self):
        """界面上正在看的会话（不一定是微信当前开着的那个）。"""
        return self._shown

    def set_chat(self, title):
        """微信切到了哪个会话：登记进下拉框并自动跟过去，不触发用户选择的回调。"""
        if not title:
            return
        browsing = self._shown != self._chat  # 正看着的就是它、但之前是「浏览中」：也得重画，把填入放开
        self._chat = title
        self._add_chat(title)
        if title != self._shown or browsing:
            self.chatBox.blockSignals(True)
            self.chatBox.setCurrentIndex(self.chatBox.findText(title))
            self.chatBox.blockSignals(False)
            self._switch_to(title)
        self._follow_text()

    def _add_chat(self, title):
        """新会话自动进下拉框；addItem 添第一条时会自己选中，别让它触发切换。"""
        if not title or self.chatBox.findText(title) >= 0:
            return
        self.chatBox.blockSignals(True)
        self.chatBox.addItem(title)
        self.chatBox.blockSignals(False)

    def _on_chat_selected(self, index):
        """用户自己挑了一个会话：只换看的内容，微信那边不动。"""
        title = self.chatBox.itemText(index)
        if title and title != self._shown:
            self._switch_to(title)

    def _switch_to(self, title):
        """切换显示会话的记录、消息和结果，起草区域恢复折叠。"""
        self.draftContent.hide()
        bind(self.draftToggle, "展开回复起草")
        self._shown = title
        self._feed_entries = list(self.feeds.get(title, []))
        self._refresh_history_text()
        self.feed.verticalScrollBar().setValue(self.feed.verticalScrollBar().maximum())
        her = self.hers.get(title)
        if her:
            self._show_latest(her)
        else:
            self.context.hide()
        self._history_title()
        self._follow_text()
        self._render_targets()
        self.show_cached(self.result_of(title) if self.result_of else None)

    def set_targets(self, chat, senders, current):
        """某个会话的发言人名单（最近的在前）和当前回复对象；正看着它才重画。"""
        self.targets[chat] = (list(senders), current)
        if chat == self._shown:
            self._render_targets()

    def _render_targets(self):
        """开关关着、或这个会话没有发言人（单聊），这一行就不出现。
        重填下拉框时屏蔽信号，别把自己的填充当成用户挑的。"""
        senders, current = self.targets.get(self._shown, ([], None))
        visible = bool(senders) and settings.reply_target()
        self.targetRow.setVisible(visible)
        if not visible:
            return
        self.targetBox.blockSignals(True)
        self.targetBox.clear()
        self.targetBox.addItems(senders)
        self.targetBox.setCurrentIndex(senders.index(current) if current in senders else 0)
        self.targetBox.blockSignals(False)

    def _on_target_selected(self, index):
        """用户挑了回复对象。浏览别的会话时改的就是那个会话的对象——记录、候选也都按会话走，口径一致。"""
        name = self.targetBox.itemText(index)
        if not name:
            return
        senders, _ = self.targets.get(self._shown, ([], None))
        self.targets[self._shown] = (senders, name)
        self.set_status(lambda: T("正在分析“{name}”的发言…").format(name=name), "busy")
        if self.on_target_change:
            self.on_target_change(self._shown, name)

    def at_prefix_enabled(self):
        """填入时要不要带「@名字 」前缀（只记在界面上，不落盘）。"""
        return self.atCheck.isChecked()

    def _follow_text(self):
        bind(self.chatFollow, ("跟随" if self._shown == self._chat else "浏览中") if self._chat else "")

    def show_cached(self, result):
        """把某个会话上次的结果放回界面；没有就回到空态。浏览别的会话时只给看不给填——
        微信当前开着的不是它，填进去就串会话了。"""
        if result:
            self.show(result)
        else:
            self._result = None
            self._current = False
            self.set_busy(False)
            self.set_draft_busy(False)
            self.cands = []
            self._clear_cards()
            self.insight.hide()
            self.intentPanel.hide()
            self.tonePanel.hide()
            self.referenceNote.hide()
            self.empty.show()
            bind(self.updated, "", "setText")
            self._empty_text()
        if self._shown != self._chat:
            self._current = False
            self.generateButton.setEnabled(False)
            for card in self.cards:
                card.set_available(False)
            self.set_status(lambda: T("正在查看“{name}”的记录。在聊天窗口切到这个会话后，就能使用回复功能。").format(name=self._shown))

    def show(self, result):
        """按推荐顺序展示，按钮始终绑定 candidates 的原始索引。"""
        self._result = result
        self.cands = result.get("candidates") or []
        self.set_busy(False)
        self._current = not result.get("stale", False) and self._shown == self._chat
        self._clear_cards()
        best = result.get("best_index")
        raw_scores = result.get("scores") or []
        scores = [raw_scores[i] if i < len(raw_scores) else None for i in range(len(self.cands))]
        if not any(scores):  # 全 0/None（旧结果或接口未返回）就不展示百分比
            scores = [None] * len(self.cands)
        # 按概率降序排，推荐位（API 给的 choice）强制第一，同分按原索引
        order = sorted(range(len(self.cands)), key=lambda i: (i != best, -(scores[i] or 0), i))
        for position, index in enumerate(order):
            card = _ReplyCard(self, index, recommended=index == best, number=position + 1, score=scores[index])
            self.replyBox.addWidget(card)
            self.cards.append(card)
        reply_to = result.get("reply_to")
        if "analyzed_text" in result:
            self._show_latest(result["analyzed_text"])
        bind(self.insightTitle, lambda: T("分析摘要 · 对象 {name}").format(name=reply_to)
             if reply_to else T("分析摘要"))
        answers = result.get("answers") or {}
        self.intentPanel.update_answers(answers)
        self.tonePanel.update_answers(answers)
        top = [(label, value) for label, value in ratings(answers, "intent")[:2] if value is not None]
        bind(self.summary, lambda: " · ".join(f"{T(label)} {value}%" for label, value in top) or T("暂无评分"))
        score = (answers.get("danger_level") or {}).get("score")
        valid_score = (not isinstance(score, bool) and isinstance(score, (int, float))
                       and isfinite(score) and 0 <= score <= 9)
        bind(self.tension, lambda: f"{T('紧张度')} {score:.0f}/9" if valid_score else T("紧张度待判断"))
        color = "#996819" if valid_score and score >= 3 else _MUTED
        if valid_score and score >= 6:
            color = "#b44832"
        qss = f"BodyLabel {{ color: {color}; background: transparent; }}"
        setCustomStyleSheet(self.tension, qss, qss)
        self.empty.hide()
        self.insight.show()
        self.intentPanel.show()
        self.tonePanel.show()
        self.referenceNote.setVisible(bool(self.cands) and not self._compact)
        updated_at = result.get("analyzed_at") or datetime.now().strftime("%H:%M")
        bind(self.updated, lambda: updated_at + " " + T("更新"))
        self.set_draft_busy(result.get("draft_busy", False), result.get("draft_error", ""))
        self.set_status("分析已更新", "success")
        if result.get("stale"):
            self.invalidate_replies()
            self.set_status("这里显示上次的分析，等待对方的新消息。")
        if result.get("analysis_busy"):
            self.set_busy(True)

    def _clear_cards(self):
        for card in self.cards:
            self.replyBox.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = []

    def after(self, ms, fn):
        QTimer.singleShot(ms, fn)

    def run(self):
        self.app.exec()
