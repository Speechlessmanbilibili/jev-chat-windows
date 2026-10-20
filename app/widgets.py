# -*- coding: utf-8 -*-
"""浅色置顶回复助手：回复建议和独立设置页。发送始终由用户确认。"""
import os
import sys
from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QProgressBar, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, ComboBox, FluentIcon as FIF, PrimaryPushButton, PushButton, TransparentToolButton, setCustomStyleSheet, setFont
from core.intent import ratings
from app.i18n import T, bind

_MUTED = "#68776f"
_GREEN = "#18794e"


def _mp_banner_path() -> str:
    """打包后在 _MEIPASS/docs，源码跑在仓库 docs/。"""
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "docs", "wechat-mp.png")


class _MpBanner(QLabel):
    """公众号长条横幅，宽度跟着设置页走，高度按原图比例。"""

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._src = QPixmap(path)
        self._shown = 0
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        if self._src.isNull() or w <= 0 or self._src.width() <= 0:
            return 0
        return max(1, round(w * self._src.height() / self._src.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        if w <= 0 or w == self._shown or self._src.isNull():
            return
        h = self.heightForWidth(w)
        self._shown = w
        self.setPixmap(self._src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.height() != h:
            self.setFixedHeight(h)


class _FitCombo(ComboBox):
    """长名字不撑开窄布局。按钮上按当前宽度省略；条目仍是全文，findText 靠它。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setText(self, text):
        self._full = text or ""
        QPushButton.setText(self, self._elide(self._full))
        self.setToolTip(self._full if self.text() != self._full else "")

    def setPlaceholderText(self, text):
        index = self.currentIndex()
        super().setPlaceholderText(text)
        # Fluent ComboBox 会连第 0 项一起覆盖；重译占位文案时保留当前会话。
        if index >= 0:
            self.setCurrentIndex(index)
            self.setText(self.itemText(index))

    def minimumSizeHint(self):
        hint = QPushButton.minimumSizeHint(self)
        return QSize(48, hint.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        shown = self._elide(self._full)
        if shown != self.text():
            QPushButton.setText(self, shown)
        self.setToolTip(self._full if shown != self._full else "")

    def _elide(self, text):
        # 右侧箭头大约 28px。还没排上版时先按一个窄宽度省略，避免最小宽度被整句名字撑开。
        avail = self.width() - 36 if self.width() > 64 else 120
        return self.fontMetrics().elidedText(text, Qt.ElideRight, max(24, avail))


def _label(text="", size=14, color=None, bold=False, parent=None):
    label = BodyLabel(text, parent)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    setFont(label, size, QFont.DemiBold if bold else QFont.Normal)
    if color:
        qss = f"BodyLabel {{ color: {color}; background: transparent; }}"
        setCustomStyleSheet(label, qss, qss)
    return label


def _tlabel(source, *args, **kwargs):
    return bind(_label("", *args, **kwargs), source)


def _tool(icon, title, callback, parent=None):
    button = TransparentToolButton(icon, parent)
    button.setFixedSize(32, 32)
    bind(button, title, "setToolTip")
    bind(button, title, "setAccessibleName")
    button.clicked.connect(callback)
    return button


class _Surface(CardWidget):
    def __init__(self, parent=None, accent=False):
        self.accent = accent
        super().__init__(parent)
        self.setBorderRadius(12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _normalBackgroundColor(self):
        return QColor("#edf7f0" if self.accent else "#ffffff")

    def _hoverBackgroundColor(self):
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()


class _Fetched(QObject):
    """取模型列表的后台线程 → 主线程：控件组、请求版本号、模型 id、失败原因。
    Qt 不让跨线程碰控件，信号是跨线程唯一干净的路。"""
    done = Signal(object, int, list, str)


class _TitleBar(QWidget):
    """只有标题栏可拖动，选择正文或按按钮不会意外移动窗口。"""
    def __init__(self, parent):
        super().__init__(parent)
        self._drag = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.window().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)


class _MainWindow(QWidget):
    """窗口大小变了就叫 Overlay 重新排布；断点没跨过时 _relayout 自己不做事，这里不用防抖。"""
    def __init__(self, relayout):
        super().__init__()
        self._relayout = relayout

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(event.size().width(), event.size().height())


class _ReplyCard(_Surface):
    def __init__(self, owner, index, recommended=False, number=1, score=None):
        super().__init__(accent=recommended)
        box = QVBoxLayout(self)
        self.box = box
        box.setSpacing(10)
        top = QHBoxLayout()
        title = lambda: T("推荐回复") if recommended else f"{T('候选')} {number}"
        top.addWidget(_tlabel(lambda: title() + (f" · {round(score * 100)}%" if score is not None else ""),
                             12, _GREEN if recommended else _MUTED, True))
        self.copyButton = _tool(FIF.COPY, "复制这条回复", lambda: owner._copy(index), self)
        self.copyButton.setFixedSize(24, 24)
        top.addWidget(self.copyButton)
        box.addLayout(top)
        self.text = _label(owner.cands[index], 15)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.text)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.fillButton = bind((PrimaryPushButton if recommended else PushButton)("", self), "填入")
        bind(self.fillButton, lambda: T("填入 {reply}").format(reply=title()), "setAccessibleName")
        self.fillButton.clicked.connect(lambda: owner._fill(index))
        bottom.addWidget(self.fillButton)
        box.addLayout(bottom)
        self.set_compact(owner._compact)

    def set_available(self, enabled):
        self.fillButton.setEnabled(enabled)
        self.copyButton.setEnabled(True)

    def set_compact(self, compact):
        self.box.setContentsMargins(12, 8, 12, 8) if compact else self.box.setContentsMargins(16, 12, 16, 12)
        self.fillButton.setMinimumWidth(80 if compact else 100)


class _RatingsPanel(_Surface):
    """独立排序的程度分数面板，默认展示前四项。"""
    def __init__(self, title, kind, color):
        super().__init__()
        self.kind, self.color = kind, color
        self.expanded = False
        self.values = []
        self.rows = []
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)
        heading = QHBoxLayout()
        heading.addWidget(_tlabel(title, 14, "#304c3c", True), 1)
        self.toggle = bind(PushButton(""), "展开全部")
        self.toggle.clicked.connect(self._toggle)
        heading.addWidget(self.toggle)
        box.addLayout(heading)
        self.items = QVBoxLayout()
        self.items.setSpacing(6)
        box.addLayout(self.items)

    def _toggle(self):
        self.expanded = not self.expanded
        self.render()

    def update_answers(self, answers):
        self.values = ratings(answers, self.kind)
        self.render()

    def render(self):
        for widget in self.rows:
            self.items.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self.rows = []
        for label, value in self.values if self.expanded else self.values[:4]:
            widget = QWidget()
            box = QVBoxLayout(widget)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(3)
            line = QHBoxLayout()
            line.addWidget(_tlabel(label, 12), 1)
            line.addWidget(_label(f"{value}%" if value is not None else "—", 12, self.color))
            box.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(value or 0)
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            bar.setStyleSheet(f"QProgressBar {{border:0; background:#e5ebe7; border-radius:2px;}}"
                             f"QProgressBar::chunk {{background:{self.color}; border-radius:2px;}}")
            bind(bar, lambda label=label, value=value:
                 f"{T(label)} {value}%" if value is not None else f"{T(label)} —", "setAccessibleName")
            box.addWidget(bar)
            self.items.addWidget(widget)
            self.rows.append(widget)
        bind(self.toggle, "收起" if self.expanded else "展开全部")
