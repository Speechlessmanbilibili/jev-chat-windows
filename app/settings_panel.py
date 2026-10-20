# -*- coding: utf-8 -*-
"""浅色置顶回复助手：回复建议和独立设置页。发送始终由用户确认。"""
import os
import threading
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, EditableComboBox, FluentIcon as FIF, LineEdit, PasswordLineEdit, PrimaryPushButton, PushButton, SpinBox, SwitchButton, setCustomStyleSheet
from app import i18n, settings
from core import jev_client, llm, providers
from app.i18n import LANGUAGES, T, bind
from app.widgets import _MUTED, _GREEN, _MpBanner, _label, _tlabel, _tool, _Surface, _Fetched, _mp_banner_path

_RELATIONSHIPS = [
    ("恋人", "romantic partners"), ("朋友", "friends"), ("同事", "colleagues"),
    ("家人", "family"), ("自定义", None),
]


class SettingsPanel:
    def _build_settings(self):
        self.settingsPage, body = self._scroll_page()
        heading = QHBoxLayout()
        heading.addWidget(_tool(FIF.RETURN, "返回意图分析", self._back_home))
        heading.addWidget(_tlabel("设置", 23, "#24382d", True), 1)
        body.addLayout(heading)
        banner = _mp_banner_path()
        if os.path.exists(banner):
            body.addWidget(_MpBanner(banner))

        language = _Surface()
        box = QVBoxLayout(language)
        box.setContentsMargins(16, 16, 16, 18)
        box.setSpacing(12)
        language_label = _tlabel("界面语言 / Language", 16, "#304c3c", True)
        box.addWidget(language_label)
        self.languageBox = ComboBox()
        self.languageBox.setMinimumWidth(0)
        self.languageBox.addItems([name for name, code in LANGUAGES])
        bind(self.languageBox, "界面语言 / Language", "setAccessibleName")
        language_label.setBuddy(self.languageBox)
        self.languageBox.currentIndexChanged.connect(self._language_changed)
        box.addWidget(self.languageBox)
        self.languageHint = _label("", 12, _MUTED)
        box.addWidget(self.languageHint)
        self.languageOverrideHint = _tlabel("本次选择立即生效；下次启动仍优先使用 JEVCHAT_LANG 指定的语言。", 12, _MUTED)
        box.addWidget(self.languageOverrideHint)
        body.addWidget(language)

        body.addWidget(_tlabel("设置关系背景和模型，让分析和回复更贴近你们的对话。", 13, _MUTED))
        preference = _Surface()
        box = QVBoxLayout(preference)
        box.setContentsMargins(16, 16, 16, 18)
        box.setSpacing(12)
        box.addWidget(_tlabel("回复偏好", 16, "#304c3c", True))
        relation_label = _tlabel("关系背景", 13)
        box.addWidget(relation_label)
        self.relationshipBox = ComboBox()
        self.relationshipBox.setMinimumWidth(0)
        self.relationshipBox.addItems([T(name) for name, value in _RELATIONSHIPS])
        bind(self.relationshipBox, "关系背景", "setAccessibleName")
        relation_label.setBuddy(self.relationshipBox)
        box.addWidget(self.relationshipBox)
        self.relEdit = LineEdit()
        bind(self.relEdit, "例如：刚认识的朋友，还不太熟悉", "setPlaceholderText")
        bind(self.relEdit, "自定义关系背景", "setAccessibleName")
        box.addWidget(self.relEdit)
        self.relationshipBox.currentIndexChanged.connect(
            lambda index: self.relEdit.setVisible(_RELATIONSHIPS[index][1] is None)
        )
        box.addWidget(self._hint("简单说明你们的关系，帮助调整称呼和回复语气。"))
        style_label = _tlabel("说话风格（可选）", 13)
        box.addWidget(style_label)
        self.styleEdit = LineEdit()
        bind(self.styleEdit, "例如：简短自然，少用表情，不说客套话", "setPlaceholderText")
        bind(self.styleEdit, "说话风格", "setAccessibleName")
        style_label.setBuddy(self.styleEdit)
        box.addWidget(self.styleEdit)
        box.addWidget(self._hint("会参考你最近的消息来写，也可以在这里补充你的说话习惯。"))
        context_label = _tlabel("上下文消息数", 13)
        box.addWidget(context_label)
        self.contextBox = SpinBox()
        self.contextBox.setRange(3, 30)
        bind(self.contextBox, "参考的最近消息条数", "setAccessibleName")
        context_label.setBuddy(self.contextBox)
        box.addWidget(self.contextBox)
        box.addWidget(self._hint(
            "分析和生成回复时，参考最近的 3～30 条消息。"
        ))
        target_row = QHBoxLayout()
        target_row.addWidget(_tlabel("群聊指定回复对象", 13), 1)
        self.targetSwitch = SwitchButton()
        bind(self.targetSwitch, "开启", "setOnText")
        bind(self.targetSwitch, "关闭", "setOffText")
        bind(self.targetSwitch, "群聊指定回复对象", "setAccessibleName")
        target_row.addWidget(self.targetSwitch)
        box.addLayout(target_row)
        box.addWidget(self._hint(
            "开启后，可以选择群聊中要分析和回复的人；关闭时跟随最新发言。"
        ))
        update_row = QHBoxLayout()
        update_row.addWidget(_tlabel("启动时检查更新", 13), 1)
        self.updateSwitch = SwitchButton()
        bind(self.updateSwitch, "开启", "setOnText")
        bind(self.updateSwitch, "关闭", "setOffText")
        bind(self.updateSwitch, "启动时检查更新", "setAccessibleName")
        update_row.addWidget(self.updateSwitch)
        box.addLayout(update_row)
        box.addWidget(self._hint(
            "启动时查询 GitHub 上的最新版本，不提交聊天内容。"
        ))
        debug_row = QHBoxLayout()
        debug_row.addWidget(_tlabel("调试视图", 13), 1)
        self.debugSwitch = SwitchButton()
        bind(self.debugSwitch, "开启", "setOnText")
        bind(self.debugSwitch, "关闭", "setOffText")
        bind(self.debugSwitch, "调试视图", "setAccessibleName")
        self.debugSwitch.checkedChanged.connect(self._debug_toggled)  # 这个开关立刻生效，不等「保存设置」
        debug_row.addWidget(self.debugSwitch)
        box.addLayout(debug_row)
        box.addWidget(self._hint(
            "在独立窗口中显示采集画面、文字识别框及处理状态。画面仅在内存中显示。"
        ))
        body.addWidget(preference)

        models = _Surface()
        box = QVBoxLayout(models)
        box.setContentsMargins(16, 16, 16, 18)
        box.setSpacing(12)
        box.addWidget(_tlabel("模型", 16, "#304c3c", True))
        self._fetched = _Fetched()
        self._fetched.done.connect(self._models_fetched)
        self.jev = self._model_group(box, "分析模型", "jev", providers.JEV_PROVIDERS)
        box.addWidget(self._hint(
            "分析意图、语气和紧张度，并为回复建议排序。"
        ))
        draft_settings_toggle = bind(PushButton(""), "回复起草设置（可选）")
        self.draftSettings = QWidget()
        draft_settings_toggle.clicked.connect(lambda: self.draftSettings.setVisible(self.draftSettings.isHidden()))
        box.addWidget(draft_settings_toggle)
        draft_settings_box = QVBoxLayout(self.draftSettings)
        draft_settings_box.setContentsMargins(0, 0, 0, 0)
        self.draft = self._model_group(draft_settings_box, "回复起草模型", "draft", providers.DRAFT_PROVIDERS)
        draft_settings_box.addWidget(self._hint(
            "生成回复建议，使用单独的 API 密钥。"
        ))
        think_row = QHBoxLayout()
        think_row.addWidget(_tlabel("起草时开启思考模式", 13), 1)
        self.thinkingSwitch = SwitchButton()
        bind(self.thinkingSwitch, "开启", "setOnText")
        bind(self.thinkingSwitch, "关闭", "setOffText")
        bind(self.thinkingSwitch, "起草时开启思考模式", "setAccessibleName")
        think_row.addWidget(self.thinkingSwitch)
        draft_settings_box.addLayout(think_row)
        draft_settings_box.addWidget(self._hint(
            lambda: T("开启后，模型会先思考再生成回复，耗时和费用可能增加。支持：{providers}。")
            .format(providers=" / ".join(providers.THINKING))
        ))
        box.addWidget(self.draftSettings)
        self.draftSettings.hide()
        body.addWidget(models)
        self.settingsFeedback = _label("", 13, _GREEN)
        self.settingsFeedback.hide()
        body.addWidget(self.settingsFeedback)
        actions = QHBoxLayout()
        back = bind(PushButton(""), "返回")
        back.clicked.connect(self._back_home)
        actions.addWidget(back)
        actions.addStretch(1)
        self.saveButton = bind(PrimaryPushButton(""), "保存设置")
        self.saveButton.clicked.connect(self._save)
        actions.addWidget(self.saveButton)
        body.addLayout(actions)
        body.addWidget(self._hint("保存后会更新分析，回复设置在下次生成时生效。"))
        body.addStretch(1)
        self._load_settings()

    def _hint(self, text):
        """设置页字段下面的灰字说明：记下来，紧凑模式一起隐藏。"""
        label = _tlabel(text, 12, _MUTED)
        self._hintLabels.append(label)
        return label

    def _model_group(self, box, title, kind, table):
        """一组「来源 / 密钥 / 模型」控件，判断和起草各一份。table 是 core/providers.py 里那张表。"""
        group = SimpleNamespace(kind=kind, table=table, ids=list(table),
                                keyTitle="分析" if kind == "jev" else "起草",
                                stored_key=lambda: "", fetch_revision=0)
        heading = QHBoxLayout()
        heading.addWidget(_tlabel(title, 14, "#304c3c", True), 1)
        group.keyState = _label("", 12, _GREEN)
        group.keyState.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        heading.addWidget(group.keyState)
        box.addLayout(heading)
        source_label = _tlabel("来源", 13)
        box.addWidget(source_label)
        group.providerBox = ComboBox()
        group.providerBox.setMinimumWidth(0)  # 选项文字长短不一，别让它撑开设置页
        group.providerBox.addItems([T(table[i].name) for i in group.ids])
        bind(group.providerBox, lambda: f"{T(title)} · {T('来源')}", "setAccessibleName")
        source_label.setBuddy(group.providerBox)
        box.addWidget(group.providerBox)
        if kind == "draft":  # 只有两个「自定义」来源要自己填地址，别的来源这一行藏着
            self.baseLabel = _label("Base URL", 13)
            box.addWidget(self.baseLabel)
            self.baseEdit = LineEdit()
            bind(self.baseEdit, "https://example.com/v1", "setPlaceholderText")
            bind(self.baseEdit, "自定义来源 Base URL", "setAccessibleName")
            self.baseLabel.setBuddy(self.baseEdit)
            box.addWidget(self.baseEdit)
        if kind == "jev":
            self.jevBaseLabel = _label("LM Studio URL", 13)
            self.jevBaseEdit = LineEdit()
            self.jevBaseEdit.setPlaceholderText(providers.LMSTUDIO_BASE)
            self.jevBaseLabel.setBuddy(self.jevBaseEdit)
            box.addWidget(self.jevBaseLabel)
            box.addWidget(self.jevBaseEdit)
        key_label = group.keyLabel = _tlabel("密钥", 13)
        box.addWidget(key_label)
        group.keyEdit = PasswordLineEdit()
        bind(group.keyEdit, lambda: f"{T(title)} · {T('密钥')}", "setAccessibleName")
        key_label.setBuddy(group.keyEdit)
        group.keyEdit.returnPressed.connect(self._save)
        box.addWidget(group.keyEdit)
        group.keyHint = self._hint("" if kind == "jev" else
                                   "起草 API 密钥保存至 LLM_API_KEY，与分析 API 密钥独立。")
        box.addWidget(group.keyHint)
        model_label = _tlabel("模型", 13)
        box.addWidget(model_label)
        row = QHBoxLayout()
        row.setSpacing(8)
        group.modelBox = EditableComboBox()  # 能选也能手打，接口新出的模型不用等我改代码
        group.modelBox.setMinimumWidth(0)
        bind(group.modelBox, lambda: f"{T(title)} · {T('模型')}", "setAccessibleName")
        model_label.setBuddy(group.modelBox)
        row.addWidget(group.modelBox, 1)
        group.fetchButton = bind(PushButton(""), "获取模型")
        bind(group.fetchButton, lambda: f"{T(title)} · {T('获取模型')}", "setAccessibleName")
        group.fetchButton.clicked.connect(lambda: self._fetch_models(group))
        row.addWidget(group.fetchButton)
        box.addLayout(row)
        group.status = _label("", 12, _MUTED)
        box.addWidget(group.status)
        group.providerBox.currentIndexChanged.connect(lambda _: self._provider_changed(group))
        group.stored_key = lambda: (settings.jev_key(self._provider_of(group)) if kind == "jev"
                                    else settings.llm_key(self._provider_of(group)))
        return group

    @staticmethod
    def _provider_of(group):
        return group.ids[max(0, group.providerBox.currentIndex())]

    def _provider_changed(self, group):
        """换来源：模型框回到这家该有的值（存的就是这家才用存的，否则用它的默认），状态清掉。"""
        group.fetch_revision += 1
        group.fetchButton.setEnabled(True)
        provider = self._provider_of(group)
        saved = settings.jev_provider() if group.kind == "jev" else settings.draft_provider()
        stored = settings.jev_model() if group.kind == "jev" else settings.draft_model()
        group.modelBox.clear()
        group.keyEdit.clear()
        group.modelBox.setText(stored if provider == saved else group.table[provider].default)
        bind(group.status, "", "setText")
        self._sync_model_fields()

    def _sync_model_fields(self):
        """两组共用：密钥已配置/未配置、占位文案、自定义 Base URL 行的显隐，
        外加紧凑模式下把来源按钮上的文字省略——ComboBox 是 QPushButton，
        minimumSizeHint 按整段文字算，不会自动换行/省略，长名字会把设置页撑宽。"""
        for group in (self.jev, self.draft):
            provider = self._provider_of(group)
            name = T(group.table[provider].name)
            configured = bool(group.stored_key())
            local = group.kind == "jev" and provider == "lmstudio"
            bind(group.keyState, "已配置" if configured else "令牌可选" if local else "未配置")
            bind(group.keyLabel, "认证令牌（可选）" if local else "密钥")
            bind(group.keyEdit, "已配置，留空可保留现有密钥" if configured else
                 "启用 LM Studio 认证后填写" if local else
                 lambda name=name: T("输入 {name} API 密钥").format(name=name), "setPlaceholderText")
            if group.kind == "jev":
                bind(group.keyHint, "连接本地服务；未启用认证时，令牌可留空。" if local else
                     "使用 OpenAI API 密钥，可读取 OPENAI_API_KEY 环境变量。" if provider == "openai" else
                     "使用所选服务的 API 密钥，可读取 JEV_API_KEY 环境变量。")
            if self._compact:
                name = group.providerBox.fontMetrics().elidedText(name, Qt.ElideRight, 180)
            group.providerBox.setText(name)
        local = self._provider_of(self.jev) == "lmstudio"
        self.jevBaseLabel.setVisible(local)
        self.jevBaseEdit.setVisible(local)
        custom = self._provider_of(self.draft) in providers.CUSTOM
        self.baseLabel.setVisible(custom)
        self.baseEdit.setVisible(custom)

    def _fetch_models(self, group):
        """「获取模型」：拿填的 key（没填就拿存的）去问接口，网络调用丢后台线程。"""
        provider = self._provider_of(group)
        custom = group.kind == "draft" and provider in providers.CUSTOM
        local = group.kind == "jev" and provider == "lmstudio"
        base = self.jevBaseEdit.text().strip() if local else self.baseEdit.text().strip() if custom else None
        key = group.keyEdit.text().strip() or group.stored_key()
        if not key and not local:
            bind(group.status, "请先输入 API 密钥。", "setText")
            return
        if custom and not base:
            bind(group.status, "请先填写服务地址。", "setText")
            return
        bind(group.status, "获取中…", "setText")
        group.fetchButton.setEnabled(False)
        group.fetch_revision += 1
        revision = group.fetch_revision
        threading.Thread(target=lambda: self._list_models(group, provider, key, base, revision),
                         daemon=True).start()

    def _list_models(self, group, provider, key, base, revision):
        """后台线程：判断走 jev_client，起草按协议走 llm；失败把原因一起送回主线程。"""
        try:
            if group.kind == "jev":
                models = jev_client.list_models(provider, key, base_url=base)
            else:
                spec = providers.DRAFT_PROVIDERS[provider]
                models = llm.list_models(spec.protocol, base or spec.base, key, headers=spec.headers)
                if spec.keep:  # 目录里混了别的协议时，只留这条路打得通的
                    models = [m for m in models if spec.keep(m)]
            reason = "" if models else "所选服务未返回可用模型。"
        except Exception as exc:  # 线程里漏异常会静默吞掉，按钮就永远停在禁用态
            # 新填的密钥尚未进入环境变量，也要在截断错误文本前完整脱敏。
            models, reason = [], jev_client.redact_secrets(str(exc), key)[:120]
        self._fetched.done.emit(group, revision, models, reason)

    def _models_fetched(self, group, revision, models, reason):
        """回到主线程：填进下拉框，原来选中的还在列表里就留着。"""
        if revision != group.fetch_revision:
            return
        group.fetchButton.setEnabled(True)
        if not models:
            bind(group.status, reason or "模型列表获取失败，请检查 API 密钥、网络及服务地址。")
            return
        current = group.modelBox.text().strip()
        group.modelBox.clear()
        group.modelBox.addItems(models)
        if current in models:
            group.modelBox.setCurrentIndex(models.index(current))
        else:
            group.modelBox.setText(current)  # 手打的没在列表里也不清掉
        bind(group.status, lambda: T("共 {count} 个").format(count=len(models)))

    def _set_group(self, group, provider, model):
        """把存下来的来源和模型放回一组控件里；填充不算用户操作，别触发换来源的重置。"""
        group.fetch_revision += 1
        group.fetchButton.setEnabled(True)
        group.providerBox.blockSignals(True)
        group.providerBox.setCurrentIndex(group.ids.index(provider))
        group.providerBox.blockSignals(False)
        group.keyEdit.clear()
        group.modelBox.clear()
        group.modelBox.setText(model)
        bind(group.status, "", "setText")

    def _load_language(self):
        lang = i18n.language()
        index = next((i for i, (_, code) in enumerate(LANGUAGES) if code == lang), 0)
        self.languageBox.blockSignals(True)
        self.languageBox.setCurrentIndex(index)
        self.languageBox.blockSignals(False)
        bind(self.languageHint, "选择后立即生效，并自动保存。", "setText")
        self.languageOverrideHint.setVisible(bool(os.environ.get("JEVCHAT_LANG", "").strip()))

    def _language_changed(self, index):
        if not 0 <= index < len(LANGUAGES):
            return
        try:
            settings.save(lang_text=LANGUAGES[index][1])
        except Exception:
            self._load_language()
            bind(self.languageHint, "语言保存失败，请检查配置文件是否可写后重试。", "setText")
            return
        i18n.reload(LANGUAGES[index][1])
        self._retranslate()
        bind(self.languageHint, "语言已切换并保存。", "setText")
        if self.on_language_changed:
            self.on_language_changed()

    def _retranslate(self):
        """只重画文字，保留输入、控件状态和进行中的模型请求。"""
        i18n.retranslate(self.win)
        blocked = self.relationshipBox.blockSignals(True)
        for index, (name, _) in enumerate(_RELATIONSHIPS):
            self.relationshipBox.setItemText(index, T(name))
        self.relationshipBox.blockSignals(blocked)
        for group in (self.jev, self.draft):
            blocked = group.providerBox.blockSignals(True)
            for index, provider in enumerate(group.ids):
                group.providerBox.setItemText(index, T(group.table[provider].name))
            group.providerBox.blockSignals(blocked)
        self._sync_model_fields()
        self._refresh_history_text()

    def _load_settings(self):
        self._load_language()
        relationship = settings.relationship()
        index = next((i for i, (_, value) in enumerate(_RELATIONSHIPS) if value == relationship),
                     len(_RELATIONSHIPS) - 1)
        self.relationshipBox.setCurrentIndex(index)
        self.relEdit.setText(relationship if _RELATIONSHIPS[index][1] is None else "")
        self.relEdit.setVisible(_RELATIONSHIPS[index][1] is None)
        self.styleEdit.setText(settings.style())
        self.contextBox.setValue(settings.context())
        self.targetSwitch.setChecked(settings.reply_target())
        self._set_group(self.jev, settings.jev_provider(), settings.jev_model())
        self._set_group(self.draft, settings.draft_provider(), settings.draft_model())
        self.baseEdit.setText(settings.draft_base_url())
        self.jevBaseEdit.setText(settings._text("jev_base_url", providers.LMSTUDIO_BASE))
        self.thinkingSwitch.setChecked(settings.thinking())
        self.updateSwitch.setChecked(settings.check_update())
        self.set_debug_switch(settings.debug_view())  # 屏蔽信号地拨，别在加载时开关一遍窗口
        self._sync_model_fields()  # 上面屏蔽了信号，这里补一次
        self.settingsFeedback.hide()

    def _save(self):
        previous_analysis = (settings.analysis_options(), settings.reply_target())
        relationship = _RELATIONSHIPS[self.relationshipBox.currentIndex()][1]
        relationship = relationship or self.relEdit.text().strip()
        jev_provider = self._provider_of(self.jev)
        draft_provider = self._provider_of(self.draft)
        base = self.baseEdit.text().strip()
        if not relationship:
            self._settings_feedback("请填写关系背景，或选择一个已有选项。", error=True)
            self.relEdit.setFocus()
            return
        for group, provider in ((self.jev, jev_provider),):
            name = group.table[provider].name
            if provider != "lmstudio" and not group.keyEdit.text().strip() and not group.stored_key():
                self._settings_feedback(lambda group=group:
                                        T("请先填写 {name} 的 API 密钥。").format(name=T(group.keyTitle)), error=True)
                group.keyEdit.setFocus()
                return
            if not group.modelBox.text().strip():
                self._settings_feedback(lambda: T("请选择或输入 {name} 的模型名称。").format(name=name), error=True)
                group.modelBox.setFocus()
                return
        try:
            settings.save(relationship, self.contextBox.value(),
                          jev_provider_text=jev_provider,
                          jev_key_text=self.jev.keyEdit.text().strip() or None,
                          jev_model_text=self.jev.modelBox.text().strip(),
                          draft_provider_text=draft_provider,
                          llm_key_text=self.draft.keyEdit.text().strip() or None,
                          draft_model_text=self.draft.modelBox.text().strip(),
                          draft_base_url_text=base,
                          reply_target_on=self.targetSwitch.isChecked(),
                          style_text=self.styleEdit.text().strip(),
                          thinking_on=self.thinkingSwitch.isChecked(),
                          check_update_on=self.updateSwitch.isChecked())
        except Exception:
            self._settings_feedback("设置保存失败，请检查配置文件写入权限及用户环境变量权限。", error=True)
            return
        self._load_settings()
        self._render_targets()  # 开关刚改过，回到首页时这一行该显该藏得重算一次
        self._settings_feedback("设置已保存。")
        if (self.on_analysis_settings_changed
                and previous_analysis != (settings.analysis_options(), settings.reply_target())):
            self.on_analysis_settings_changed()
        self.setupButton.hide()
        if not self.cands and not self._busy:
            self._empty_text()
            self.set_status("准备就绪，等待新消息。", "idle")

    def _debug_toggled(self, on):
        """调试视图独立于「保存设置」：拨一下就开窗/收窗，顺手落盘，重启还在。"""
        try:
            settings.save(debug_view_on=on)
        except Exception:
            self.set_debug_switch(settings.debug_view())
            self._settings_feedback("设置保存失败，请检查配置文件写入权限及用户环境变量权限。", error=True)
            return
        if self.on_toggle_debug:
            self.on_toggle_debug(on)

    def set_debug_switch(self, on):
        """调试窗被用户直接关掉时把开关拨回去；屏蔽信号，免得又回调一圈。"""
        self.debugSwitch.blockSignals(True)
        self.debugSwitch.setChecked(on)
        self.debugSwitch.blockSignals(False)

    def _settings_feedback(self, text, error=False):
        color = "#b44832" if error else _GREEN
        qss = f"BodyLabel {{ color: {color}; background: transparent; }}"
        setCustomStyleSheet(self.settingsFeedback, qss, qss)
        bind(self.settingsFeedback, text)
        self.settingsFeedback.show()

    def open_settings(self):
        if self.pages.currentWidget() != self.settingsPage:
            self._load_settings()
        self.pages.setCurrentWidget(self.settingsPage)
        self.settingsButton.setEnabled(False)
        self.languageBox.setFocus()
        self.settingsPage.verticalScrollBar().setValue(0)

    def _back_home(self):
        self.jev.keyEdit.clear()
        self.draft.keyEdit.clear()
        self.pages.setCurrentWidget(self.home)
        self.settingsButton.setEnabled(True)
