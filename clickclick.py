# -*- coding: UTF-8 -*-
"""
 Copyright (c) 2026 yushihong. Licensed under the MIT License.
【10秒快速上手】
  1. 复制本文件到任意文件夹（支持中文路径）。
  2. 在同目录下创建 "templates" 文件夹，把按钮截图（PNG格式）放进去。
  3. 写一行代码：auto.click("你的按钮名称")
  4. 运行，完成。

【20260502更新】
  ★ 图像引擎升级：修复DPI缩放问题，100%/125%/150%缩放均正常匹配
  ★ 定时任务改用sched模块，不再轮询空耗CPU
  ★ 文件查找改用os.scandir，速度大幅提升
  ★ 剪贴板操作加入上下文管理器，更安全
"""

import sys
import os
import time
import datetime
import subprocess
import logging
import re
import json
import sched
from ctypes import Structure, c_ulong, windll, byref
from typing import List, Tuple, Union, Optional, Callable, Dict

# ---------- 自动安装缺失的依赖包 ----------
_required_packages = {
    'cv2': 'opencv-python',
    'numpy': 'numpy',
    'PIL': 'Pillow',
    'win32gui': 'pywin32',
    'win32api': 'pywin32',
    'win32con': 'pywin32',
    'win32clipboard': 'pywin32',
    'win32print': 'pywin32',
}

_missing = []
for _mod, _pkg in _required_packages.items():
    try:
        __import__(_mod)
    except ImportError:
        _missing.append(_pkg)

if _missing:
    print("=" * 60)
    print("首次运行：正在安装必需的依赖包，请稍候...")
    print(f"需要安装：{', '.join(set(_missing))}")
    print("=" * 60)
    for _pkg in set(_missing):
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", _pkg,
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"  ✓ {_pkg} 安装成功")
        except:
            print(f"  ✗ {_pkg} 安装失败，请手动运行: pip install {_pkg}")
    print("=" * 60)
    print("安装完成，正在启动...\n")

import cv2
import numpy as np
from PIL import Image, ImageGrab
import win32gui
import win32api
import win32con
import win32print
from win32.win32api import GetSystemMetrics
from win32clipboard import (
    GetClipboardData,
    OpenClipboard,
    CloseClipboard,
    EmptyClipboard,
    SetClipboardData,
)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    配置类 - 只需修改这里                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class Config:
    """所有用户可配置的参数。"""

    # ===== 路径设置 =====
    template_dir = "templates"
    log_dir = "logs"
    screenshot_dir = "screenshots"
    error_dir = "error_snapshots"

    # ===== 图像识别参数 =====
    default_similarity = 0.9
    dedup_radius = 5
    forced_image_format = ".png"

    # ===== 超时与重试 =====
    default_timeout = 10
    retry_interval = 0.2
    post_click_delay = 0.3

    # ===== 调试设置 =====
    verbose_log = True
    auto_screenshot_on_error = True

    # ===== 流程引擎设置 =====
    flow_default_retries = 0
    flow_default_retry_wait = 1


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                     自动初始化                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

_base_dir = os.path.dirname(os.path.abspath(__file__))
for _d in [Config.template_dir, Config.log_dir, Config.screenshot_dir, Config.error_dir]:
    _path = os.path.join(_base_dir, _d)
    if not os.path.exists(_path):
        os.makedirs(_path, exist_ok=True)

_log_level = logging.DEBUG if Config.verbose_log else logging.INFO
_log_fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_fmt)

_file_handler = logging.FileHandler(
    os.path.join(_base_dir, Config.log_dir, f"log_{time.strftime('%Y%m%d')}.log"),
    encoding='utf-8'
)
_file_handler.setLevel(_log_level)
_file_handler.setFormatter(_log_fmt)

logger = logging.getLogger('ClickClick')
logger.setLevel(_log_level)
logger.addHandler(_console_handler)
logger.addHandler(_file_handler)
logger.info("=" * 40)
logger.info("ClickClick 办公助手 启动")
logger.info(f"模板目录={Config.template_dir}, 相似度={Config.default_similarity}, 超时={Config.default_timeout}s")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    屏幕工具（DPI双重坐标体系）                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_real_resolution():
    """获取真实的物理分辨率（DPI缩放前）"""
    hDC = win32gui.GetDC(0)
    try:
        w = win32print.GetDeviceCaps(hDC, win32con.DESKTOPHORZRES)
        h = win32print.GetDeviceCaps(hDC, win32con.DESKTOPVERTRES)
    finally:
        win32gui.ReleaseDC(0, hDC)
    return w, h


def get_screen_size():
    """获取缩放后的逻辑分辨率"""
    return GetSystemMetrics(0), GetSystemMetrics(1)


def get_scale_factor():
    """计算DPI缩放系数（物理分辨率 / 逻辑分辨率）"""
    w_real, _ = get_real_resolution()
    w_logic, _ = get_screen_size()
    return w_real / w_logic if w_logic > 0 else 1.0


def logical_to_real(x, y, scale=None):
    """将逻辑坐标转换为真实（物理）坐标"""
    if scale is None:
        scale = get_scale_factor()
    return int(x * scale), int(y * scale)


def real_to_logical(x, y, scale=None):
    """将真实（物理）坐标转换为逻辑坐标"""
    if scale is None:
        scale = get_scale_factor()
    return int(x / scale), int(y / scale)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    鼠标操作                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class POINT(Structure):
    _fields_ = [("x", c_ulong), ("y", c_ulong)]


def get_mouse_point():
    """获取鼠标当前逻辑坐标"""
    time.sleep(0.05)
    po = POINT()
    windll.user32.GetCursorPos(byref(po))
    return int(po.x), int(po.y)


def mouse_moveto(x, y):
    """移动鼠标到逻辑坐标"""
    windll.user32.SetCursorPos(int(x), int(y))


def mouse_left_down():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)


def mouse_left_up():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def mouse_right_down():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)


def mouse_right_up():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def mouse_left_click(x=None, y=None, k=1):
    """在逻辑坐标处左键单击"""
    if x is not None and y is not None:
        mouse_moveto(int(x), int(y))
        time.sleep(0.05)
    for _ in range(int(k)):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def mouse_right_click(x=None, y=None):
    """在逻辑坐标处右键单击"""
    if x is not None and y is not None:
        mouse_moveto(int(x), int(y))
        time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def drag_mouse(x1, y1, x2, y2, duration=0.5):
    """平滑拖拽（逻辑坐标）"""
    mouse_moveto(int(x1), int(y1))
    time.sleep(0.1)
    mouse_left_down()
    time.sleep(0.1)
    for i in range(1, 11):
        cx = int(x1 + (x2 - x1) * i / 10)
        cy = int(y1 + (y2 - y1) * i / 10)
        mouse_moveto(cx, cy)
        time.sleep(duration / 10)
    mouse_left_up()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    键盘操作                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

