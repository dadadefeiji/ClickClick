# -*- coding: UTF-8 -*-
"""
 Copyright (c) 2026 yushihong. Licensed under the Apache-2.0 license.
 作者知乎主页：https://www.zhihu.com/people/mhaksy

【10秒快速上手】
  1. 复制本文件到任意文件夹（支持中文路径）。
  2. 在同目录下创建 "templates" 文件夹，把按钮截图（PNG格式）放进去。
  3. 写一行代码：auto.click("你的按钮名称")
  4. 运行，完成。

【ImgClickFlow v1.0 核心特性】
  ★ DPI自适应：自动适配100%/125%/150%缩放，一次编写，随处运行
  ★ 智能去重：基于NMS算法合并邻近匹配点，避免重复操作
  ★ 零负担等待：内置重试与超时，无需手动轮询
  ★ 批量识别：find_all()返回所有坐标，轻松实现批量循环
  ★ 链式流程：auto.do()流式编排，像写文章一样写自动化
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
import threading
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
from PIL import Image, ImageDraw, ImageFont, ImageGrab
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

logger = logging.getLogger('ImgClickFlow')
logger.setLevel(_log_level)
logger.addHandler(_console_handler)
logger.addHandler(_file_handler)
logger.info("=" * 40)
logger.info("ImgClickFlow 办公助手 启动")
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
    图像识别引擎 - DPI缩放修复版

    核心改进：
    - 图像匹配在物理坐标系中进行（不受缩放影响）
    - 返回物理坐标，点击时自动转换为逻辑坐标
    - 支持模板缓存，加速重复查找
    - 非极大值抑制去重，避免重复点击
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
        """去重：合并相邻匹配点（NMS算法）"""
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
        """查找所有匹配目标（物理坐标列表）"""
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
            print(f"  缩放不是100%，ImgClickFlow 已自动补偿")

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

    def __init__(self, locator, recorder, error_handler, debug_recorder=None):
        self.locator = locator
        self.recorder = recorder
        self.error_handler = error_handler
        self._debug_recorder = debug_recorder
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
                    if self._debug_recorder:
                        self._debug_recorder.success()
                    return True
            except Exception as e:
                last_error = e
                logger.error(f"流程异常: {e}")

        if last_error:
            if self._debug_recorder:
                self._debug_recorder.failure(str(last_error))
            logger.error(f"最终错误: {last_error}")
        return False

    def _make_action_str(self, action, target, kwargs):
        """为调试录像生成操作描述字符串"""
        if action in ('click', 'dclick', 'rclick'):
            if isinstance(target, str):
                return f"auto.do().{action}({target!r})"
            elif target is None:
                return f"auto.do().{action}()"
            else:
                return f"auto.do().{action}({target}, {kwargs.get('y', '')})"
        elif action == 'write':
            return f'auto.do().write("{target}")'
        elif action == 'press':
            times = kwargs.get('times', 1)
            return f'auto.do().press("{target}", times={times})'
        elif action == 'hotkey':
            keys = "+".join(target)
            return f'auto.do().hotkey({keys})'
        elif action == 'wait':
            return f'auto.do().wait("{target}")'
        elif action == 'wait_not':
            return f'auto.do().wait_not("{target}")'
        elif action == 'pause':
            return f'auto.do().pause({target})'
        elif action == 'if_start':
            return f'auto.do().if_see("{target}")'
        elif action == 'if_not_start':
            return f'auto.do().if_not_see("{target}")'
        elif action == 'else':
            return 'auto.do().else_do()'
        elif action == 'endif':
            return 'auto.do().endif()'
        elif action == 'for_start':
            return 'auto.do().for_data(...)'
        elif action == 'for_end':
            return 'auto.do().end_for()'
        else:
            return f'auto.do().{action}({target})'

    def _execute_steps(self, steps):
        i = 0
        while i < len(steps):
            action, target, kwargs = steps[i]
            # 调试录像：在执行前截图（仅水印）
            if self._debug_recorder and self._debug_recorder.enabled:
                code = self._make_action_str(action, target, kwargs)
                self._debug_recorder.capture(code)

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

                # 循环内的步骤也需要调试截图
                if self._debug_recorder and self._debug_recorder.enabled:
                    code = self._make_action_str(action, target, kwargs)
                    self._debug_recorder.capture(code)

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
# ║                 调试录像模块 DebugRecorder（自动启动，毫秒时间戳命名）        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class DebugRecorder:
    """调试录像模块：自动截图、水印、焦点标记。总开关：enabled"""

    def __init__(self):
        self.enabled = True
        self.max_screenshots = 15
        self.max_age_days = 7
        self._lock = threading.Lock()
        self._task_name = None
        self._task_dir = None
        self._counter = 0
        self._is_failure = False
        self.font_en = None
        self.font_cn = None
        self._font_valid = False
        self._max_failed_tasks = 5
        self._init_font()

    def _auto_start(self):
        """自动启动录像：以调用脚本名创建[脚本名_操作截屏]文件夹"""
        import __main__
        try:
            script_path = os.path.abspath(__main__.__file__)
        except AttributeError:
            # 交互式环境
            script_path = os.path.join(os.getcwd(), 'unknown_script.py')
        script_dir = os.path.dirname(script_path)
        script_name = os.path.splitext(os.path.basename(script_path))[0]
        self._task_name = script_name
        self._task_dir = os.path.join(script_dir, f"{script_name}_操作截屏")
        os.makedirs(self._task_dir, exist_ok=True)
        print(f"调试录像已自动启动，截图保存在: {self._task_dir}")

    def start(self, task_name=None):
        """手动启动录像（可自定义任务名）"""
        if not self.enabled:
            return
        with self._lock:
            if task_name:
                self._task_name = task_name
            else:
                import __main__
                main_file = getattr(__main__, '__file__', 'unknown_script')
                self._task_name = os.path.splitext(os.path.basename(main_file))[0] or "未命名任务"
            script_dir = os.path.dirname(os.path.abspath(__main__.__file__)) if hasattr(__main__, '__file__') else os.getcwd()
            self._task_dir = os.path.join(script_dir, f"{self._task_name}_操作截屏")
            os.makedirs(self._task_dir, exist_ok=True)
            self._counter = 0
            self._is_failure = False
            print(f"调试录像已手动启动: {self._task_dir}")

    def _init_font(self):
        """预检并加载中英文字体"""
        self.font_en = None
        self.font_cn = None
        try:
            self.font_en = ImageFont.truetype("consola.ttf", 16)
        except:
            try:
                self.font_en = ImageFont.truetype("cour.ttf", 16)
            except:
                try:
                    self.font_en = ImageFont.load_default()
                except:
                    pass
        try:
            self.font_cn = ImageFont.truetype("msyh.ttc", 16)
        except:
            try:
                self.font_cn = ImageFont.truetype("simsun.ttc", 16)
            except:
                self.font_cn = self.font_en
        self._font_valid = self.font_en is not None

    def _get_font(self, text):
        """根据文本内容选择中英文字体"""
        if self.font_cn and re.search(r'[\u4e00-\u9fff]', text):
            return self.font_cn
        return self.font_en if self.font_en else ImageFont.load_default()

    def capture(self, action_code, focus_shape=None):
        """截取当前屏幕，添加水印和可选的焦点标记，保存到任务目录"""
        if not self.enabled:
            return
        # 自动启动
        if self._task_dir is None:
            self._auto_start()

        with self._lock:
            try:
                screenshot = ImageGrab.grab()
                if screenshot is None:
                    return

                # 绘制焦点形状（在加水印之前，避免被覆盖）
                if focus_shape is not None:
                    self._draw_focus_shape(screenshot, focus_shape)

                # 添加水印
                now = datetime.datetime.now()
                now_str = now.strftime("%Y-%m-%d %H:%M:%S")
                display_code = action_code if len(action_code) <= 50 else action_code[:47] + "..."
                if self._is_failure:
                    line2 = f"[{self._task_name}][失败] {display_code}"
                else:
                    line2 = f"[{self._task_name}] {display_code}"
                watermarked = self._add_watermark(screenshot, now_str, line2)

                # 生成毫秒时间戳文件名，处理冲突
                base_name = f"capture_{now.strftime('%Y%m%d%H%M%S%f')[:-3]}"  # 截掉最后三位微秒转毫秒
                filepath = os.path.join(self._task_dir, f"{base_name}.png")
                suffix = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(self._task_dir, f"{base_name}_{suffix}.png")
                    suffix += 1

                watermarked.save(filepath)
                self._counter += 1

                # 实时清理（失败时不限制数量）
                if not self._is_failure:
                    self._enforce_limit()

            except Exception as e:
                logger.debug(f"调试截图失败: {e}")

    def _draw_focus_shape(self, image, shape):
        """根据形状字典在图片上绘制焦点标记：圆圈或矩形"""
        if shape is None:
            return
        scale = get_scale_factor()
        draw = ImageDraw.Draw(image)
        try:
            if shape['type'] == 'circle':
                x, y = shape['center']
                rx, ry = logical_to_real(x, y, scale)
                r_outer = max(1, int(25 * scale))
                r_inner = max(1, int(20 * scale))
                # 外红圆
                bbox_outer = [rx - r_outer, ry - r_outer, rx + r_outer, ry + r_outer]
                draw.ellipse(bbox_outer, outline='red', width=max(2, int(2*scale)))
                # 内白圆
                bbox_inner = [rx - r_inner, ry - r_inner, rx + r_inner, ry + r_inner]
                draw.ellipse(bbox_inner, outline='white', width=max(1, int(1*scale)))
            elif shape['type'] == 'rectangle':
                left, top = logical_to_real(shape['left'], shape['top'], scale)
                w = int(shape['width'] * scale)
                h = int(shape['height'] * scale)
                bbox = [left, top, left + w, top + h]
                draw.rectangle(bbox, outline='red', width=max(3, int(3*scale)))
        except:
            pass

    def _add_watermark(self, image, line1, line2):
        """在图片右下角添加白字黑边水印，自动适配中英文字体"""
        draw = ImageDraw.Draw(image)
        font1 = self._get_font(line1)
        font2 = self._get_font(line2)
        margin = 10
        try:
            bbox1 = draw.textbbox((0, 0), line1, font=font1)
            w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
            bbox2 = draw.textbbox((0, 0), line2, font=font2)
            w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
        except AttributeError:
            w1, h1 = draw.textsize(line1, font=font1)
            w2, h2 = draw.textsize(line2, font=font2)
        total_height = h1 + h2 + 5
        max_width = max(w1, w2)
        img_w, img_h = image.size
        x = img_w - max_width - margin
        y = img_h - total_height - margin
        offsets = [(-1,-1), (-1,1), (1,-1), (1,1)]
        for dx, dy in offsets:
            draw.text((x+dx, y+dy), line1, font=font1, fill="black")
            draw.text((x+dx, y+dy+h1+5), line2, font=font2, fill="black")
        draw.text((x, y), line1, font=font1, fill="white")
        draw.text((x, y+h1+5), line2, font=font2, fill="white")
        return image

    def _enforce_limit(self):
        if not self._task_dir:
            return
        try:
            # 按文件名（时间戳）排序，保留最新的 max_screenshots 张
            files = [f for f in os.listdir(self._task_dir) if f.startswith("capture_") and f.endswith(".png")]
            files.sort()  # 字符串排序即时间顺序
            while len(files) > self.max_screenshots:
                oldest = files.pop(0)
                os.remove(os.path.join(self._task_dir, oldest))
        except Exception as e:
            logger.debug(f"清理截图失败: {e}")

    def success(self):
        if not self.enabled or not self._task_dir:
            return
        with self._lock:
            self._enforce_limit()
            print(f"录像任务正常结束，保留最近 {min(self.max_screenshots, self._counter)} 张截图")

    def failure(self, error_msg=""):
        if not self.enabled or not self._task_dir:
            return
        with self._lock:
            self._is_failure = True
            try:
                screenshot = ImageGrab.grab()
                if screenshot:
                    now = datetime.datetime.now()
                    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
                    msg_display = error_msg[:47] + "..." if len(error_msg) > 50 else error_msg
                    line2 = f"[{self._task_name}][失败] {msg_display}"
                    watermarked = self._add_watermark(screenshot, now_str, line2)
                    base_name = f"failure_{now.strftime('%Y%m%d%H%M%S%f')[:-3]}"
                    failure_path = os.path.join(self._task_dir, f"{base_name}.png")
                    watermarked.save(failure_path)
            except Exception as e:
                logger.debug(f"失败截图保存失败: {e}")
            self._write_error_summary(error_msg)

    def _write_error_summary(self, error_msg):
        if not self._task_dir:
            return
        summary_path = os.path.join(self._task_dir, "error_summary.txt")
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"任务名称: {self._task_name}\n")
                f.write(f"失败时间: {datetime.datetime.now()}\n")
                f.write(f"错误信息: {error_msg}\n")
                f.write(f"截图数量: {self._counter}\n")
        except Exception as e:
            logger.debug(f"写入错误摘要失败: {e}")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    主用户接口类 _Auto (集成录像调用)                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class _Auto:
    """ImgClickFlow 办公助手"""

    def __init__(self):
        self._locator = _LocatorFusion()
        self._recorder = _StepRecorder()
        self._error_handler = _ErrorHandler()
        self._env_checker = _EnvChecker()
        self.debug = _DebugTools(self._recorder)
        self._step_mode = False
        self._step_pace = 0
        # 调试录像记录器（默认开启，自动启动）
        self.recorder = DebugRecorder()

    # ===== 通用暂停 =====
    def delay(self, seconds=1.0):
        """暂停指定秒数（封装 time.sleep）"""
        time.sleep(float(seconds))

    # ===== 屏幕截图 =====
    def shot(self, filename="screenshot"):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.shot("{filename}")')
        path = os.path.join(_base_dir, Config.screenshot_dir, f"{filename}_{time.strftime('%H%M%S')}.png")
        ImageGrab.grab().save(path)
        logger.info(f"截图已保存: {path}")
        print(f"截图已保存: {path}")
        return path

    def snip(self, x, y, w, h, filename="region"):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.snip({x},{y},{w},{h},"{filename}")')
        path = os.path.join(_base_dir, Config.screenshot_dir, f"{filename}_{time.strftime('%H%M%S')}.png")
        ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h))).save(path)
        logger.info(f"区域截图已保存: {path}")
        print(f"区域截图已保存: {path}")
        return path

    # ===== 鼠标操作 =====
    def moveto(self, x, y):
        """移动鼠标到指定坐标"""
        if self.recorder.enabled:
            self.recorder.capture(f'auto.moveto({x}, {y})', focus_shape={'type':'circle', 'center':(x, y)})
        mouse_moveto(int(x), int(y))

    # 别名
    move = moveto

    def click(self, *args):
        if not args:
            if self.recorder.enabled:
                x, y = get_mouse_point()
                self.recorder.capture("auto.click()", focus_shape={'type':'circle', 'center':(x, y)})
            x, y = get_mouse_point()
            mouse_left_click(x, y)
        elif len(args) == 1 and isinstance(args[0], str):
            # 找图点击，截图由 _click_by_image 内部处理
            self._click_by_image(args[0])
        elif len(args) >= 2:
            if self.recorder.enabled:
                self.recorder.capture(f"auto.click({args[0]}, {args[1]})", focus_shape={'type':'circle', 'center':(args[0], args[1])})
            mouse_left_click(int(args[0]), int(args[1]))

    def dclick(self, *args):
        if not args:
            if self.recorder.enabled:
                x, y = get_mouse_point()
                self.recorder.capture("auto.dclick()", focus_shape={'type':'circle', 'center':(x, y)})
            x, y = get_mouse_point()
            mouse_left_click(x, y, k=2)
        elif len(args) == 1 and isinstance(args[0], str):
            self._click_by_image(args[0], clicks=2)
        elif len(args) >= 2:
            if self.recorder.enabled:
                self.recorder.capture(f"auto.dclick({args[0]}, {args[1]})", focus_shape={'type':'circle', 'center':(args[0], args[1])})
            mouse_left_click(int(args[0]), int(args[1]), k=2)

    def rclick(self, *args):
        if not args:
            if self.recorder.enabled:
                x, y = get_mouse_point()
                self.recorder.capture("auto.rclick()", focus_shape={'type':'circle', 'center':(x, y)})
            x, y = get_mouse_point()
            mouse_right_click(x, y)
        elif len(args) == 1 and isinstance(args[0], str):
            self._click_by_image(args[0], right_click=True)
        elif len(args) >= 2:
            if self.recorder.enabled:
                self.recorder.capture(f"auto.rclick({args[0]}, {args[1]})", focus_shape={'type':'circle', 'center':(args[0], args[1])})
            mouse_right_click(int(args[0]), int(args[1]))

    def drag(self, x1, y1, x2, y2):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.drag({x1},{y1},{x2},{y2})', focus_shape={'type':'circle', 'center':(x1, y1)})
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
        """找图点击，负责录像截图（含矩形标记）"""
        action_code = f"auto.{'rclick' if right_click else 'dclick' if clicks>1 else 'click'}(\"{tempname}\")"
        start_time = time.time()

        # 找图
        coords = self._locator.find(tempname)
        scale = self._locator.get_scale_factor()
        if coords != (-1, -1):
            # 成功：截取操作前画面并画矩形
            lx, ly = coords
            tw, th = self._locator.get_template_size()
            tw_logic = int(tw / scale)
            th_logic = int(th / scale)
            shape = {'type': 'rectangle', 'left': lx, 'top': ly, 'width': tw_logic, 'height': th_logic}
            if self.recorder.enabled:
                self.recorder.capture(action_code, focus_shape=shape)

            # 执行点击
            cx, cy = int(lx + tw_logic/2), int(ly + th_logic/2)
            if right_click:
                mouse_right_click(cx, cy)
            else:
                mouse_left_click(cx, cy, k=clicks)
            time.sleep(Config.post_click_delay)
            self._recorder.record('click', tempname, True, time.time() - start_time)
            return True
        else:
            # 失败：截取现场画面（无标记）
            if self.recorder.enabled:
                self.recorder.capture(action_code, focus_shape=None)
            self._error_handler.save_error_screenshot(tempname)
            print(self._error_handler.format_error_message(tempname, Config.default_similarity, Config.default_timeout))
            self._recorder.record('click', tempname, False, time.time() - start_time)
            return False

    # ===== 键盘操作 =====
    def write(self, text, times=1):
        if self.recorder.enabled:
            display = str(text)[:47] + '...' if len(str(text)) > 50 else str(text)
            self.recorder.capture(f'auto.write("{display}", times={times})')
        saystring(str(text), k=times)

    def press(self, key_name, times=1):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.press("{key_name}", times={times})')
        key_press(str(key_name), k=times)

    def hotkey(self, *keys):
        if self.recorder.enabled:
            keys_str = '+'.join(keys)
            self.recorder.capture(f'auto.hotkey({keys_str})')
        key_press_plus([str(k).lower() for k in keys])

    def press_sequence(self, *keys):
        if self.recorder.enabled:
            seq = ', '.join(keys)
            self.recorder.capture(f'auto.press_sequence({seq})')
        for k in keys:
            key_press(str(k))
            time.sleep(0.05)

    # ===== 图像识别 =====
    def find(self, tempname, timeout=None, similarity=None, rect=None):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.find("{tempname}")')
        return self._locator.find(tempname, timeout=timeout, area=rect)

    def find_all(self, tempname, timeout=None, similarity=None, rect=None):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.find_all("{tempname}")')
        return self._locator.find_all(tempname, timeout=timeout, area=rect)

    def wait(self, tempname, timeout=30):
        if self.recorder.enabled:
            self.recorder.capture(f'auto.wait("{tempname}", timeout={timeout})')
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
        if self.recorder.enabled:
            self.recorder.capture(f'auto.wait_not("{tempname}", timeout={timeout})')
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
        flow = Flow(self._locator, self._recorder, self._error_handler, debug_recorder=self.recorder)
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
        if self.recorder.enabled:
            self.recorder.capture(f'auto.capture("{name}")')
        return capture_template_simple(name)

    # ===== 帮助 =====
    def help(self):
        print(__doc__)
        print("\n作者知乎：https://www.zhihu.com/people/mhaksy")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    创建全局实例                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

auto = _Auto()
auto.version = "1.0.0"

# 导出别名
search = find_files
monthends = first_last_day

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    运行入口                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    auto.help()
    print("\n" + "=" * 60)
    print("ImgClickFlow v1.0 正式发布")
    print("作者知乎：https://www.zhihu.com/people/mhaksy")
    print("核心特性：DPI自动适配 | 智能去重 | 零负担等待 | 批量识别 | 链式流程")
    print("=" * 60)
    print("\n助手已就绪。")

    # 完整使用手册
    print('''
╔══════════════════════════════════════════════════════════════════════╗
║              ImgClickFlow 办公助手 — 完整使用手册                   ║
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
  ├── imgclickflow.py   ← 主脚本文件
  ├── templates/       ← 按钮截图文件夹（放PNG图片）
  ├── logs/            ← 运行日志（自动生成）
  ├── screenshots/     ← 用户截图（自动生成）
  └── error_snapshots/ ← 失败截图（自动生成）

【三步开始】
  步骤1：把脚本放到任意文件夹
  步骤2：在同目录创建 templates 文件夹，放入按钮PNG截图
  步骤3：写一行代码运行

  from imgclickflow import auto
  auto.click("按钮名称")   # 找图并点击，就这么简单

【重要提醒】
  ★ 截图必须用 PNG 格式！JPG 会造成像素偏移！
  ★ v1.0 已修复 DPI 缩放问题，100%/125%/150% 均可正常使用
  ★ 模板只截按钮本体，越小越独特越好

═══════════════════════════════════════════════════════════════════════
二、配置与参数（修改脚本中的 Config 类）
═══════════════════════════════════════════════════════════════════════

  template_dir = "templates"        # 模板截图存放文件夹
  log_dir = "logs"                  # 日志存放文件夹
  screenshot_dir = "screenshots"    # 截图存放文件夹
  error_dir = "error_snapshots"     # 失败截图存放文件夹
  default_similarity = 0.9         # 图像匹配相似度（0~1，越高越严格）
  default_timeout = 10             # 找图默认超时（秒）
  retry_interval = 0.2             # 找图失败重试间隔（秒）
  post_click_delay = 0.3           # 点击后等待界面反应的时间（秒）

═══════════════════════════════════════════════════════════════════════
三、API 速查表
═══════════════════════════════════════════════════════════════════════

3.1 鼠标操作
────────────────────────────────────────────────────────────────────

  auto.moveto(x, y)            移动鼠标到逻辑坐标
  auto.click()               左键单击（三种用法：无参数/坐标/图片名）
  auto.dclick()              双击
  auto.rclick()              右键单击
  auto.drag(x1,y1,x2,y2)     平滑拖拽
  auto.pos()                 实时显示鼠标坐标（Ctrl+C停止）

3.2 键盘操作
────────────────────────────────────────────────────────────────────

  auto.write(text, times=1)       粘贴文本（支持中文）
  auto.press(key, times=1)        按下并释放单个键
  auto.hotkey(k1,k2,...)          组合键
  auto.press_sequence(*keys)      依次按下多个键
  auto.delay(seconds)             暂停指定秒数（无需导入 time）

  常用键名：enter, tab, esc, spacebar, backspace, del, ins,
           F1~F12, up_arrow, down_arrow, left_arrow, right_arrow,
           ctrl, alt, shift, left_win, right_win,
           numpad_0~numpad_9, 0~9, a~z, + , - . / ` ; [ \\ ] '

3.3 图像识别
────────────────────────────────────────────────────────────────────

  auto.find("按钮名", timeout=None, similarity=None, rect=None)
      返回 (x, y) 或 (-1, -1)
  auto.find_all("按钮名") 
      返回所有匹配坐标列表 [(x,y), ...]
  auto.wait("按钮名", timeout=30)
      等待图片出现，成功返回True
  auto.wait_not("按钮名", timeout=30)
      等待图片消失

3.4 流程引擎（链式调用）
────────────────────────────────────────────────────────────────────

  创建流程：auto.do() → 添加步骤 → .run()

  可用方法：
    .click(目标) .dclick(目标) .rclick(目标)
    .write(文本) .press(键名) .hotkey(k1,k2,...)
    .wait(目标) .wait_not(目标) .pause(秒)
    .retry(次数, 间隔)      # 整体重试
    .if_see(目标) .if_not_see(目标) .else_do() .endif()
    .for_data(列表) .end_for()   # 循环体可用{item}和{index}

3.5 调试工具
────────────────────────────────────────────────────────────────────

  auto.debug.on()         开启操作追踪
  auto.debug.off()        关闭追踪
  auto.debug.report()     生成HTML执行报告
  auto.debug.replay()     控制台回放记录

3.6 环境诊断
────────────────────────────────────────────────────────────────────

  auto.check()                全面诊断（分辨率、缩放、依赖）
  auto.check_templates()      检查所有模板是否可见

3.7 截图工具
────────────────────────────────────────────────────────────────────

  auto.shot("文件名")         全屏截图
  auto.snip(x,y,w,h,"文件名") 区域截图
  auto.capture("按钮名")      交互式生成模板截图

3.8 定时任务
────────────────────────────────────────────────────────────────────

  auto.cron("17:30", my_task)      # 每天17:30执行
  auto.cron1("18:00", my_task)     # 一次性定时

3.9 文件查找（需导入 search）
────────────────────────────────────────────────────────────────────

  from imgclickflow import search
  folders, files = search(r"D:\\工作", "报告,2025,doc")

3.10 日期工具（需导入 monthends）
────────────────────────────────────────────────────────────────────

  from imgclickflow import monthends
  days = monthends(2025)   # 返回2月到次年1月的首末日列表

═══════════════════════════════════════════════════════════════════════
四、经典实战案例（缩略版，更多见项目主页）
═══════════════════════════════════════════════════════════════════════

# 案例1：保存并关闭
auto.click("保存按钮")
auto.delay(1)
auto.click("关闭按钮")

# 案例2：链式新建文档并保存
auto.do()
    .click("新建按钮")
    .write("文档内容")
    .click("保存")
    .run()

# 案例3：批量循环填写表格
data = ["张三","李四","王五"]
auto.do()
    .for_data(data)
        .click("姓名框")
        .write("{item}")
        .click("保存")
    .end_for()
    .run()

# 案例4：条件分支
auto.do()
    .click("提交")
    .if_see("成功")
        .click("确定")
    .else_do()
        .click("重试")
    .endif()
    .run()

# 案例5：每日定时截图
def daily_job():
    auto.click("刷新")
    auto.shot("日报")
auto.cron("17:30", daily_job)

═══════════════════════════════════════════════════════════════════════
文档版本：v1.1    适用脚本：ImgClickFlow    最后更新：2026年5月
作者知乎：https://www.zhihu.com/people/mhaksy
═══════════════════════════════════════════════════════════════════════
''')
