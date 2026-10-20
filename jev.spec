# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包定义，由 tools/build_release.ps1 统一调用。
onedir 不是 onefile：PySide6 + onnxruntime 打出来 ~150MB，onefile 每次启动都要解压一遍，慢且占临时盘。
只在 Windows 上跑，下面的 collect_all 也只认 Windows 上装好的那几个包。"""
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files
import os

NAME = "jev-chat-windows"

hiddenimports = ["socksio"]
for sdk in ("openai", "typesafe_sdk", "anthropic", "google.genai"):
    hiddenimports += collect_submodules(sdk)
datas, binaries = [], []
datas += [("docs/wechat-mp.png", "docs")]  # 设置页底部的公众号长条横幅
for pkg in (
    "rapidocr_onnxruntime",  # .onnx 模型 + config.yaml 是包数据，不收就是启动即炸
    "onnxruntime",           # capi 下面那堆 DLL
    "qfluentwidgets",        # qss / 图标资源
    "windows_capture",       # Rust 编译的 .pyd
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("certifi")

excludes = [
    # 确认没人用：rapidocr 只 import 了 cv2 / PIL / yaml / pyclipper / shapely（PIL 千万别排，读图要它）
    "tkinter", "matplotlib", "scipy", "pandas",
] + ["PySide6." + m for m in (
    # 留着 QtCore / QtGui / QtWidgets / QtSvg / QtSvgWidgets / QtXml —— import qfluentwidgets 实测就这六个
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel",
    "QtMultimedia", "QtMultimediaWidgets", "QtCharts", "QtDataVisualization",
    "QtQuick", "QtQuick3D", "QtQuickControls2", "QtQuickWidgets", "QtQuickTest", "QtQml",
    "QtPdf", "QtPdfWidgets", "QtBluetooth", "QtNfc", "QtSensors", "QtSerialPort",
    "QtTest", "QtDesigner", "QtHelp", "QtRemoteObjects", "QtScxml", "QtStateMachine",
    "QtTextToSpeech", "QtPositioning", "QtLocation", "QtSql",
    "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras",
)]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
# Qt 使用 Windows 自带的 ICU 接口。构建环境 PATH 中其他工具的同名
# ICU DLL 可能带版本化符号，打入包中会覆盖系统接口并导致 QtCore 加载失败。
a.binaries = [entry for entry in a.binaries
              if os.path.basename(entry[0]).lower() not in {"icu.dll", "icuuc.dll", "icuin.dll"}
              and not os.path.basename(entry[0]).lower().startswith("icudt")]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # runner 上本来就没 upx，而且压 Qt / onnxruntime 的 DLL 是出了名的能压坏
    console=os.environ.get("JEV_BUILD_CONSOLE") == "1",  # 本地诊断可启用控制台，正式构建保持图形模式
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="docs/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NAME,
)