VK_CODE = {
    'backspace': 0x08, 'tab': 0x09, 'clear': 0x0C, 'enter': 0x0D,
    'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12, 'pause': 0x13,
    'caps_lock': 0x14, 'esc': 0x1B, 'spacebar': 0x20,
    'page_up': 0x21, 'page_down': 0x22, 'end': 0x23, 'home': 0x24,
    'left_arrow': 0x25, 'up_arrow': 0x26, 'right_arrow': 0x27, 'down_arrow': 0x28,
    'select': 0x29, 'print': 0x2A, 'execute': 0x2B, 'print_screen': 0x2C,
    'ins': 0x2D, 'del': 0x2E, 'help': 0x2F,
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59, 'z': 0x5A,
    'numpad_0': 0x60, 'numpad_1': 0x61, 'numpad_2': 0x62, 'numpad_3': 0x63,
    'numpad_4': 0x64, 'numpad_5': 0x65, 'numpad_6': 0x66, 'numpad_7': 0x67,
    'numpad_8': 0x68, 'numpad_9': 0x69,
    'multiply_key': 0x6A, 'add_key': 0x6B, 'separator_key': 0x6C,
    'subtract_key': 0x6D, 'decimal_key': 0x6E, 'divide_key': 0x6F,
    'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74,
    'F6': 0x75, 'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79,
    'F11': 0x7A, 'F12': 0x7B,
    'num_lock': 0x90, 'scroll_lock': 0x91,
    'left_shift': 0xA0, 'right_shift': 0xA1,
    'left_control': 0xA2, 'right_control': 0xA3,
    'left_win': 0x5B, 'right_win': 0x5C,
    '+': 0xBB, ',': 0xBC, '-': 0xBD, '.': 0xBE, '/': 0xBF,
    '`': 0xC0, ';': 0xBA, '[': 0xDB, '\\': 0xDC, ']': 0xDD, "'": 0xDE,
}


def key_down(keys_str=''):
    """按下按键（不释放）"""
    for c in keys_str:
        vk = VK_CODE.get(c.lower())
        if vk is not None:
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.01)


def key_up(keys_str=''):
    """释放按键"""
    for c in keys_str:
        vk = VK_CODE.get(c.lower())
        if vk is not None:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)


def key_press(key_str='', k=1):
    """按下并释放指定键k次"""
    vk = VK_CODE.get(key_str.lower())
    if vk is None:
        return
    for _ in range(k):
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)


def key_press_plus(keys_list=[]):
    """按下组合键（按顺序全部按下，再反向全部释放）"""
    for item in keys_list:
        vk = VK_CODE.get(item.lower())
        if vk is not None:
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
    for item in reversed(keys_list):
        vk = VK_CODE.get(item.lower())
        if vk is not None:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    剪贴板操作（升级：上下文管理器）                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _Clipboard:
    """剪贴板上下文管理器"""

    def __enter__(self):
        OpenClipboard()
        return self

    def __exit__(self, *args):
        CloseClipboard()

    def get_text(self, encoding='gbk'):
        try:
            return GetClipboardData(win32con.CF_TEXT).decode(encoding, errors='ignore')
        except:
            return ""

    def set_text(self, text):
        EmptyClipboard()
        SetClipboardData(win32con.CF_UNICODETEXT, str(text))


def _get_clipboard_text():
    with _Clipboard() as cb:
        return cb.get_text()


def _set_clipboard_text(text):
    with _Clipboard() as cb:
        cb.set_text(text)


