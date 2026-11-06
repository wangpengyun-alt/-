#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片信息与编辑器 —— 重写第 3 部分。

本阶段实现：
    * 打开并校验图片，读取文件名、格式、宽高、颜色模式和文件大小；
    * 图片预览与基础错误提示；
    * 等比/精确缩放，90°、180°、270° 旋转，撤销与还原；
    * 指定坐标裁剪、预览图拖动框选和越界提示；
    * 彩色转灰度，并保留透明通道。

保存、格式转换和原图保护将在第 4 部分补全。

运行：
    python image_editor.py
"""

from __future__ import annotations

import math
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageOps, ImageTk, UnidentifiedImageError

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "图片信息与编辑器"
APP_VERSION = "1.0"
PART_LABEL = "PART 3 / 4"

OPEN_FILETYPES = [
    ("常见图片", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif"),
    ("PNG 图片", "*.png"),
    ("JPEG 图片", "*.jpg *.jpeg"),
    ("BMP 图片", "*.bmp"),
    ("WebP 图片", "*.webp"),
    ("TIFF 图片", "*.tif *.tiff"),
    ("GIF 图片", "*.gif"),
    ("所有文件", "*.*"),
]

MODE_LABELS = {
    "1": "1（黑白）",
    "L": "L（灰度）",
    "LA": "LA（灰度 + 透明）",
    "P": "P（调色板）",
    "RGB": "RGB（彩色）",
    "RGBA": "RGBA（彩色 + 透明）",
    "CMYK": "CMYK（印刷色）",
    "YCbCr": "YCbCr（亮度/色度）",
    "I": "I（32 位整数）",
    "F": "F（32 位浮点）",
}

# 防止误输入超大尺寸导致耗尽内存。
MAX_IMAGE_SIDE = 12000
MAX_IMAGE_PIXELS = 100_000_000

# 界面配色
BG = "#EEF2F7"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
ACCENT_SOFT = "#DBEAFE"
DANGER = "#DC2626"
SUCCESS = "#15803D"
PREVIEW_BG = "#1B1D23"


# ---------------------------------------------------------------------------
# 核心逻辑：图片读取与信息整理
# ---------------------------------------------------------------------------


class ImageEditorError(Exception):
    """本程序可预期错误的基类。"""


class ImageLoadError(ImageEditorError):
    """文件不存在、无法读取或不是有效图片。"""


class ValidationError(ImageEditorError):
    """用户输入的参数不合法。"""


class CropOutOfBoundsError(ValidationError):
    """裁剪区域超出图片边界。"""


@dataclass(frozen=True)
class ImageInfo:
    """图片原始信息快照。"""

    path: Path
    filename: str
    image_format: str
    width: int
    height: int
    mode: str
    file_size_bytes: int

    @property
    def file_size_mb(self) -> str:
        """按 MB 显示，保留两位小数。"""
        return f"{self.file_size_bytes / (1024 * 1024):.2f} MB"

    @property
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.mode, self.mode)

    @property
    def size_text(self) -> str:
        return f"{self.width} × {self.height} 像素"


def describe_mode(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


def load_image_file(path: str | os.PathLike[str]) -> Tuple[Image.Image, ImageInfo]:
    """读取图片并返回工作图像与原始信息。

    JPEG 的 EXIF 方向会被应用到工作图像，确保预览方向正确。
    多帧图片（如 GIF/TIFF）只读取第一帧。
    """
    file_path = Path(path).expanduser()

    if not file_path.exists():
        raise ImageLoadError(f"文件不存在：\n{file_path}")
    if not file_path.is_file():
        raise ImageLoadError(f"所选路径不是文件：\n{file_path}")

    try:
        if file_path.stat().st_size == 0:
            raise ImageLoadError(f"文件内容为空，不是有效图片：\n{file_path}")
        with Image.open(file_path) as opened:
            opened.load()  # 提前解码，损坏文件会在这里暴露
            image_format = (opened.format or file_path.suffix.lstrip(".")).upper()
            image = ImageOps.exif_transpose(opened).copy()
    except ImageLoadError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageLoadError(
            "图片像素数量过大，出于安全考虑无法打开。"
        ) from exc
    except UnidentifiedImageError as exc:
        raise ImageLoadError(
            f"文件不是有效的图片，或格式暂不支持：\n{file_path.name}"
        ) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageLoadError(f"无法读取图片：{exc}") from exc

    try:
        file_size = file_path.stat().st_size
    except OSError as exc:
        raise ImageLoadError(f"无法读取文件信息：{exc}") from exc

    info = ImageInfo(
        path=file_path.resolve(),
        filename=file_path.name,
        image_format=image_format,
        width=image.width,
        height=image.height,
        mode=image.mode,
        file_size_bytes=file_size,
    )
    return image, info


def parse_positive_int(value: str, field_name: str) -> int:
    """把界面文本解析为正整数，空值或非法值给出中文提示。"""
    text = str(value).strip()
    if not text:
        raise ValidationError(f"请输入{field_name}。")
    try:
        number = int(text)
    except ValueError as exc:
        raise ValidationError(f"{field_name}必须是整数。") from exc
    if number <= 0:
        raise ValidationError(f"{field_name}必须大于 0。")
    return number


def parse_optional_positive_int(value: str, field_name: str) -> int | None:
    """把界面文本解析为可空正整数；空值返回 None。"""
    if not str(value).strip():
        return None
    return parse_positive_int(value, field_name)


def parse_nonnegative_int(value: str, field_name: str) -> int:
    """把界面文本解析为非负整数。"""
    text = str(value).strip()
    if not text:
        raise ValidationError(f"请输入{field_name}。")
    try:
        number = int(text)
    except ValueError as exc:
        raise ValidationError(f"{field_name}必须是整数。") from exc
    if number < 0:
        raise ValidationError(f"{field_name}不能小于 0。")
    return number


def calculate_resize_dimensions(
    original_width: int,
    original_height: int,
    width: int | None = None,
    height: int | None = None,
) -> Tuple[int, int]:
    """只提供宽或高时按比例计算另一边，两者都提供时精确缩放。"""
    if width is None and height is None:
        raise ValidationError("请至少填写宽度或高度。")

    for value, name in ((width, "宽度"), (height, "高度")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise ValidationError(f"{name}必须是大于 0 的整数。")

    if width is None:
        assert height is not None
        new_width = max(1, int(round(original_width * height / original_height)))
        new_height = height
    elif height is None:
        new_width = width
        new_height = max(1, int(round(original_height * width / original_width)))
    else:
        new_width, new_height = width, height

    if new_width > MAX_IMAGE_SIDE or new_height > MAX_IMAGE_SIDE:
        raise ValidationError(
            f"目标尺寸过大，单边不能超过 {MAX_IMAGE_SIDE} 像素。"
        )
    if new_width * new_height > MAX_IMAGE_PIXELS:
        raise ValidationError("目标图片总像素过大，请减小缩放尺寸。")
    return new_width, new_height


def resize_image(
    image: Image.Image,
    width: int | None = None,
    height: int | None = None,
) -> Image.Image:
    """按指定宽/高等比或精确缩放图片。"""
    new_width, new_height = calculate_resize_dimensions(
        image.width, image.height, width, height
    )
    if (new_width, new_height) == image.size:
        return image.copy()
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def rotate_image(image: Image.Image, angle: int) -> Image.Image:
    """顺时针旋转 90°、180° 或 270°。"""
    if angle not in (90, 180, 270):
        raise ValidationError("旋转角度只支持 90°、180° 或 270°。")
    # Pillow 的 ROTATE_90 是逆时针；这里映射成顺时针角度。
    operations = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    return image.transpose(operations[angle])


def crop_image(
    image: Image.Image, x: int, y: int, width: int, height: int
) -> Image.Image:
    """裁剪指定矩形区域；越界时抛出明确的异常。"""
    values = ((x, "X 坐标"), (y, "Y 坐标"), (width, "裁剪宽度"), (height, "裁剪高度"))
    for value, name in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{name}必须是整数。")
    if x < 0 or y < 0:
        raise ValidationError("裁剪坐标不能小于 0。")
    if width <= 0 or height <= 0:
        raise ValidationError("裁剪宽度和高度必须大于 0。")
    if x + width > image.width or y + height > image.height:
        raise CropOutOfBoundsError(
            "裁剪区域超出图片范围。\n\n"
            f"图片尺寸：{image.width} × {image.height} 像素\n"
            f"当前区域：x={x}, y={y}, 宽={width}, 高={height}\n\n"
            "请调整坐标或区域大小，确保区域完全位于图片内。"
        )
    return image.crop((x, y, x + width, y + height))


def to_grayscale(image: Image.Image) -> Image.Image:
    """转换灰度图；原图有透明通道时以 LA 模式保留透明度。"""
    if image.mode in ("L", "LA"):
        return image.copy()
    if image.mode == "1":
        return image.convert("L")
    try:
        if has_alpha(image):
            rgba = image.convert("RGBA")
            gray = rgba.convert("L")
            alpha = rgba.getchannel("A")
            return Image.merge("LA", (gray, alpha))
        return ImageOps.grayscale(image)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"无法转换为灰度图：{exc}") from exc


class ImageDocument:
    """保存原图、当前编辑结果以及可撤销的历史状态。"""

    def __init__(self, image: Image.Image, info: ImageInfo) -> None:
        self.info = info
        self.path = info.path
        self._states = [("原图", image)]
        self._index = 0

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "ImageDocument":
        image, info = load_image_file(path)
        return cls(image, info)

    @property
    def image(self) -> Image.Image:
        return self._states[self._index][1]

    @property
    def action_label(self) -> str:
        return self._states[self._index][0]

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def is_modified(self) -> bool:
        return self._index > 0

    def apply(self, image: Image.Image, label: str) -> None:
        """提交一次编辑；之后的历史分支会被丢弃。"""
        del self._states[self._index + 1 :]
        self._states.append((label, image))
        self._index += 1

    def undo(self) -> str | None:
        if not self.can_undo:
            return None
        undone_label = self._states[self._index][0]
        self._index -= 1
        return undone_label

    def reset(self) -> bool:
        if not self.is_modified:
            return False
        self._index = 0
        return True


# ---------------------------------------------------------------------------
# 界面辅助函数
# ---------------------------------------------------------------------------


def make_checkerboard(size: Tuple[int, int], cell: int = 12) -> Image.Image:
    """生成透明区域预览用的棋盘格底图。"""
    tile = Image.new("RGB", (cell * 2, cell * 2), "#EDEFF3")
    draw = ImageDraw.Draw(tile)
    draw.rectangle((0, 0, cell - 1, cell - 1), fill="#D8DDE6")
    draw.rectangle((cell, cell, cell * 2 - 1, cell * 2 - 1), fill="#D8DDE6")

    board = Image.new("RGB", size, "#EDEFF3")
    for y in range(0, size[1], cell * 2):
        for x in range(0, size[0], cell * 2):
            board.paste(tile, (x, y))
    return board


def has_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA", "PA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def make_app_icon() -> Image.Image:
    """程序化生成窗口图标，避免依赖外部图标文件。"""
    icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=ACCENT)
    draw.rounded_rectangle((15, 19, 49, 45), radius=4, outline="white", width=3)
    draw.ellipse((20, 24, 28, 32), fill="white")
    draw.polygon([(18, 42), (29, 31), (36, 38), (41, 33), (47, 42)], fill="white")
    return icon


# ---------------------------------------------------------------------------
# 图形界面
# ---------------------------------------------------------------------------


class ImageEditorApp(tk.Tk):
    """第 3 部分主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.configure(bg=BG)
        self.minsize(980, 680)

        self.document: ImageDocument | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_geom: Tuple[int, int, int, int, float] | None = None
        self._render_job: str | None = None
        self._crop_drag_start: Tuple[int, int] | None = None
        self._crop_rect_id: int | None = None

        self._setup_fonts()
        self._setup_styles()
        self._set_window_icon()
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_info()
        self._refresh_action_states()
        self._center_window()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(100, self._render_preview)

    # ----- 初始化 ---------------------------------------------------------

    def _setup_fonts(self) -> None:
        available = set(tkfont.families(self))
        preferred = (
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "PingFang SC",
            "Noto Sans CJK SC",
            "Segoe UI",
        )
        self.font_family = next(
            (name for name in preferred if name in available),
            tkfont.nametofont("TkDefaultFont").actual("family"),
        )
        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkTooltipFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(
                    family=self.font_family, size=10
                )
            except tk.TclError:
                pass

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        family = self.font_family

        style.configure(".", font=(family, 10), background=SURFACE, foreground=TEXT)
        style.configure("TFrame", background=SURFACE)
        style.configure("Panel.TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=TEXT)

        style.configure(
            "TButton",
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(13, 7),
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            font=(family, 10),
        )
        style.map(
            "TButton",
            background=[
                ("pressed", "#E2E8F0"),
                ("active", "#F8FAFC"),
            ],
            bordercolor=[("active", "#CBD5E1")],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#FFFFFF",
            bordercolor=ACCENT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            padding=(18, 9),
            font=(family, 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", ACCENT_DARK), ("active", ACCENT_DARK)],
            bordercolor=[("active", ACCENT_DARK)],
        )
        style.configure(
            "Secondary.TButton",
            background="#F1F5F9",
            foreground=TEXT,
            bordercolor="#CBD5E1",
            lightcolor="#CBD5E1",
            darkcolor="#CBD5E1",
            padding=(13, 7),
            font=(family, 10),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("disabled", "#F3F4F6"),
                ("pressed", "#CBD5E1"),
                ("active", "#E2E8F0"),
            ],
            foreground=[("disabled", "#94A3B8")],
            bordercolor=[("disabled", BORDER)],
        )
        style.configure(
            "Soft.TButton",
            background=ACCENT_SOFT,
            foreground=ACCENT_DARK,
            bordercolor="#93C5FD",
            lightcolor="#93C5FD",
            darkcolor="#93C5FD",
            padding=(13, 7),
            font=(family, 10),
        )
        style.map(
            "Soft.TButton",
            background=[("pressed", "#BFDBFE"), ("active", "#BFDBFE")],
            bordercolor=[("active", "#60A5FA")],
        )
        style.configure(
            "TEntry",
            fieldbackground=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            insertcolor=TEXT,
            padding=(7, 6),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            darkcolor=[("focus", ACCENT)],
        )

        style.configure(
            "TNotebook",
            background=SURFACE,
            borderwidth=0,
            bordercolor=BORDER,
            lightcolor=SURFACE,
            darkcolor=SURFACE,
            relief="flat",
        )
        style.configure(
            "TNotebook.Tab",
            background="#F1F5F9",
            foreground=MUTED,
            padding=(13, 7),
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            font=(family, 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE), ("active", "#E8EEF8")],
            foreground=[("selected", ACCENT), ("active", TEXT)],
        )
        style.configure("TSeparator", background=BORDER)

    def _set_window_icon(self) -> None:
        icon = make_app_icon()
        self._window_icon = ImageTk.PhotoImage(icon)
        self.iconphoto(True, self._window_icon)
        self._header_icon = ImageTk.PhotoImage(
            icon.resize((42, 42), Image.Resampling.LANCZOS)
        )

    def _center_window(self) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1200, max(980, screen_w - 120))
        height = min(800, max(680, screen_h - 120))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self) -> None:
        self._build_header()

        self.status_var = tk.StringVar(value="就绪 · 请打开一张图片")
        status_bar = tk.Frame(self, bg=SURFACE, height=32)
        status_bar.pack(side="bottom", fill="x")
        status_bar.pack_propagate(False)
        tk.Frame(status_bar, bg=BORDER, height=1).pack(side="top", fill="x")

        self.status_label = tk.Label(
            status_bar,
            textvariable=self.status_var,
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        )
        self.status_label.pack(side="left", padx=20, pady=6)
        tk.Label(
            status_bar,
            text="Ctrl+O 打开    Ctrl+Z 撤销",
            bg=SURFACE,
            fg="#94A3B8",
            font=(self.font_family, 9),
            anchor="e",
        ).pack(side="right", padx=20, pady=6)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(16, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=390)
        body.grid_rowconfigure(0, weight=1)

        self._build_preview(body)
        self._build_sidebar(body)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=SURFACE, height=78)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")

        inner = tk.Frame(header, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=22)

        tk.Label(inner, image=self._header_icon, bg=SURFACE).pack(
            side="left", pady=18
        )
        title_box = tk.Frame(inner, bg=SURFACE)
        title_box.pack(side="left", padx=12, pady=14)
        tk.Label(
            title_box,
            text="图片信息与编辑器",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 17, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="阶段 3 · 裁剪、灰度与透明通道",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(anchor="w")

        self.open_btn = ttk.Button(
            inner,
            text="打开图片",
            style="Accent.TButton",
            command=self._on_open,
        )
        self.open_btn.pack(side="right", pady=18)
        self.reset_btn = ttk.Button(
            inner,
            text="还原原图",
            style="Secondary.TButton",
            command=self._on_reset,
        )
        self.reset_btn.pack(side="right", padx=(0, 8), pady=18)
        self.undo_btn = ttk.Button(
            inner,
            text="撤销",
            style="Secondary.TButton",
            command=self._on_undo,
        )
        self.undo_btn.pack(side="right", padx=(0, 8), pady=18)
        tk.Label(
            inner,
            text=PART_LABEL,
            bg=ACCENT_SOFT,
            fg=ACCENT_DARK,
            font=(self.font_family, 8, "bold"),
            padx=9,
            pady=4,
        ).pack(side="right", padx=(0, 12), pady=20)

    def _build_preview(self, parent: tk.Widget) -> None:
        card = tk.Frame(
            parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        header = tk.Frame(card, bg=SURFACE)
        header.grid(row=0, column=0, sticky="ew", padx=17, pady=(13, 8))
        tk.Label(
            header,
            text="图像预览",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 11, "bold"),
        ).pack(side="left")
        self.preview_badge_var = tk.StringVar(value="未打开图片")
        tk.Label(
            header,
            textvariable=self.preview_badge_var,
            bg=SURFACE_ALT,
            fg=MUTED,
            font=(self.font_family, 9),
            padx=9,
            pady=3,
        ).pack(side="right")

        canvas_wrap = tk.Frame(card, bg=SURFACE)
        canvas_wrap.grid(row=2, column=0, sticky="nsew", padx=16)
        self.canvas = tk.Canvas(
            canvas_wrap,
            bg=PREVIEW_BG,
            highlightthickness=0,
            bd=0,
            cursor="",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        tk.Label(
            card,
            text="第 3 部分：已支持缩放、旋转、裁剪与灰度；格式转换将在第 4 部分加入。",
            bg=SURFACE,
            fg="#94A3B8",
            font=(self.font_family, 9),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=17, pady=(8, 12))

    def _build_sidebar(self, parent: tk.Widget) -> None:
        side = tk.Frame(parent, bg=BG)
        side.grid(row=0, column=1, sticky="nsew")

        self.notebook = ttk.Notebook(side)
        self.notebook.pack(fill="both", expand=True)

        self.info_tab = tk.Frame(self.notebook, bg=SURFACE, padx=18, pady=16)
        self.resize_tab = tk.Frame(self.notebook, bg=SURFACE, padx=18, pady=16)
        self.crop_tab = tk.Frame(self.notebook, bg=SURFACE, padx=18, pady=16)
        self.rotate_tab = tk.Frame(self.notebook, bg=SURFACE, padx=18, pady=16)
        self.notebook.add(self.info_tab, text="图片信息")
        self.notebook.add(self.resize_tab, text="缩放")
        self.notebook.add(self.crop_tab, text="裁剪")
        self.notebook.add(self.rotate_tab, text="旋转/灰度")

        self._build_info_tab()
        self._build_resize_tab()
        self._build_crop_tab()
        self._build_rotate_tab()
        self.notebook.select(self.info_tab)

    def _build_info_tab(self) -> None:
        tab = self.info_tab

        title_row = tk.Frame(tab, bg=SURFACE)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text="图片信息",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 12, "bold"),
        ).pack(side="left")
        self.info_state_var = tk.StringVar(value="未打开")
        self.info_state_badge = tk.Label(
            title_row,
            textvariable=self.info_state_var,
            bg=SURFACE_ALT,
            fg=MUTED,
            font=(self.font_family, 8),
            padx=8,
            pady=2,
        )
        self.info_state_badge.pack(side="right")

        tk.Label(
            tab,
            text="打开图片后自动读取；文件大小按 MB 显示，保留两位小数。",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=335,
            anchor="w",
        ).pack(fill="x", pady=(4, 12))

        self.info_vars = {
            "filename": tk.StringVar(value="—"),
            "format": tk.StringVar(value="—"),
            "width": tk.StringVar(value="—"),
            "height": tk.StringVar(value="—"),
            "mode": tk.StringVar(value="—"),
            "size": tk.StringVar(value="—"),
        }
        rows = [
            ("文件名", "filename"),
            ("图片格式", "format"),
            ("宽度", "width"),
            ("高度", "height"),
            ("颜色模式", "mode"),
            ("文件大小", "size"),
        ]

        grid = tk.Frame(tab, bg=SURFACE)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        for row_index, (label, key) in enumerate(rows):
            tk.Label(
                grid,
                text=label,
                bg=SURFACE,
                fg=MUTED,
                font=(self.font_family, 9),
                anchor="w",
                width=8,
            ).grid(row=row_index, column=0, sticky="nw", pady=4)
            tk.Label(
                grid,
                textvariable=self.info_vars[key],
                bg=SURFACE,
                fg=TEXT,
                font=(
                    self.font_family,
                    10,
                    "bold" if key in ("filename", "width", "height") else "normal",
                ),
                anchor="w",
                justify="left",
                wraplength=255 if key == "filename" else 0,
            ).grid(row=row_index, column=1, sticky="we", pady=4)

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=(12, 10))
        tk.Label(
            tab,
            text="文件位置",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(fill="x")
        self.info_path_var = tk.StringVar(value="—")
        tk.Label(
            tab,
            textvariable=self.info_path_var,
            bg=SURFACE_ALT,
            fg=MUTED,
            font=(self.font_family, 8),
            justify="left",
            anchor="w",
            wraplength=320,
            padx=9,
            pady=7,
        ).pack(fill="x", pady=(4, 8))

        self.info_note_var = tk.StringVar(
            value="打开图片后可进行等比缩放、精确缩放和旋转。"
        )
        tk.Label(
            tab,
            textvariable=self.info_note_var,
            bg=SURFACE,
            fg="#94A3B8",
            font=(self.font_family, 8),
            justify="left",
            wraplength=330,
            anchor="w",
        ).pack(fill="x")

    def _build_resize_tab(self) -> None:
        tab = self.resize_tab
        tk.Label(
            tab,
            text="按尺寸缩放",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            tab,
            text="至少填写一项；只填宽度或高度时，另一项按原图比例自动计算。",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=335,
            anchor="w",
        ).pack(fill="x", pady=(4, 10))

        self.resize_current_var = tk.StringVar(value="当前图片：—")
        tk.Label(
            tab,
            textvariable=self.resize_current_var,
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        form = tk.Frame(tab, bg=SURFACE)
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)

        self.resize_width_var = tk.StringVar()
        self.resize_height_var = tk.StringVar()
        for row_index, (label, variable) in enumerate(
            (("宽度", self.resize_width_var), ("高度", self.resize_height_var))
        ):
            tk.Label(
                form,
                text=label,
                bg=SURFACE,
                fg=TEXT,
                font=(self.font_family, 9),
                anchor="w",
                width=6,
            ).grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Entry(
                form, textvariable=variable, width=14, justify="right"
            ).grid(row=row_index, column=1, sticky="we", padx=(0, 7), pady=4)
            tk.Label(
                form,
                text="px",
                bg=SURFACE,
                fg=MUTED,
                font=(self.font_family, 9),
                width=2,
                anchor="w",
            ).grid(row=row_index, column=2, sticky="w", pady=4)

        self.resize_info_label = tk.Label(
            tab,
            text="输出尺寸：请填写宽度或高度",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=335,
        )
        self.resize_info_label.pack(fill="x", pady=(9, 10))
        self.resize_width_var.trace_add("write", lambda *_: self._update_resize_hint())
        self.resize_height_var.trace_add("write", lambda *_: self._update_resize_hint())

        self.resize_btn = ttk.Button(
            tab,
            text="应用缩放",
            style="Accent.TButton",
            command=self._apply_resize,
        )
        self.resize_btn.pack(fill="x")

        self._add_note_box(
            tab,
            "缩放说明",
            "只填一边时按原比例缩放，两边都填时精确缩放。\n"
            "放大不会增加真实细节，建议避免过度放大。",
        )

    def _entry_box(
        self,
        parent: tk.Widget,
        title: str,
        variable: tk.StringVar,
        row: int,
        column: int,
    ) -> None:
        box = tk.Frame(parent, bg=SURFACE)
        box.grid(
            row=row,
            column=column,
            sticky="ew",
            padx=(0, 8) if column == 0 else 0,
            pady=(0, 8),
        )
        box.grid_columnconfigure(0, weight=1)
        tk.Label(
            box,
            text=title,
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 3))
        ttk.Entry(box, textvariable=variable, width=9, justify="right").grid(
            row=1, column=0, sticky="ew"
        )

    def _build_crop_tab(self) -> None:
        tab = self.crop_tab
        tk.Label(
            tab,
            text="指定区域裁剪",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            tab,
            text="坐标从左上角 (0, 0) 开始。\n宽高单位为像素；也可直接在预览图上拖动框选。",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=335,
            anchor="w",
        ).pack(fill="x", pady=(4, 8))

        self.crop_current_var = tk.StringVar(value="当前图片：—")
        tk.Label(
            tab,
            textvariable=self.crop_current_var,
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(0, 7))

        self.crop_x_var = tk.StringVar()
        self.crop_y_var = tk.StringVar()
        self.crop_w_var = tk.StringVar()
        self.crop_h_var = tk.StringVar()

        form = tk.Frame(tab, bg=SURFACE)
        form.pack(fill="x")
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)
        self._entry_box(form, "X 坐标", self.crop_x_var, 0, 0)
        self._entry_box(form, "Y 坐标", self.crop_y_var, 0, 1)
        self._entry_box(form, "区域宽度", self.crop_w_var, 1, 0)
        self._entry_box(form, "区域高度", self.crop_h_var, 1, 1)

        self.crop_info_label = tk.Label(
            tab,
            text="选区：—",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
            justify="left",
            wraplength=335,
        )
        self.crop_info_label.pack(fill="x", pady=(2, 8))
        for var in (self.crop_x_var, self.crop_y_var, self.crop_w_var, self.crop_h_var):
            var.trace_add("write", lambda *_: self._update_crop_hint())

        button_row = tk.Frame(tab, bg=SURFACE)
        button_row.pack(fill="x")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)
        self.crop_btn = ttk.Button(
            button_row,
            text="应用裁剪",
            style="Accent.TButton",
            command=self._apply_crop,
        )
        self.crop_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.crop_all_btn = ttk.Button(
            button_row,
            text="全选图片",
            style="Secondary.TButton",
            command=self._select_full_crop,
        )
        self.crop_all_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._add_note_box(
            tab,
            "裁剪说明",
            "区域必须完全位于图片内，否则会阻止裁剪并提示越界。\n"
            "拖动框选后会自动切换到本页并填写坐标。",
        )

    def _build_rotate_tab(self) -> None:
        tab = self.rotate_tab
        tk.Label(
            tab,
            text="旋转图片",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            tab,
            text="按顺时针方向旋转；90° 与 270° 会交换宽高，画质不受影响。",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=335,
            anchor="w",
        ).pack(fill="x", pady=(4, 10))

        self.rotate_current_var = tk.StringVar(value="当前图片：—")
        tk.Label(
            tab,
            textvariable=self.rotate_current_var,
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        rotate_row = tk.Frame(tab, bg=SURFACE)
        rotate_row.pack(fill="x")
        for column_index in range(3):
            rotate_row.grid_columnconfigure(column_index, weight=1)

        self.rotate_buttons = []
        for index, angle in enumerate((90, 180, 270)):
            button = ttk.Button(
                rotate_row,
                text=f"↻ {angle}°",
                style="Soft.TButton",
                command=lambda value=angle: self._rotate(value),
            )
            button.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0, 6) if index < 2 else 0,
            )
            self.rotate_buttons.append(button)

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=(16, 13))
        tk.Label(
            tab,
            text="色彩调整",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 11, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            tab,
            text="将彩色图片转换为灰度图；带透明通道的图片会保留透明度。",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, 9),
            justify="left",
            wraplength=335,
            anchor="w",
        ).pack(fill="x", pady=(4, 9))

        self.grayscale_btn = ttk.Button(
            tab,
            text="转换为灰度图",
            style="Soft.TButton",
            command=self._apply_grayscale,
        )
        self.grayscale_btn.pack(fill="x")

        self._add_note_box(
            tab,
            "处理说明",
            "旋转使用无损转置，不会重新采样或损失画质。\n"
            "透明图片转灰度后以 LA 模式保留 alpha 通道，便于后续导出。",
        )

    def _add_note_box(self, parent: tk.Widget, title: str, text: str) -> None:
        box = tk.Frame(parent, bg=SURFACE_ALT, padx=11, pady=9)
        box.pack(fill="x", pady=(18, 0))
        tk.Label(
            box,
            text=title,
            bg=SURFACE_ALT,
            fg=ACCENT_DARK,
            font=(self.font_family, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            box,
            text=text,
            bg=SURFACE_ALT,
            fg=MUTED,
            font=(self.font_family, 8),
            justify="left",
            anchor="w",
            wraplength=315,
        ).pack(fill="x", pady=(4, 0))

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _event: self._shortcut(self._on_open))
        self.bind("<Control-z>", lambda _event: self._shortcut(self._on_undo))

    @staticmethod
    def _shortcut(callback) -> str:
        callback()
        return "break"

    def report_callback_exception(self, exc, value, tb) -> None:
        """兜底处理 Tk 回调中的未预期异常，避免程序直接退出。"""
        traceback.print_exception(exc, value, tb)
        try:
            messagebox.showerror(
                "程序错误",
                "操作过程中发生意外错误：\n"
                f"{value}\n\n"
                "程序仍可继续使用，请重试或换一张图片。",
                parent=self,
            )
        except Exception:
            pass

    # ----- 信息状态 -------------------------------------------------------

    def _refresh_info(self) -> None:
        doc = self.document
        if doc is None:
            for variable in self.info_vars.values():
                variable.set("—")
            self.info_state_var.set("未打开")
            self.info_state_badge.configure(bg=SURFACE_ALT, fg=MUTED)
            self.info_path_var.set("—")
            self.info_note_var.set("打开图片后可进行缩放、旋转、裁剪和灰度转换。")
            self.preview_badge_var.set("未打开图片")
            self.resize_current_var.set("当前图片：—")
            self.crop_current_var.set("当前图片：—")
            self.rotate_current_var.set("当前图片：—")
            self._update_resize_hint()
            self._update_crop_hint()
            return

        info = doc.info
        image = doc.image
        self.info_vars["filename"].set(info.filename)
        self.info_vars["format"].set(info.image_format)
        self.info_vars["width"].set(f"{image.width} px")
        self.info_vars["height"].set(f"{image.height} px")
        self.info_vars["mode"].set(describe_mode(image.mode))
        self.info_vars["size"].set(info.file_size_mb)
        self.info_path_var.set(str(info.path))
        if doc.is_modified:
            self.info_state_var.set(f"已编辑 · {doc.action_label}")
            self.info_state_badge.configure(bg=ACCENT_SOFT, fg=ACCENT_DARK)
        else:
            self.info_state_var.set("原图")
            self.info_state_badge.configure(bg=SURFACE_ALT, fg=MUTED)
        self.info_note_var.set(
            f"原图尺寸：{info.width} × {info.height} 像素；"
            "文件大小为原图大小，宽高和颜色模式显示当前结果。"
        )
        self.preview_badge_var.set(
            f"{doc.action_label} · {image.width} × {image.height} px · {image.mode}"
        )
        self.resize_current_var.set(f"当前图片：{image.width} × {image.height} px")
        self.crop_current_var.set(f"当前图片：{image.width} × {image.height} px")
        self.rotate_current_var.set(f"当前图片：{image.width} × {image.height} px")
        self._update_resize_hint()
        self._update_crop_hint()

    def _refresh_action_states(self) -> None:
        doc = self.document
        state = "normal" if doc is not None else "disabled"
        for button in (
            self.resize_btn,
            self.crop_btn,
            self.crop_all_btn,
            self.grayscale_btn,
            *self.rotate_buttons,
        ):
            button.configure(state=state)
        self.undo_btn.configure(
            state="normal" if doc is not None and doc.can_undo else "disabled"
        )
        self.reset_btn.configure(
            state="normal" if doc is not None and doc.is_modified else "disabled"
        )
        self.canvas.configure(cursor="crosshair" if doc is not None else "")

    def _update_resize_hint(self) -> None:
        if not hasattr(self, "resize_info_label"):
            return
        doc = self.document
        if doc is None:
            self.resize_info_label.configure(text="输出尺寸：—", fg=MUTED)
            return
        try:
            width = parse_optional_positive_int(self.resize_width_var.get(), "宽度")
            height = parse_optional_positive_int(self.resize_height_var.get(), "高度")
            if width is None and height is None:
                self.resize_info_label.configure(
                    text="输出尺寸：请填写宽度或高度", fg=MUTED
                )
                return
            new_width, new_height = calculate_resize_dimensions(
                doc.image.width, doc.image.height, width, height
            )
            suffix = "（等比）" if (width is None or height is None) else ""
            self.resize_info_label.configure(
                text=f"输出尺寸：{new_width} × {new_height} px {suffix}",
                fg=ACCENT,
            )
        except ValidationError as exc:
            self.resize_info_label.configure(text=str(exc), fg=DANGER)

    def _update_crop_hint(self) -> None:
        if not hasattr(self, "crop_info_label"):
            return
        doc = self.document
        if doc is None:
            self.crop_info_label.configure(text="选区：—", fg=MUTED)
            return
        try:
            x = parse_nonnegative_int(self.crop_x_var.get(), "X 坐标")
            y = parse_nonnegative_int(self.crop_y_var.get(), "Y 坐标")
            width = parse_positive_int(self.crop_w_var.get(), "裁剪宽度")
            height = parse_positive_int(self.crop_h_var.get(), "裁剪高度")
        except ValidationError:
            self.crop_info_label.configure(
                text="选区：请输入完整的裁剪参数", fg=MUTED
            )
            return

        if x + width > doc.image.width or y + height > doc.image.height:
            self.crop_info_label.configure(
                text="选区超出图片范围，请调整坐标或尺寸", fg=DANGER
            )
        else:
            self.crop_info_label.configure(
                text=f"选区：{width} × {height} px，右下角 ({x + width}, {y + height})",
                fg=MUTED,
            )

    def _reset_fields_for_document(self) -> None:
        self.resize_width_var.set("")
        self.resize_height_var.set("")
        if self.document is not None:
            width, height = self.document.image.size
            self.crop_x_var.set("0")
            self.crop_y_var.set("0")
            self.crop_w_var.set(str(width))
            self.crop_h_var.set(str(height))
        else:
            for variable in (
                self.crop_x_var,
                self.crop_y_var,
                self.crop_w_var,
                self.crop_h_var,
            ):
                variable.set("")
        self._update_resize_hint()
        self._update_crop_hint()

    def _commit_edit(self, new_image: Image.Image, label: str, message: str) -> None:
        doc = self.document
        if doc is None:
            return
        doc.apply(new_image, label)
        self._reset_fields_for_document()
        self._refresh_info()
        self._refresh_action_states()
        self._render_preview()
        self._set_status(message, "success")

    def _show_validation(self, exc: Exception, title: str = "参数错误") -> None:
        messagebox.showerror(title, str(exc), parent=self)
        self._set_status(str(exc).splitlines()[0], "error")

    def _apply_resize(self) -> None:
        doc = self.document
        if doc is None:
            return
        try:
            width = parse_optional_positive_int(self.resize_width_var.get(), "宽度")
            height = parse_optional_positive_int(self.resize_height_var.get(), "高度")
            if width is None and height is None:
                raise ValidationError("请至少填写宽度或高度。")
            old_width, old_height = doc.image.size
            new_image = resize_image(doc.image, width, height)
        except ValidationError as exc:
            self._show_validation(exc)
            return
        except Exception as exc:
            messagebox.showerror("缩放失败", f"无法完成缩放：\n{exc}", parent=self)
            self._set_status("缩放失败。", "error")
            return

        label = "等比缩放" if (width is None or height is None) else "精确缩放"
        self._commit_edit(
            new_image,
            label,
            f"{label}完成：{old_width} × {old_height} → "
            f"{new_image.width} × {new_image.height} 像素",
        )

    def _apply_crop(self) -> None:
        doc = self.document
        if doc is None:
            return
        try:
            x = parse_nonnegative_int(self.crop_x_var.get(), "X 坐标")
            y = parse_nonnegative_int(self.crop_y_var.get(), "Y 坐标")
            width = parse_positive_int(self.crop_w_var.get(), "裁剪宽度")
            height = parse_positive_int(self.crop_h_var.get(), "裁剪高度")
            old_width, old_height = doc.image.size
            new_image = crop_image(doc.image, x, y, width, height)
        except CropOutOfBoundsError as exc:
            messagebox.showerror("裁剪区域越界", str(exc), parent=self)
            self._set_status("裁剪区域超出图片范围，请重新设置。", "error")
            return
        except ValidationError as exc:
            self._show_validation(exc)
            return
        except Exception as exc:
            messagebox.showerror("裁剪失败", f"无法完成裁剪：\n{exc}", parent=self)
            self._set_status("裁剪失败。", "error")
            return

        self._commit_edit(
            new_image,
            "区域裁剪",
            f"裁剪完成：原图 {old_width} × {old_height}，"
            f"新图 {new_image.width} × {new_image.height} 像素",
        )

    def _select_full_crop(self) -> None:
        doc = self.document
        if doc is None:
            return
        width, height = doc.image.size
        self.crop_x_var.set("0")
        self.crop_y_var.set("0")
        self.crop_w_var.set(str(width))
        self.crop_h_var.set(str(height))
        self._set_status("已选中整张图片范围。")

    def _rotate(self, angle: int) -> None:
        doc = self.document
        if doc is None:
            return
        try:
            old_size = doc.image.size
            new_image = rotate_image(doc.image, angle)
        except ValidationError as exc:
            self._show_validation(exc)
            return
        except Exception as exc:
            messagebox.showerror("旋转失败", f"无法完成旋转：\n{exc}", parent=self)
            self._set_status("旋转失败。", "error")
            return

        self._commit_edit(
            new_image,
            f"旋转 {angle}°",
            f"旋转完成：{old_size[0]} × {old_size[1]} → "
            f"{new_image.width} × {new_image.height} 像素",
        )

    def _apply_grayscale(self) -> None:
        doc = self.document
        if doc is None:
            return
        if doc.image.mode in ("L", "LA"):
            messagebox.showinfo("无需转换", "当前图片已经是灰度图。", parent=self)
            self._set_status("当前图片已经是灰度图。")
            return
        try:
            new_image = to_grayscale(doc.image)
        except ValidationError as exc:
            self._show_validation(exc)
            return
        except Exception as exc:
            messagebox.showerror(
                "转换失败", f"无法转换为灰度图：\n{exc}", parent=self
            )
            self._set_status("灰度转换失败。", "error")
            return

        self._commit_edit(
            new_image,
            "灰度转换",
            f"已转换为灰度图，颜色模式：{describe_mode(new_image.mode)}",
        )

    def _on_undo(self) -> None:
        doc = self.document
        if doc is None or not doc.can_undo:
            return
        undone = doc.undo()
        self._reset_fields_for_document()
        self._refresh_info()
        self._refresh_action_states()
        self._render_preview()
        self._set_status(
            f"已撤销：{undone or '上一步'}。当前：{doc.action_label}。",
            "success",
        )

    def _on_reset(self) -> None:
        doc = self.document
        if doc is None or not doc.is_modified:
            return
        if not messagebox.askyesno(
            "还原原图",
            "确定放弃当前所有编辑，恢复到打开时的原图吗？",
            icon="warning",
            parent=self,
        ):
            return
        doc.reset()
        self._reset_fields_for_document()
        self._refresh_info()
        self._refresh_action_states()
        self._render_preview()
        self._set_status("已还原为原图。", "success")

    def _set_status(self, text: str, kind: str = "info") -> None:
        colors = {"info": MUTED, "success": SUCCESS, "error": DANGER}
        self.status_var.set(text)
        self.status_label.configure(fg=colors.get(kind, MUTED))

    # ----- 打开图片 -------------------------------------------------------

    def _on_open(self) -> None:
        path = filedialog.askopenfilename(
            title="打开图片",
            filetypes=OPEN_FILETYPES,
            parent=self,
        )
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> None:
        """加载指定路径（也供命令行参数调用）。"""
        try:
            document = ImageDocument.from_file(path)
        except ImageEditorError as exc:
            messagebox.showerror("打开失败", str(exc), parent=self)
            self._set_status("打开图片失败，请检查文件。", "error")
            return
        except Exception as exc:
            messagebox.showerror(
                "打开失败", f"发生意外错误，无法打开图片：\n{exc}", parent=self
            )
            self._set_status("打开图片时发生意外错误。", "error")
            return

        self.document = document
        self.title(f"{APP_TITLE} · {document.info.filename}")
        self._reset_fields_for_document()
        self._refresh_info()
        self._refresh_action_states()
        self.notebook.select(self.info_tab)
        self._render_preview()
        self._set_status(
            f"已打开：{document.info.filename}（{document.info.size_text}，"
            f"{describe_mode(document.info.mode)}）",
            "success",
        )

    # ----- 预览 -----------------------------------------------------------

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        self._preview_geom = None
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._render_job = self.after(90, self._render_preview)

    def _draw_placeholder(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 2)
        height = max(self.canvas.winfo_height(), 2)
        self.canvas.create_text(
            width / 2,
            height / 2 - 30,
            text="尚未打开图片",
            fill="#A5ADBC",
            font=(self.font_family, 17, "bold"),
        )
        self.canvas.create_text(
            width / 2,
            height / 2 + 16,
            text="点击右上角“打开图片”，或按 Ctrl+O\n支持 PNG / JPG / BMP / WebP / TIFF / GIF",
            fill="#727A88",
            font=(self.font_family, 9),
            justify="center",
        )
        self.canvas.create_rectangle(
            max(20, width / 2 - 220),
            max(20, height / 2 - 110),
            min(width - 20, width / 2 + 220),
            min(height - 20, height / 2 + 110),
            outline="#343844",
            dash=(5, 5),
        )

    def _render_preview(self) -> None:
        self._render_job = None
        self._crop_drag_start = None
        self._crop_rect_id = None
        self.canvas.delete("all")
        self._preview_photo = None
        self._preview_geom = None

        doc = self.document
        if doc is None:
            self._draw_placeholder()
            return

        canvas_w = max(self.canvas.winfo_width(), 2)
        canvas_h = max(self.canvas.winfo_height(), 2)
        margin = 22
        available_w = max(canvas_w - margin * 2, 1)
        available_h = max(canvas_h - margin * 2, 1)
        image = doc.image
        scale = min(
            available_w / image.width,
            available_h / image.height,
            1.0,
        )
        display_w = max(1, int(round(image.width * scale)))
        display_h = max(1, int(round(image.height * scale)))

        try:
            if has_alpha(image):
                rgba = image.convert("RGBA")
                thumbnail = rgba.resize(
                    (display_w, display_h), Image.Resampling.LANCZOS
                )
                board = make_checkerboard(thumbnail.size)
                board.paste(thumbnail, mask=thumbnail.getchannel("A"))
                display = board
            else:
                display = image.convert("RGB")
                if display.size != (display_w, display_h):
                    display = display.resize(
                        (display_w, display_h), Image.Resampling.LANCZOS
                    )
            photo = ImageTk.PhotoImage(display)
        except Exception as exc:
            self.canvas.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text=f"无法生成预览：\n{exc}",
                fill="#FCA5A5",
                font=(self.font_family, 10),
                justify="center",
            )
            self._set_status("无法生成图像预览，但仍可读取图片信息。", "error")
            return

        x = (canvas_w - display_w) // 2
        y = (canvas_h - display_h) // 2
        self.canvas.create_image(x, y, image=photo, anchor="nw")
        self.canvas.create_rectangle(
            x,
            y,
            x + display_w,
            y + display_h,
            outline="#3A4050",
            width=1,
        )
        self._preview_photo = photo
        self._preview_geom = (x, y, display_w, display_h, display_w / image.width)

    def _point_to_image(self, x: float, y: float) -> Tuple[float, float]:
        if self._preview_geom is None:
            raise ValidationError("预览尚未准备好。")
        origin_x, origin_y, display_w, display_h, scale = self._preview_geom
        x = min(max(x, origin_x), origin_x + display_w)
        y = min(max(y, origin_y), origin_y + display_h)
        return (x - origin_x) / scale, (y - origin_y) / scale

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self.document is None or self._preview_geom is None:
            return
        origin_x, origin_y, display_w, display_h, _ = self._preview_geom
        if not (
            origin_x <= event.x <= origin_x + display_w
            and origin_y <= event.y <= origin_y + display_h
        ):
            return
        self._crop_drag_start = (event.x, event.y)
        if self._crop_rect_id is not None:
            self.canvas.delete(self._crop_rect_id)
        self._crop_rect_id = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#38BDF8",
            width=2,
            dash=(5, 3),
        )

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self._crop_drag_start is None or self._crop_rect_id is None:
            return
        if self._preview_geom is None:
            return
        origin_x, origin_y, display_w, display_h, _ = self._preview_geom
        start_x, start_y = self._crop_drag_start
        current_x = min(max(event.x, origin_x), origin_x + display_w)
        current_y = min(max(event.y, origin_y), origin_y + display_h)
        self.canvas.coords(
            self._crop_rect_id, start_x, start_y, current_x, current_y
        )

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self._crop_drag_start is None or self._crop_rect_id is None:
            return
        start_x, start_y = self._crop_drag_start
        end_x, end_y = event.x, event.y
        self._crop_drag_start = None

        if abs(end_x - start_x) < 3 or abs(end_y - start_y) < 3:
            self.canvas.delete(self._crop_rect_id)
            self._crop_rect_id = None
            return
        if self._preview_geom is None or self.document is None:
            return

        left_canvas, right_canvas = sorted((start_x, end_x))
        top_canvas, bottom_canvas = sorted((start_y, end_y))
        left_f, top_f = self._point_to_image(left_canvas, top_canvas)
        right_f, bottom_f = self._point_to_image(right_canvas, bottom_canvas)

        image_width, image_height = self.document.image.size
        left = max(0, min(image_width - 1, int(math.floor(left_f))))
        top = max(0, min(image_height - 1, int(math.floor(top_f))))
        right = max(left + 1, min(image_width, int(math.ceil(right_f))))
        bottom = max(top + 1, min(image_height, int(math.ceil(bottom_f))))

        self.crop_x_var.set(str(left))
        self.crop_y_var.set(str(top))
        self.crop_w_var.set(str(right - left))
        self.crop_h_var.set(str(bottom - top))
        self.notebook.select(self.crop_tab)
        self._set_status(
            f"已框选区域：x={left}, y={top}, 宽={right - left}, 高={bottom - top}。"
            "确认后点击“应用裁剪”。"
        )


def main() -> None:
    app = ImageEditorApp()
    if len(sys.argv) > 1:
        initial_path = sys.argv[1]
        app.after(150, lambda: app.load_path(initial_path))
    app.mainloop()


if __name__ == "__main__":
    main()
