# -*- coding: utf-8 -*-
"""把选中的候选填进微信输入框：写剪贴板 → 点输入框 → Ctrl+V。绝不发回车、绝不点发送。"""
import ctypes
import ctypes.wintypes as w
import time

u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32

# 64 位下 ctypes.windll 默认 restype 是 32 位 c_int，而 GlobalAlloc 返回 64 位 HGLOBAL——
# 不声明类型句柄会被截断成垃圾值，GlobalLock(垃圾) 返回 NULL，memmove(NULL,…) 就是
# "access violation writing 0x0"。所有带句柄/指针的函数必须显式声明。
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
k32.GlobalFree.argtypes = [ctypes.c_void_p]
u32.SetClipboardData.restype = ctypes.c_void_p
u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
u32.GetForegroundWindow.restype = w.HWND
u32.SetForegroundWindow.argtypes = [w.HWND]
u32.IsWindow.argtypes = [w.HWND]
u32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
u32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
ctypes.windll.dwmapi.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]


def set_clipboard(text):
    """写剪贴板。剪贴板可能被别的程序占着（剪贴板管理器、截图工具），重试几次。"""
    data = text.encode("utf-16-le") + b"\0\0"
    for attempt in range(10):
        if not u32.OpenClipboard(None):
            time.sleep(0.05)
            continue
        try:
            u32.EmptyClipboard()
            h = k32.GlobalAlloc(0x2, len(data))  # GMEM_MOVEABLE
            if not h:
                raise RuntimeError("GlobalAlloc 失败")
            p = k32.GlobalLock(h)
            if not p:
                k32.GlobalFree(h)
                raise RuntimeError("GlobalLock 失败")
            ctypes.memmove(p, data, len(data))
            k32.GlobalUnlock(h)
            if not u32.SetClipboardData(13, h):  # CF_UNICODETEXT；成功后句柄归系统，不能 Free
                k32.GlobalFree(h)
                raise RuntimeError(f"SetClipboardData 失败 (attempt {attempt})")
            return
        finally:
            u32.CloseClipboard()
    raise RuntimeError("OpenClipboard 连续失败，剪贴板被其他程序占用")


def fill(hwnd, area, text, *, expected_title, app=None):
    """area = 消息区 (x0, y0, x1, y1)；输入框就在底线 y1 下面。"""
    from app.capture import unminimize, verify_chat
    from app.chatapps import get

    if not hwnd or not u32.IsWindow(hwnd):
        raise RuntimeError("聊天窗口已关闭，请重新开启采集。")
    unminimize(hwnd)

    # SetForegroundWindow 有前台窗口保护，普通后台进程会被拒；AttachThreadInput 绕过
    fg = u32.GetForegroundWindow()
    if fg != hwnd:
        fg_tid = u32.GetWindowThreadProcessId(fg, None)
        our_tid = k32.GetCurrentThreadId()
        attached = bool(fg_tid and fg_tid != our_tid and u32.AttachThreadInput(our_tid, fg_tid, True))
        try:
            u32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u32.AttachThreadInput(our_tid, fg_tid, False)
        time.sleep(0.15)  # 给微信一点时间响应前台切换
    if u32.GetForegroundWindow() != hwnd:
        raise RuntimeError("无法激活聊天窗口，请切换到该窗口后重试。")

    area = verify_chat(hwnd, expected_title, get(app))
    if u32.GetForegroundWindow() != hwnd:
        raise RuntimeError("当前窗口已切换，请返回聊天窗口后重试。")
    r = w.RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
            raise RuntimeError("无法读取聊天窗口的位置，请重新开启采集。")
    x0, _, _, y1 = area
    cx, cy = r.left + x0 + 60, r.top + y1 + 40
    if not (r.left <= cx < r.right and r.top <= cy < r.bottom):
        raise RuntimeError("输入区域已变化，请等待重新识别后重试。")
    set_clipboard(text)

    old = w.POINT()
    u32.GetCursorPos(ctypes.byref(old))
    u32.SetCursorPos(cx, cy)
    time.sleep(0.05)
    down, up = (0x8, 0x10) if u32.GetSystemMetrics(23) else (0x2, 0x4)
    u32.mouse_event(down, 0, 0, 0, 0)
    u32.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.05)
    u32.SetCursorPos(old.x, old.y)
    time.sleep(0.05)
    if u32.GetForegroundWindow() != hwnd:
        raise RuntimeError("当前窗口已切换，请返回聊天窗口后重试。")
    # 光标移到已有文本的绝对末尾：点击落在文字中间时 caret 会插在中间，
    # 连续多次填入就串行错乱；Ctrl+End 保证新内容永远追加在最后
    u32.keybd_event(0x11, 0, 0, 0)  # Ctrl 按下
    u32.keybd_event(0x23, 0, 0, 0)  # End 按下（VK_END）
    u32.keybd_event(0x23, 0, 2, 0)  # End 抬起
    u32.keybd_event(0x11, 0, 2, 0)  # Ctrl 抬起
    time.sleep(0.05)
    u32.keybd_event(0x11, 0, 0, 0)  # Ctrl
    u32.keybd_event(0x56, 0, 0, 0)  # V
    u32.keybd_event(0x56, 0, 2, 0)
    u32.keybd_event(0x11, 0, 2, 0)
    # 到此为止。发不发、改不改，人来。