def saystring(string, k=1):
    """通过剪贴板粘贴文本（支持中文）"""
    time.sleep(0.1)
    _set_clipboard_text(str(string))
    time.sleep(0.1)
    for _ in range(k):
        key_press_plus(['ctrl', 'v'])
        time.sleep(0.05)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               图像识别引擎（升级：DPI双重坐标体系）                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _ImageEngine:
    """
    图像识别引擎 v2.0 - DPI缩放修复版

    核心改进：
    - 图像匹配在物理坐标系中进行（不受缩放影响）
    - 返回物理坐标，点击时自动转换为逻辑坐标
    - 支持模板缓存，加速重复查找
    """

    def __init__(self):
        self.path = os.path.join(_base_dir, Config.template_dir)
        self.imgstyle = Config.forced_image_format
        self.threshold = Config.default_similarity
        self.dedup_radius = Config.dedup_radius
        self.real_w, self.real_h = get_real_resolution()
        self.logic_w, self.logic_h = get_screen_size()
        self.scale = get_scale_factor()
        self.search_area_real = (0, 0, self.real_w, self.real_h)
        self.tempsize = (0, 0)
        self.zuobiao = []
        # 截图缓存
        self._cached_screenshot = None
        self._cached_screenshot_time = 0
        self._cache_duration = 0.1

    def _load_template(self, tempname):
        """加载模板图片（支持中文路径）"""
        template_file = os.path.join(self.path, tempname + self.imgstyle)
        if not os.path.exists(template_file):
            alternatives = ['.png', '.PNG', '.jpg', '.jpeg', '.bmp']
            for fmt in alternatives:
                alt_file = os.path.join(self.path, tempname + fmt)
                if os.path.exists(alt_file):
                    template_file = alt_file
                    break
            else:
                raise FileNotFoundError(
                    f"找不到模板图片 '{tempname}{self.imgstyle}'\n"
                    f"搜索路径: {self.path}"
                )
        img_array = np.fromfile(template_file, dtype=np.uint8)
        template = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if template is None:
            raise ValueError(f"模板图片读取失败: {template_file}")
        return template

    def _grab_screen(self, area_real=None):
        """
        截取屏幕指定区域（返回物理分辨率图像）
        area_real: (left, top, width, height) 物理坐标
        """
        now = time.time()
        if (self._cached_screenshot is not None and
                now - self._cached_screenshot_time < self._cache_duration and
                area_real is None):
            return self._cached_screenshot

        if area_real is None:
            area_real = (0, 0, self.real_w, self.real_h)

        left_real, top_real, width_real, height_real = area_real
        # ImageGrab.grab 使用逻辑坐标
        logic_left, logic_top = real_to_logical(left_real, top_real, self.scale)
        logic_right = real_to_logical(left_real + width_real, top_real, self.scale)[0]
        logic_bottom = real_to_logical(left_real, top_real + height_real, self.scale)[1]

        img_pil = ImageGrab.grab((logic_left, logic_top, logic_right, logic_bottom))
        img_np = np.asarray(img_pil)

        if area_real is None:
            self._cached_screenshot = img_np
            self._cached_screenshot_time = now

        return img_np

    def _non_max_suppression(self, points):
        """去重：合并相邻匹配点"""
        if not points:
            return []
        merged = []
        for pt in points:
            conflict = False
            for m in merged:
                if (abs(pt[0] - m[0]) <= self.dedup_radius and
                        abs(pt[1] - m[1]) <= self.dedup_radius):
                    conflict = True
                    break
            if not conflict:
                merged.append(pt)
        return merged

    def find_img(self, tempname, area_real=None, threshold=None):
        """
        灰度匹配 - 在物理坐标系中进行
        返回物理坐标列表
        """
        if area_real is None:
            area_real = self.search_area_real
        if threshold is None:
            threshold = self.threshold

        screen = self._grab_screen(area_real)
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_RGB2GRAY)

        temp = self._load_template(tempname)
        temp_gray = cv2.cvtColor(temp, cv2.COLOR_BGR2GRAY)

        self.tempsize = temp_gray.shape[1], temp_gray.shape[0]

        result = cv2.matchTemplate(screen_gray, temp_gray, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= threshold)

        points = []
        for pt in zip(*loc[::-1]):
            # pt 是截图内的相对坐标，转换为物理屏幕坐标
            x = int(pt[0] + area_real[0])
            y = int(pt[1] + area_real[1])
            points.append((x, y))

        self.zuobiao = self._non_max_suppression(points)
        return self.zuobiao

    def find_img_colorful(self, tempname, area_real=None, threshold=None):
        """彩色匹配 - 物理坐标系"""
        if area_real is None:
            area_real = self.search_area_real
        if threshold is None:
            threshold = self.threshold

        screen = self._grab_screen(area_real)
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

        temp = self._load_template(tempname)
        self.tempsize = temp.shape[1], temp.shape[0]

        result = cv2.matchTemplate(screen_bgr, temp, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= threshold)

        points = []
        for pt in zip(*loc[::-1]):
            x = int(pt[0] + area_real[0])
            y = int(pt[1] + area_real[1])
            points.append((x, y))

        self.zuobiao = self._non_max_suppression(points)
        return self.zuobiao

    def find_best(self, tempname, timeout=None, area_real=None, threshold=None):
        """优先灰度匹配，失败则彩色匹配，返回物理坐标"""
        timeout = timeout or Config.default_timeout
        threshold = threshold or self.threshold

        start_time = time.time()
        while time.time() - start_time < timeout:
            coords = self.find_img(tempname, area_real, threshold)
            if coords:
                return coords[0]

            coords = self.find_img_colorful(tempname, area_real, threshold)
            if coords:
                return coords[0]

            time.sleep(Config.retry_interval)

        logger.warning(f"匹配失败: {tempname}，阈值={threshold}，超时={timeout}s")
        return -1, -1

    def find_all(self, tempname, timeout=None, area_real=None, threshold=None):
        """查找所有匹配目标"""
        timeout = timeout or Config.default_timeout
        threshold = threshold or self.threshold

        start_time = time.time()
        while time.time() - start_time < timeout:
            coords = self.find_img(tempname, area_real, threshold)
            if coords:
                return coords
            coords = self.find_img_colorful(tempname, area_real, threshold)
            if coords:
                return coords
            time.sleep(Config.retry_interval)

        return []

    def click_by_img(self, tempname, timeout=None):
        """
        找图并点击中心（自动转换物理→逻辑坐标）
        """
        timeout = timeout or Config.default_timeout
        max_attempts = max(int(timeout * 5), 25)

        for _ in range(max_attempts):
            result = self.find_best(tempname, timeout=1)
            if result != (-1, -1):
                real_x, real_y = result
                # 计算中心点（物理坐标）
                center_real_x = real_x + self.tempsize[0] // 2
                center_real_y = real_y + self.tempsize[1] // 2
                # 转换为逻辑坐标点击
                logic_x, logic_y = real_to_logical(center_real_x, center_real_y, self.scale)
                mouse_left_click(logic_x, logic_y)
                return True
            time.sleep(0.2)

        logger.warning(f"点击失败: {tempname}，超时={timeout}s")
        return False

    def find_one_logical(self, tempname, timeout=None):
        """查找并返回逻辑坐标（供 auto.find 使用）"""
        result = self.find_best(tempname, timeout)
        if result != (-1, -1):
            return real_to_logical(result[0], result[1], self.scale)
        return -1, -1


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    定位融合层                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _LocatorFusion:
    """定位融合层"""

    def __init__(self):
        self.image_engine = _ImageEngine()

    def find(self, tempname, timeout=None, area=None, threshold=None):
        """查找目标，返回逻辑坐标 (x, y) 或 (-1, -1)"""
        # 如果传入了area（逻辑坐标），转换为物理坐标
        area_real = None
        if area is not None:
            left, top, width, height = area
            left_real, top_real = logical_to_real(left, top)
            width_real = int(width * self.image_engine.scale)
            height_real = int(height * self.image_engine.scale)
            area_real = (left_real, top_real, width_real, height_real)
        return self.image_engine.find_one_logical(tempname, timeout)

    def find_all(self, tempname, timeout=None, area=None, threshold=None):
        """查找所有目标，返回逻辑坐标列表"""
        area_real = None
        if area is not None:
            left, top, width, height = area
            left_real, top_real = logical_to_real(left, top)
            width_real = int(width * self.image_engine.scale)
            height_real = int(height * self.image_engine.scale)
            area_real = (left_real, top_real, width_real, height_real)

        real_coords = self.image_engine.find_all(tempname, timeout, area_real, threshold)
        return [real_to_logical(x, y, self.image_engine.scale) for x, y in real_coords]

    def click(self, tempname, timeout=None):
        return self.image_engine.click_by_img(tempname, timeout)

    def get_template_size(self):
        return self.image_engine.tempsize

    def get_scale_factor(self):
        return self.image_engine.scale


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    操作追踪器                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _StepRecorder:
    """操作追踪器"""

    def __init__(self):
        self.enabled = False
        self.steps = []
        self.flow_name = "未命名流程"
        self.start_time = None

    def on(self):
        self.enabled = True
        self.steps = []
        self.start_time = time.time()
        logger.info("操作追踪已开启")

    def off(self):
        self.enabled = False
        logger.info("操作追踪已关闭")

    def record(self, action, target, result, duration):
        if not self.enabled:
            return
        step = {
            'step': len(self.steps) + 1,
            'action': action,
            'target': str(target),
            'result': 'success' if result else 'failed',
            'timestamp': time.strftime('%H:%M:%S'),
            'duration': round(duration, 3),
        }
        self.steps.append(step)

    def generate_report(self):
        if not self.steps:
            print("没有可报告的执行记录。")
            return None

        total = len(self.steps)
        success = sum(1 for s in self.steps if s['result'] == 'success')
        failed = sum(1 for s in self.steps if s['result'] == 'failed')
        total_duration = sum(s['duration'] for s in self.steps)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>执行报告 - {self.flow_name}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary {{ display: flex; gap: 20px; }}
        .summary-card {{ flex: 1; background: #fff; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-card .number {{ font-size: 36px; font-weight: bold; }}
        .success {{ color: #4CAF50; }}
        .failed {{ color: #f44336; }}
        .steps {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .step {{ border-left: 3px solid #ddd; padding: 10px 15px; margin: 10px 0; }}
        .step.success {{ border-left-color: #4CAF50; }}
        .step.failed {{ border-left-color: #f44336; background: #fff5f5; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>执行报告</h1>
        <p>流程名称: {self.flow_name}</p>
        <p>总耗时: {total_duration:.2f}秒</p>
    </div>
    <div class="summary">
        <div class="summary-card"><div>总步骤</div><div class="number">{total}</div></div>
        <div class="summary-card"><div class="success">成功</div><div class="number success">{success}</div></div>
        <div class="summary-card"><div class="failed">失败</div><div class="number failed">{failed}</div></div>
    </div>
    <div class="steps"><h2>步骤详情</h2>"""
        for step in self.steps:
            sc = 'success' if step['result'] == 'success' else 'failed'
            icon = '✓' if step['result'] == 'success' else '✗'
            html += f"""<div class="step {sc}"><span>#{step['step']} {step['action']}({step['target']}) {icon} {step['duration']}s</span></div>"""
        html += "</div></body></html>"

        report_path = os.path.join(_base_dir, Config.log_dir, f"report_{time.strftime('%Y%m%d_%H%M%S')}.html")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"执行报告已保存: {report_path}")
        print(f"执行报告已保存: {report_path}")
        print(f"总步骤: {total} | 成功: {success} | 失败: {failed} | 总耗时: {total_duration:.2f}s")
        return report_path


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    错误处理器                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _ErrorHandler:
    """错误处理"""

    @staticmethod
    def save_error_screenshot(template_name):
        try:
            path = os.path.join(_base_dir, Config.error_dir,
                                f"not_found_{template_name}_{time.strftime('%H%M%S')}.png")
            ImageGrab.grab().save(path)
            logger.info(f"错误截图已保存: {path}")
            return path
        except:
            return None

    @staticmethod
    def format_error_message(template_name, similarity, timeout):
        return (
            f"✗ 未能在屏幕上找到 '{template_name}'\n"
            f"  相似度阈值: {similarity}\n"
            f"  超时时间: {timeout}秒\n"
            f"  可能原因:\n"
            f"   1. 按钮尚未出现\n"
            f"   2. 按钮外观已变化（需重新截图）\n"
            f"   3. 模板截图是JPG格式（必须用PNG）"
        )


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    环境检测器                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _EnvChecker:
    """环境诊断"""

    @staticmethod
    def check():
        print("\n" + "=" * 60)
        print("环境诊断")
        print("=" * 60)

        print(f"\n脚本目录: {_base_dir}")
        print(f"Python版本: {sys.version}")

        real_w, real_h = get_real_resolution()
        logic_w, logic_h = get_screen_size()
        scale = get_scale_factor()
        print(f"\n屏幕分辨率:")
        print(f"  物理分辨率: {real_w}x{real_h}")
        print(f"  逻辑分辨率: {logic_w}x{logic_h}")
        print(f"  缩放系数: {scale:.2f} ({int(scale*100)}%)")
        if scale != 1.0:
            print(f"  缩放不是100%，v4.0已自动补偿")

        template_path = os.path.join(_base_dir, Config.template_dir)
        print(f"\n模板目录: {template_path}")
        if os.path.exists(template_path):
            png_files = [f for f in os.listdir(template_path) if f.lower().endswith('.png')]
            non_png = [f for f in os.listdir(template_path)
                       if f.lower().endswith(('.jpg', '.jpeg', '.bmp'))]
            print(f"  模板总数: {len(png_files) + len(non_png)}")
            print(f"  PNG格式: {len(png_files)}")
            if non_png:
                print(f"  非PNG格式: {len(non_png)}个 {non_png}")

        print(f"\n核心依赖:")
        for mod_name in ['cv2', 'numpy', 'PIL', 'win32gui', 'win32clipboard']:
            try:
                __import__(mod_name)
                print(f"  {mod_name}: OK")
            except ImportError:
                print(f"  {mod_name}: 缺失")

        print("\n" + "=" * 60)

    @staticmethod
    def check_templates():
        template_path = os.path.join(_base_dir, Config.template_dir)
        if not os.path.exists(template_path):
            print(f"模板目录 '{Config.template_dir}' 不存在")
            return

        engine = _ImageEngine()
        png_files = [f for f in os.listdir(template_path) if f.lower().endswith('.png')]

        print(f"\n模板健康检查 - 共 {len(png_files)} 个模板")
        print("-" * 50)

        ok_count = 0
        for f in png_files:
            name = f[:-4]
            result = engine.find_best(name, timeout=1)
            if result != (-1, -1):
                print(f"  OK {name}")
                ok_count += 1
            else:
                print(f"  未找到 {name}")

        print("-" * 50)
        print(f"当前可见: {ok_count}/{len(png_files)}")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    流程引擎                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class Flow:
    """流程引擎"""

    def __init__(self, locator, recorder, error_handler):
        self.locator = locator
        self.recorder = recorder
        self.error_handler = error_handler
        self.steps = []
        self._current_if_stack = []
        self._retry_count = 0
        self._retry_wait = 0
        self._step_mode = False
        self._step_pace = 0
        self._data_context = {}
        self._loop_data = None

    def click(self, target, **kwargs):
        self.steps.append(('click', target, kwargs))
        return self

    def dclick(self, target, **kwargs):
        self.steps.append(('dclick', target, kwargs))
        return self

    def rclick(self, target, **kwargs):
        self.steps.append(('rclick', target, kwargs))
        return self

    def write(self, text):
        self.steps.append(('write', text, {}))
        return self

    def press(self, key, times=1):
        self.steps.append(('press', key, {'times': times}))
        return self

    def hotkey(self, *keys):
        self.steps.append(('hotkey', keys, {}))
        return self

    def wait(self, target, timeout=None):
        self.steps.append(('wait', target, {'timeout': timeout}))
        return self

    def wait_not(self, target, timeout=None):
        self.steps.append(('wait_not', target, {'timeout': timeout}))
        return self

    def pause(self, seconds):
        self.steps.append(('pause', seconds, {}))
        return self

    def if_see(self, target, **kwargs):
        self.steps.append(('if_start', target, kwargs))
        self._current_if_stack.append('if')
        return self

    def if_not_see(self, target, **kwargs):
        self.steps.append(('if_not_start', target, kwargs))
        self._current_if_stack.append('if_not')
        return self

    def else_do(self):
        self.steps.append(('else', None, {}))
        return self

    def endif(self):
        self.steps.append(('endif', None, {}))
        if self._current_if_stack:
            self._current_if_stack.pop()
        return self

    def retry(self, count, wait=1):
        self._retry_count = count
        self._retry_wait = wait
        return self

    def for_data(self, data_list):
        self._loop_data = data_list
        self.steps.append(('for_start', None, {}))
        return self

    def end_for(self):
        self.steps.append(('for_end', None, {}))
        return self

    def run(self):
        max_attempts = self._retry_count + 1
        last_error = None

        for attempt in range(max_attempts):
            if attempt > 0:
                logger.info(f"重试第 {attempt}/{self._retry_count} 次...")
                print(f"重试第 {attempt}/{self._retry_count} 次...")
                time.sleep(self._retry_wait)
            try:
                if self._execute_steps(self.steps):
                    return True
            except Exception as e:
                last_error = e
                logger.error(f"流程异常: {e}")

        if last_error:
            logger.error(f"最终错误: {last_error}")
        return False

    def _execute_steps(self, steps):
        i = 0
        while i < len(steps):
            action, target, kwargs = steps[i]
            if self._step_mode:
                input(f"[单步] 即将执行: {action}({target})，按回车继续...")

            if action in ('if_start', 'if_not_start', 'else', 'endif'):
                skip_to = self._handle_conditional(steps, i)
                if skip_to is not None:
                    i = skip_to
                    continue
            elif action == 'for_start':
                i = self._execute_loop(steps, i)
                continue
            elif action == 'for_end':
                i += 1
            else:
                result = self._execute_single(action, target, kwargs)
                if not result:
                    return False
                i += 1

            if self._step_pace > 0:
                time.sleep(self._step_pace)
        return True

    def _handle_conditional(self, steps, start_idx):
        action, target, kwargs = steps[start_idx]
        if action == 'if_start':
            if self._check_condition(target, kwargs):
                return None
            else:
                return self._skip_to_next_branch(steps, start_idx)
        elif action == 'if_not_start':
            if not self._check_condition(target, kwargs):
                return None
            else:
                return self._skip_to_next_branch(steps, start_idx)
        elif action == 'else':
            return None
        elif action == 'endif':
            return None

    def _skip_to_next_branch(self, steps, start_idx):
        depth = 0
        for i in range(start_idx + 1, len(steps)):
            action = steps[i][0]
            if action in ('if_start', 'if_not_start'):
                depth += 1
            elif action == 'endif':
                if depth == 0:
                    return i + 1
                depth -= 1
            elif action == 'else' and depth == 0:
                return i + 1
        return len(steps)

    def _check_condition(self, target, kwargs):
        if target is None:
            return False
        result = self.locator.find(target, timeout=1, **kwargs)
        return result != (-1, -1)

    def _execute_loop(self, steps, start_idx):
        """执行循环体"""
        loop_end = self._find_loop_end(steps, start_idx)
        if loop_end is None:
            logger.error("未找到循环结束标记 end_for()")
            return len(steps)

        if not self._loop_data:
            logger.warning("循环数据为空，跳过循环体")
            return loop_end + 1

        for idx, item in enumerate(self._loop_data):
            self._data_context['item'] = item
            self._data_context['index'] = idx
            logger.info(f"循环 {idx+1}/{len(self._loop_data)}: {item}")

            # 逐条执行循环体内的步骤，保持记录顺序
            i = start_idx + 1
            while i < loop_end:
                action, target, kwargs = steps[i]

                if action in ('if_start', 'if_not_start', 'else', 'endif'):
                    skip_to = self._handle_conditional(steps, i)
                    if skip_to is not None:
                        i = skip_to
                        continue

                # 替换占位符
                new_target = target
                if isinstance(target, str):
                    new_target = target.replace('{item}', str(item))
                    new_target = new_target.replace('{index}', str(idx))

                result = self._execute_single(action, new_target, kwargs)
                if not result:
                    logger.error(f"循环第{idx+1}次执行失败: {action}({target})")
                    return loop_end + 1

                if self._step_pace > 0:
                    time.sleep(self._step_pace)

                i += 1

        return loop_end + 1

    def _find_loop_end(self, steps, start_idx):
        depth = 0
        for i in range(start_idx + 1, len(steps)):
            if steps[i][0] == 'for_start':
                depth += 1
            elif steps[i][0] == 'for_end':
                if depth == 0:
                    return i
                depth -= 1
        return None

    def _resolve_placeholders(self, steps):
        resolved = []
        for step in steps:
            action, target, kwargs = step
            new_target = target
            if isinstance(target, str):
                new_target = target.replace('{item}', str(self._data_context.get('item', '')))
                new_target = new_target.replace('{index}', str(self._data_context.get('index', '')))
            resolved.append((action, new_target, kwargs))
        return resolved

    def _execute_single(self, action, target, kwargs):
        start_time = time.time()
        result = True

        try:
            if action == 'click':
                if isinstance(target, str):
                    result = self.locator.click(target)
                elif isinstance(target, (int, float)):
                    mouse_left_click(int(target), int(kwargs.get('y', 0)))
                else:
                    x, y = get_mouse_point()
                    mouse_left_click(x, y)
            elif action == 'dclick':
                if isinstance(target, str):
                    coords = self.locator.find(target)
                    if coords != (-1, -1):
                        mouse_left_click(int(coords[0]), int(coords[1]), k=2)
                    else:
                        result = False
                else:
                    mouse_left_click(int(target), int(kwargs.get('y', 0)), k=2)
            elif action == 'rclick':
                if isinstance(target, str):
                    coords = self.locator.find(target)
                    if coords != (-1, -1):
                        mouse_right_click(int(coords[0]), int(coords[1]))
                    else:
                        result = False
                else:
                    mouse_right_click(int(target), int(kwargs.get('y', 0)))
            elif action == 'write':
                saystring(str(target))
            elif action == 'press':
                times = kwargs.get('times', 1)
                key_press(str(target), k=times)
            elif action == 'hotkey':
                key_press_plus(list(target))
            elif action == 'wait':
                timeout = kwargs.get('timeout') or Config.default_timeout
                result = self.locator.find(target, timeout=timeout) != (-1, -1)
            elif action == 'wait_not':
                timeout = kwargs.get('timeout') or Config.default_timeout
                start = time.time()
                while time.time() - start < timeout:
                    if self.locator.find(target, timeout=1) == (-1, -1):
                        result = True
                        break
                    time.sleep(0.5)
                else:
                    result = False
            elif action == 'pause':
                time.sleep(float(target))
        except Exception as e:
            logger.error(f"操作异常: {action}({target}) - {e}")
            result = False

        duration = time.time() - start_time
        self.recorder.record(action, target, result, duration)

        if not result and action not in ('wait', 'wait_not', 'pause'):
            print(self.error_handler.format_error_message(target, Config.default_similarity, Config.default_timeout))

        return result


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    文件查找（升级：os.scandir）                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def find_files(file_path=r'D:\企划部工作\02 对外报送', keyword='普惠，doc，2022'):
    """按关键字查找文件夹和文件（使用os.scandir加速）"""
    file_keywords = re.split(r'[.,。,，,\,]', keyword)
    file_keywords = [k.strip() for k in file_keywords if k.strip()]

    matched_folders = []
    matched_files = []

    def scan(dirpath):
        with os.scandir(dirpath) as it:
            dirs = []
            files = []
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry.name)
                elif entry.is_file():
                    files.append(entry.name)

            # 检查文件夹
            if all(k in dirpath for k in file_keywords):
                matched_folders.append(dirpath)

            # 检查文件
            for fname in files:
                full = os.path.join(dirpath, fname)
                if all(k in full for k in file_keywords):
                    matched_files.append(full)

            for d in dirs:
                scan(os.path.join(dirpath, d))

    scan(file_path)
    print(f'找到文件夹 {len(matched_folders)} 个')
    print(f'找到文件 {len(matched_files)} 个')
    return matched_folders, matched_files


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    定时任务（升级：sched模块）                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

_scheduler = sched.scheduler(time.time, time.sleep)


def _cron_wrapper(task, run_once, target_int):
    """定时任务包装器"""
    logger.info(f"定时任务执行: {time.strftime('%H:%M:%S')}")
    try:
        task()
    except Exception as e:
        logger.error(f"定时任务异常: {e}")
    if not run_once:
        # 安排下一次（60秒后）
        _scheduler.enter(60, 1, _cron_wrapper, (task, run_once, target_int))


def _calc_delay(target, now):
    """计算从 now 到 target 的秒数（支持跨天）"""
    target_h = target // 10000
    target_m = (target % 10000) // 100
    target_s = target % 100
    now_h = now // 10000
    now_m = (now % 10000) // 100
    now_s = now % 100

    target_seconds = target_h * 3600 + target_m * 60 + target_s
    now_seconds = now_h * 3600 + now_m * 60 + now_s

    if target_seconds > now_seconds:
        return target_seconds - now_seconds
    else:
        return 86400 - now_seconds + target_seconds


def timer_task(timer, task):
    """每天定时执行（非阻塞，使用sched）"""
    target = int(timer)
    now = int(time.strftime("%H%M%S"))
    delay = _calc_delay(target, now)

    logger.info(f"定时任务将在 {delay} 秒后启动")
    _scheduler.enter(delay, 1, _cron_wrapper, (task, False, target))


def timer_task_once(timer, task):
    """一次性定时执行"""
    target = int(timer)
    now = int(time.strftime("%H%M%S"))
    delay = _calc_delay(target, now)

    logger.info(f"一次性定时任务将在 {delay} 秒后启动")
    _scheduler.enter(delay, 1, _cron_wrapper, (task, True, target))


def timer_tasks(**kwargs):
    """多个定时任务"""
    for t_str, task in kwargs.items():
        timer_task(t_str, task)

    # 启动调度器（阻塞）
    _scheduler.run()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    日期工具                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def first_last_day(year=2026):
    """获取某年各月的首日和末日（2月到次年1月，共12个月）"""
    result = []
    for i in range(2, 14):
        if i <= 12:
            month = i
            year_str = str(year)
        else:
            month = 1
            year_str = str(year + 1)
        first = f"{year_str}-{month:02d}-01"
        if month == 12:
            next_first = f"{year+1}-01-01"
        else:
            next_first = f"{year_str}-{month+1:02d}-01"
        last = (datetime.datetime.strptime(next_first, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        result.append([first, last])
    return result

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    调试工具类                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _DebugTools:
    """调试工具"""

    def __init__(self, recorder):
        self.recorder = recorder

    def on(self):
        self.recorder.on()

    def off(self):
        self.recorder.off()

    def report(self):
        return self.recorder.generate_report()

    def replay(self):
        if not self.recorder.steps:
            print("没有可回放的记录。")
            return
        print(f"\n执行回放 - {self.recorder.flow_name}")
        print("-" * 50)
        for step in self.recorder.steps:
            icon = 'OK' if step['result'] == 'success' else 'FAIL'
            print(f"  {icon} 步骤{step['step']}: {step['action']}({step['target']}) - {step['duration']}s")
        print("-" * 50)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    截图工具                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def capture_template_simple(name):
    """截图工具：全屏截图并提示裁剪"""
    print(f"\n截图工具 - 模板名称: {name}")
    print("操作步骤:")
    print("  1. 确保目标按钮在屏幕上可见")
    print("  2. 按回车完成全屏截图")
    print("  3. 用画图工具裁剪到只保留按钮区域")
    input("\n按回车截图...")

    try:
        save_path = os.path.join(_base_dir, Config.template_dir, f"{name}.png")
        screenshot = ImageGrab.grab()
        screenshot.save(save_path)
        print(f"\n截图已保存: {save_path}")
        print("请用画图工具裁剪后覆盖该文件")
        return save_path
    except Exception as e:
        logger.error(f"截图失败: {e}")
        return None


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    主用户接口类 _Auto                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _Auto:
    """ClickClick 办公助手"""

    def __init__(self):
        self._locator = _LocatorFusion()
        self._recorder = _StepRecorder()
        self._error_handler = _ErrorHandler()
        self._env_checker = _EnvChecker()
        self.debug = _DebugTools(self._recorder)
        self._step_mode = False
        self._step_pace = 0

    # ===== 屏幕截图 =====
    def shot(self, filename="screenshot"):
        path = os.path.join(_base_dir, Config.screenshot_dir, f"{filename}_{time.strftime('%H%M%S')}.png")
        ImageGrab.grab().save(path)
        logger.info(f"截图已保存: {path}")
        print(f"截图已保存: {path}")
        return path

    def snip(self, x, y, w, h, filename="region"):
        path = os.path.join(_base_dir, Config.screenshot_dir, f"{filename}_{time.strftime('%H%M%S')}.png")
        ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h))).save(path)
        logger.info(f"区域截图已保存: {path}")
        print(f"区域截图已保存: {path}")
        return path

    # ===== 鼠标操作 =====
    def move(self, x, y):
        mouse_moveto(int(x), int(y))

    def click(self, *args):
        if not args:
            x, y = get_mouse_point()
            mouse_left_click(x, y)
        elif len(args) == 1 and isinstance(args[0], str):
            self._click_by_image(args[0])
        elif len(args) >= 2:
            mouse_left_click(int(args[0]), int(args[1]))

    def dclick(self, *args):
        if not args:
            x, y = get_mouse_point()
            mouse_left_click(x, y, k=2)
        elif len(args) == 1 and isinstance(args[0], str):
            self._click_by_image(args[0], clicks=2)
        elif len(args) >= 2:
            mouse_left_click(int(args[0]), int(args[1]), k=2)

    def rclick(self, *args):
        if not args:
            x, y = get_mouse_point()
            mouse_right_click(x, y)
        elif len(args) == 1 and isinstance(args[0], str):
            self._click_by_image(args[0], right_click=True)
        elif len(args) >= 2:
            mouse_right_click(int(args[0]), int(args[1]))

    def drag(self, x1, y1, x2, y2):
        drag_mouse(int(x1), int(y1), int(x2), int(y2))

    def pos(self):
        print("显示鼠标坐标（按Ctrl+C停止）...")
        try:
            while True:
                x, y = get_mouse_point()
                scale = get_scale_factor()
                print(f"\r鼠标坐标: ({x:>5}, {y:>5})  缩放: {scale:.2f}  ", end="")
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n已停止。")

    def _click_by_image(self, tempname, clicks=1, right_click=False):
        start_time = time.time()
        coords = self._locator.find(tempname)

        if coords == (-1, -1):
            self._error_handler.save_error_screenshot(tempname)
            print(self._error_handler.format_error_message(tempname, Config.default_similarity, Config.default_timeout))
            self._recorder.record('click', tempname, False, time.time() - start_time)
            return False

        cx, cy = int(coords[0]), int(coords[1])

        if right_click:
            mouse_right_click(cx, cy)
            action = 'rclick'
        else:
            mouse_left_click(cx, cy, k=clicks)
            action = 'dclick' if clicks > 1 else 'click'

        time.sleep(Config.post_click_delay)
        self._recorder.record(action, tempname, True, time.time() - start_time)
        logger.info(f"{action} '{tempname}' at ({cx},{cy})")
        return True

    # ===== 键盘操作 =====
    def write(self, text, times=1):
        saystring(str(text), k=times)

    def press(self, key_name, times=1):
        key_press(str(key_name), k=times)

    def hotkey(self, *keys):
        key_press_plus([str(k).lower() for k in keys])

    def press_sequence(self, *keys):
        for k in keys:
            key_press(str(k))
            time.sleep(0.05)

    # ===== 图像识别 =====
    def find(self, tempname, timeout=None, similarity=None, rect=None):
        return self._locator.find(tempname, timeout=timeout, area=rect)

    def find_all(self, tempname, timeout=None, similarity=None, rect=None):
        """查找所有匹配目标，返回逻辑坐标列表 [(x, y), ...]"""
        return self._locator.find_all(tempname, timeout=timeout, area=rect)
 
    def wait(self, tempname, timeout=30):
        logger.info(f"等待 '{tempname}' 出现（超时={timeout}s）...")
        print(f"等待 '{tempname}' 出现...")
        result = self._locator.find(tempname, timeout=timeout)
        if result != (-1, -1):
            print(f"'{tempname}' 已出现")
            return True
        else:
            print(f"超时: '{tempname}' 未出现")
            return False

    def wait_not(self, tempname, timeout=30):
        logger.info(f"等待 '{tempname}' 消失（超时={timeout}s）...")
        print(f"等待 '{tempname}' 消失...")
        start = time.time()
        while time.time() - start < timeout:
            if self._locator.find(tempname, timeout=1) == (-1, -1):
                print(f"'{tempname}' 已消失")
                return True
            time.sleep(0.5)
        print(f"超时: '{tempname}' 未消失")
        return False

    # ===== 定时任务 =====
    def cron(self, time_str, task_func):
        t = time_str.replace(':', '')
        logger.info(f"已设置每日定时任务: {time_str}")
        timer_task(t, task_func)

    def cron1(self, time_str, task_func):
        t = time_str.replace(':', '')
        logger.info(f"已设置一次性定时任务: {time_str}")
        timer_task_once(t, task_func)

    # ===== 流程引擎 =====
    def do(self):
        flow = Flow(self._locator, self._recorder, self._error_handler)
        flow._step_mode = self._step_mode
        flow._step_pace = self._step_pace
        return flow

    # ===== 调试 =====
    def step(self):
        self._step_mode = not self._step_mode
        print("单步模式已开启" if self._step_mode else "单步模式已关闭")

    def pace(self, seconds):
        self._step_pace = float(seconds)
        print(f"步骤间隔已设置为 {seconds} 秒")

    # ===== 环境诊断 =====
    def check(self):
        self._env_checker.check()

    def check_templates(self):
        self._env_checker.check_templates()

    # ===== 截图工具 =====
    def capture(self, name):
        return capture_template_simple(name)

    # ===== 帮助 =====
    def help(self):
        print(__doc__)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    创建全局实例                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

auto = _Auto()
auto.version = "4.0.0"

# 导出别名
search = find_files
monthends = first_last_day

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    运行入口                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    auto.help()
    print("\n" + "=" * 60)
    print("v4.0 更新：DPI修复 | 剔除MS Office | 定时任务升级")
    print("=" * 60)
    print("\n助手已就绪。")


    '''╔══════════════════════════════════════════════════════════════════════╗
║              ClickClick 办公助手 — 完整使用手册                      ║
║                  DPI已修复 · 纯文本 · 即查即用                        ║
╚══════════════════════════════════════════════════════════════════════╝

【目录】
  一、快速上手
  二、配置与参数
  三、API速查表
    3.1 鼠标操作
    3.2 键盘操作
    3.3 图像识别
    3.4 等待操作
    3.5 流程引擎（链式调用）
    3.6 调试工具
    3.7 环境诊断
    3.8 截图工具
    3.9 定时任务
    3.10 文件查找
    3.11 日期工具
  四、经典实战案例

═══════════════════════════════════════════════════════════════════════
一、快速上手
═══════════════════════════════════════════════════════════════════════

【文件结构】
  你的工作目录/
  ├── clickclick.py    ← 主脚本文件
  ├── templates/       ← 按钮截图文件夹（放PNG图片）
  ├── logs/            ← 运行日志（自动生成）
  ├── screenshots/     ← 用户截图（自动生成）
  └── error_snapshots/ ← 失败截图（自动生成）

【三步开始】
  步骤1：把脚本放到任意文件夹
  步骤2：在同目录创建 templates 文件夹，放入按钮PNG截图
  步骤3：写一行代码运行

  from clickclick import auto
  auto.click("按钮名称")   # 找图并点击，就这么简单

【重要提醒】
  ★ 截图必须用 PNG 格式！JPG 会造成像素偏移！
  ★ v4.0 已修复 DPI 缩放问题，100%/125%/150% 均可正常使用
  ★ 模板只截按钮本体，越小越独特越好

═══════════════════════════════════════════════════════════════════════
二、配置与参数
═══════════════════════════════════════════════════════════════════════

脚本内有一个 Config 类，集中管理所有可调参数：

  Config.template_dir = "templates"        # 模板截图存放文件夹
  Config.log_dir = "logs"                  # 日志存放文件夹
  Config.screenshot_dir = "screenshots"    # 截图存放文件夹
  Config.error_dir = "error_snapshots"     # 失败截图存放文件夹
  Config.default_similarity = 0.9         # 图像匹配相似度（0~1，越高越严格）
  Config.default_timeout = 10             # 找图默认超时（秒）
  Config.retry_interval = 0.2             # 找图失败重试间隔（秒）
  Config.post_click_delay = 0.3           # 点击后等待界面反应的时间（秒）

═══════════════════════════════════════════════════════════════════════
三、API 速查表
═══════════════════════════════════════════════════════════════════════

3.1 鼠标操作
────────────────────────────────────────────────────────────────────

  auto.move(x, y)
    移动鼠标到指定坐标
    示例：auto.move(500, 300)

  auto.click()
    左键单击。三种用法：
    · auto.click("保存")      # 找图并点击中心
    · auto.click(100, 200)    # 在坐标(100, 200)点击
    · auto.click()            # 在当前位置点击

  auto.dclick()
    双击。三种用法同上：
    · auto.dclick("文件")
    · auto.dclick(100, 200)
    · auto.dclick()

  auto.rclick()
    右键单击。三种用法同上：
    · auto.rclick("菜单")
    · auto.rclick(100, 200)
    · auto.rclick()

  auto.drag(x1, y1, x2, y2)
    从(x1,y1)平滑拖拽到(x2,y2)
    示例：auto.drag(100, 100, 500, 400)

  auto.pos()
    实时显示鼠标当前坐标（Ctrl+C停止）

3.2 键盘操作
────────────────────────────────────────────────────────────────────

  auto.write(text, times=1)
    粘贴文本（支持中文，通过剪贴板+Ctr+V实现）
    示例：auto.write("已完成")
    示例：auto.write("重要文本", times=3)   # 粘贴3次

  auto.press(key, times=1)
    按下并释放单个键
    示例：auto.press("enter")
    示例：auto.press("tab", times=3)
    常用键名：enter, tab, esc, spacebar, backspace, del, ins
             F1~F12, up_arrow, down_arrow, left_arrow, right_arrow
             ctrl, alt, shift, left_win, right_win
             numpad_0~numpad_9
             0~9, a~z
             + , - . / ` ; [ \ ] '

  auto.hotkey(key1, key2, ...)
    按下组合键
    示例：auto.hotkey("ctrl", "v")     # 粘贴
    示例：auto.hotkey("ctrl", "a")     # 全选
    示例：auto.hotkey("alt", "tab")    # 切换窗口

  auto.press_sequence(key1, key2, ...)
    依次按下多个键
    示例：auto.press_sequence("a", "b", "c")

3.3 图像识别
────────────────────────────────────────────────────────────────────

  auto.find("按钮名")
    在屏幕上查找图片，返回坐标或(-1,-1)
    示例：x, y = auto.find("确定按钮")
    示例：x, y = auto.find("确定", rect=(0,0,500,500))  # 限定区域查找

  auto.find("按钮名", similarity=0.85)
    放宽匹配精度（默认0.9，降低可在模糊时提高成功率）

3.4 等待操作
────────────────────────────────────────────────────────────────────

  auto.wait("加载完成", timeout=30)
    等待图片出现，默认超时30秒
    示例：auto.wait("进度条", 60)  # 最多等60秒

  auto.wait_not("加载动画", timeout=30)
    等待图片消失，默认超时30秒
    示例：auto.wait_not("loading")

3.5 流程引擎（链式调用）
────────────────────────────────────────────────────────────────────

  这是本工具最强大的功能，可像写文章一样编排自动化步骤。

  【基础链式】
  auto.do()
    通过 .do() 创建一个流程，然后用链式方法添加步骤，最后 .run() 执行。

  可用的链式方法：
    .click(目标)         添加点击步骤
    .dclick(目标)        添加双击步骤
    .rclick(目标)        添加右键步骤
    .write(文本)         添加输入步骤
    .press(键名)         添加按键步骤
    .hotkey(k1,k2,...)   添加组合键步骤
    .wait(目标)          添加等待出现步骤
    .wait_not(目标)      添加等待消失步骤
    .pause(秒数)         添加暂停步骤
    .retry(次数, 间隔)   设置失败重试
    .run()               执行流程

  【条件分支】
    .if_see(目标)        如果看到目标则执行后续
    .if_not_see(目标)    如果没看到目标则执行后续
    .else_do()           否则执行后续
    .endif()             结束条件块

  【循环】
    .for_data(列表)      遍历数据列表
    .end_for()           结束循环
    循环体内可用 {item} 表示当前项，{index} 表示索引

  【调试链式流程】
    auto.step()          开启/关闭单步模式（每步暂停等回车）
    auto.pace(秒数)      设置步骤间隔（方便观察执行过程）

3.6 调试工具
────────────────────────────────────────────────────────────────────

  auto.debug.on()
    开启操作追踪（记录每步成败、耗时、截图）
    示例：先 auto.debug.on()，再执行流程，最后 auto.debug.report()

  auto.debug.off()
    关闭操作追踪

  auto.debug.report()
    生成HTML执行报告（含步骤明细、成功率、耗时统计）

  auto.debug.replay()
    在命令行回放最近一次操作记录

3.7 环境诊断
────────────────────────────────────────────────────────────────────

  auto.check()
    一键检查：Python版本、屏幕分辨率、缩放系数、模板数量、依赖状态

  auto.check_templates()
    逐一检查所有模板能否在当前屏幕找到（需要目标窗口已打开）

3.8 截图工具
────────────────────────────────────────────────────────────────────

  auto.shot("文件名")
    全屏截图，保存到 screenshots 目录
    示例：auto.shot("我的桌面")

  auto.snip(x, y, w, h, "文件名")
    区域截图
    示例：auto.snip(0, 0, 500, 500, "左上角区域")

  auto.capture("按钮名称")
    截图模板工具：全屏截图后提示手动裁剪
    示例：auto.capture("保存按钮")  → 用画图裁剪后覆盖即可

3.9 定时任务
────────────────────────────────────────────────────────────────────

  auto.cron("时间", 任务函数)
    每天定时执行
    示例：auto.cron("17:30", my_task)   # 每天17:30执行
    示例：auto.cron("173000", my_task)  # 每天17:30:00执行

  auto.cron1("时间", 任务函数)
    一次性定时执行
    示例：auto.cron1("18:00", my_task)  # 到18:00执行一次

  【注意】定时任务需要保持脚本运行。使用 sched 模块实现，不会空耗CPU。

3.10 文件查找
────────────────────────────────────────────────────────────────────

  search(路径, 关键词)
    按关键词查找文件夹和文件（通过逗号分隔多个关键词）
    示例：folders, files = search(r"D:\工作", "报告,2025,doc")

3.11 日期工具
────────────────────────────────────────────────────────────────────

  monthends(年份)
    获取某年各月首日和末日（从2月到次年1月）
    示例：days = monthends(2025)
    返回：[['2025-02-01','2025-02-28'], ['2025-03-01','2025-03-31'], ...]

═══════════════════════════════════════════════════════════════════════
四、经典实战案例
═══════════════════════════════════════════════════════════════════════

【案例1】简单点击：保存并关闭
────────────────────────────────
  auto.click("保存按钮")
  time.sleep(1)
  auto.click("关闭按钮")

【案例2】填表提交
────────────────────────────────
  auto.click("姓名输入框")
  auto.write("张三")
  auto.click("年龄输入框")
  auto.write("28")
  auto.click("提交按钮")

【案例3】等待加载后操作
────────────────────────────────
  auto.wait("加载完成", timeout=60)   # 等最多60秒
  auto.click("下一步")
  auto.wait("页面就绪")
  auto.click("确定")

【案例4】链式流程：新建文档→写内容→保存
要把整个链式调用放在 一对括号 里，或者使用 行末反斜杠 \ 来续行。
推荐方式：括号包裹
(auto.do()
      .click("新建按钮")
      .pause(0.5)
      .write("这是自动生成的文档内容")
      .click("保存按钮")
      .pause(0.3)
      .hotkey("ctrl", "s")
      .run())

【案例5】条件分支：根据结果走不同路径
────────────────────────────────
  # 场景：点击提交后，如果成功就点确定，否则点重试
  auto.do()
      .click("提交按钮")
      .pause(1)
      .if_see("成功提示")
          .click("确定")
      .else_do()
          .click("重试")
      .endif()
      .run()

【案例6】双重条件：成功/警告/失败三路分支
────────────────────────────────
  auto.do()
      .click("提交按钮")
      .pause(2)
      .if_see("成功提示")
          .click("确定")
      .else_do()
          .if_see("警告提示")
              .click("继续")
          .else_do()
              .click("取消")
          .endif()
      .endif()
      .run()

【案例7】循环处理：批量填写多条数据
────────────────────────────────
  data = ["张三", "李四", "王五", "赵六"]

  auto.do()
      .click("新建按钮")
      .pause(0.5)
      .for_data(data)
          .click("姓名输入框")
          .write("{item}")          # {item} 会被替换为当前数据
          .click("保存按钮")
          .pause(0.3)
          .click("新增按钮")
      .end_for()
      .run()

【案例8】循环+条件：批量处理带异常判断
────────────────────────────────
  tasks = ["任务A", "任务B", "任务C"]

  auto.do()
      .for_data(tasks)
          .click("搜索框")
          .write("{item}")
          .press("enter")
          .pause(1)
          .if_see("未找到结果")
              .click("跳过")
          .else_do()
              .click("第一个结果")
              .click("下载按钮")
              .pause(2)
          .endif()
      .end_for()
      .run()

【案例9】失败重试：重要操作不怕失败
────────────────────────────────
  auto.do()
      .click("刷新按钮")
      .pause(1)
      .click("导出数据")      # 如果这步失败，会重试3次
      .retry(3, wait=2)       # 重试3次，间隔2秒
      .run()

【案例10】一键生成日报：截图+记录日志
────────────────────────────────
  def daily_report():
      auto.click("刷新数据")
      auto.wait("数据加载完成", 30)
      auto.shot("今日数据截图")
      auto.click("导出报表")
      auto.write("日报已生成")

  auto.cron("17:30", daily_report)   # 每天17:30自动执行

【案例11】带调试的流程开发
────────────────────────────────
  # 开发新流程时，打开调试模式
  auto.debug.on()            # 开启追踪
  auto.step()                # 开启单步模式
  auto.pace(1.0)             # 每步间隔1秒

  auto.do()
      .click("新建")
      .write("测试数据")
      .click("保存")
      .run()

  auto.debug.report()        # 生成HTML报告查看结果

【案例12】多条件组合：智能登录
────────────────────────────────
  auto.do()
      .click("登录按钮")
      .pause(2)
      .if_see("验证码弹窗")
          .write("1234")
          .click("确认")
          .pause(2)
      .endif()
      .if_see("登录成功")
          .click("进入系统")
      .else_do()
          .if_see("密码错误")
              .write("正确密码")
              .click("重新登录")
          .else_do()
              .click("忘记密码")
          .endif()
      .endif()
      .run()

【案例13】表格数据提取
────────────────────────────────
  # 假设表格有10行，每行有"编辑"按钮
  for row in range(10):
      btns = auto.find_all("编辑按钮")  # 找到所有编辑按钮
      if btns:
          x, y = btns[0]               # 点第一个
          auto.click(x, y)
          auto.write(f"第{row+1}行数据")
          auto.click("保存")
          auto.click("返回列表")
          time.sleep(0.5)

═══════════════════════════════════════════════════════════════════════
附录：常见问题
═══════════════════════════════════════════════════════════════════════

Q: 找图总是失败？
A: ① 确认截图是PNG格式  ② 确认文件名完全一致（不含扩展名）
   ③ 确认按钮在屏幕上可见  ④ 运行 auto.check() 诊断环境
   ⑤ 尝试放宽相似度：auto.find("按钮", similarity=0.85)

Q: 点击位置有偏差？
A: v4.0 已修复DPI问题。如仍有偏差，运行 auto.check() 检查缩放系数

Q: 流程跑到一半卡住了？
A: 开启调试模式排查：
   auto.debug.on()
   auto.step()             # 单步执行
   auto.pace(1.0)          # 慢速执行
   执行流程后 auto.debug.report() 查看报告

Q: 定时任务不执行？
A: 定时任务需要脚本保持运行状态（不退出），且系统不进入休眠

═══════════════════════════════════════════════════════════════════════
文档版本：v4.0
适用脚本：ClickClick 办公助手
最后更新：2026年5月
许可证：本项目基于 MIT License 开源，详情见 LICENSE 文件。
反馈与支持：欢迎在 GitHub 提交 Issue
═══════════════════════════════════════════════════════════════════════'''
