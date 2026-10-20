# -*- coding: utf-8 -*-
"""子进程：截图 → 定位消息区 → OCR 头部会话名和消息 → 按会话去重，全在这边跑。
一次 OCR 250~800ms，放父进程的 Qt 主线程界面就僵了。
只往队列里丢纯 tuple/str（底色 bg 是 numpy，留在这边不过队列）。帧全程内存，绝不落盘。"""
import ctypes
import time

import numpy as np

from app import chatapps
from app.capture import Capture, chat_area, unminimize, window_scale
from app.ocr import Reader, read_title


def _packet(full, area, title, reader, lines):
    """调试视图的一帧：整帧缩到长边 ≤1100 再走队列（原帧 2560 宽裸传要 20MB），只在内存里传，不落盘。
    整数步长切片够用，不引新依赖；框和坐标照发原始值，画的那边按 scale 折算。"""
    k = max(1, -(-max(full.shape[:2]) // 1100))
    small = np.ascontiguousarray(full[::k, ::k])
    return {"w": small.shape[1], "h": small.shape[0], "rgb": small.tobytes(), "scale": k,
            "area": tuple(int(v) for v in area[:4]) if area else None,
            "pane_top": int(area[5]) if area else 0, "title": title,
            "boxes": reader.last_boxes if reader else [],
            "lines": [(w, n, t) for w, n, t, _ in lines],
            "ocr_ms": reader.last_ms if reader else 0, "ts": time.time()}


def run(q, hwnd, enabled, debug_on, app_key=None):
    """enabled 置位=采集，清掉=暂停。暂停时停掉 WGC 会话（Windows 那圈黄色采集边框也跟着没了），
    恢复时重开一个；readers 一直留着，去重状态不丢，恢复后不会把屏幕上的旧消息再报一遍。
    debug_on 置位才往队列里送整帧（一帧 2~3MB），关着一点额外活都不干。"""
    ctypes.windll.user32.SetProcessDPIAware()
    app = chatapps.get(app_key)
    cap = None
    readers = {}  # {会话名: Reader}，一个会话一套去重状态
    title, head = "", None  # 当前会话名 / 上一帧的头部像素
    last_area = None  # 上次发给父进程的 4 元组，变了才再发一次
    warned = False  # 消息区识别失败是否已经报过，拖窗口时别每帧刷一条
    retry_frame, retry_at = None, 0.0
    started, received, waiting_warned = time.monotonic(), False, False
    while True:
        if not enabled.is_set():
            if cap is not None:
                cap.stop()
                cap = None
                q.put(("paused",))
            enabled.wait()
            continue
        if cap is None:
            try:
                cap = Capture(hwnd, app=app)
                started, received, waiting_warned = time.monotonic(), False, False
            except Exception as e:
                q.put(("dead", "无法开始采集：" + (" ".join(str(e).split())[:120] or type(e).__name__)))
                return
            q.put(("resumed",))
        if not cap.alive():
            break
        try:
            unminimize(hwnd)
            full = cap.settled()
            if full is not None:
                retry_frame = None
            if full is None and retry_frame is not None and time.monotonic() >= retry_at:
                full = retry_frame
            if full is None and not received and not waiting_warned and time.monotonic() - started >= 8:
                q.put(("status", "尚未收到有效画面，请检查聊天窗口是否允许截图，或重新开启采集。"))
                waiting_warned = True
            if full is not None:
                received = True
                reader, lines = None, []  # 调试视图要用，消息区没认出来时就是空的
                scale = window_scale(hwnd)
                area = chat_area(full, app=app, scale=scale)  # 停稳后重算，同时适应跨屏后的 DPI。
                if area is None:
                    if not warned:
                        q.put(("status", "未能定位消息区域，请适当放大聊天窗口。"))
                        warned = True
                else:
                    warned = False
                    cap.set_area(area, full.shape, scale=scale)
                    x0, y0, x1, y1, bg, y_pane = area
                    rect = (x0, y0, x1, y1)
                    if rect != last_area:
                        q.put(("area", rect))
                        last_area = rect
                    crop = full[y_pane:y0, x0:x1]  # 头部：会话名在这里
                    if head is None or not np.array_equal(crop, head):  # 名字没动就别白跑一次 OCR
                        name = read_title(crop, app)
                        if not name:
                            if retry_frame is None:
                                q.put(("status", "未能识别会话名称，正在重试。请保持聊天窗口可见。"))
                            retry_frame, retry_at = full, time.monotonic() + 0.5
                            time.sleep(0.05)
                            continue
                        head = crop.copy()
                        retry_frame = None
                        # 会话名称严格匹配，避免相近名称的不同会话共用消息与分析。
                        if name != title:
                            title = name
                            q.put(("chat", title))
                    if title not in readers:
                        readers[title] = Reader(app)
                    reader = readers[title]
                    lines = reader.read(full[y0:y1, x0:x1], bg)
                    new = reader.new_lines(lines)
                    if new:
                        q.put(("lines", title, new, rect))
                if debug_on.is_set():
                    q.put(("debug", _packet(full, area, title, reader, lines)))
        except Exception as exc:
            cap.stop()
            q.put(("dead", f"识别已停止：{type(exc).__name__}: {exc}"))
            return
        time.sleep(0.05)
    try:
        cap.wait()
    except Exception as exc:
        q.put(("dead", f"采集已停止：{exc}"))
    else:
        q.put(("dead", "采集已停止，请确认聊天窗口已打开后重新开启采集。"))
