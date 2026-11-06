#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片信息与编辑器 —— 重写第 1 部分。

本阶段只实现：
    * 打开并校验图片；
    * 读取文件名、格式、宽高、颜色模式和文件大小；
    * 图片预览与基础错误提示；
    * 为后续编辑功能预留界面框架。

缩放、裁剪、旋转、灰度、保存和格式转换将在后续分支中逐步补全。

运行：
    python image_editor.py
"""

from __future__ import annotations

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
PART_LABEL = "PART 1 / 4"

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


class ImageDocument:
    """第 1 部分只保存当前图像和信息，编辑历史将在后续部分加入。"""

    def __init__(self, image: Image.Image, info: ImageInfo) -> None:
        self.image = image
        self.info = info
        self.path = info.path

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "ImageDocument":
        image, info = load_image_file(path)
        return cls(image, info)


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
    """第 1 部分主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.configure(bg=BG)
        self.minsize(980, 680)

        self.document: ImageDocument | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._render_job: str | None = None

        self._setup_fonts()
        self._setup_styles()
        self._set_window_icon()
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_info()
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
            text="Ctrl+O 打开图片",
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
            text="阶段 1 · 打开图片并读取基本信息",
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

        tk.Label(
            card,
            text="第 1 部分：读取文件信息并预览图片；编辑功能将在后续合并中加入。",
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
        self.progress_tab = tk.Frame(self.notebook, bg=SURFACE, padx=18, pady=16)
        self.notebook.add(self.info_tab, text="图片信息")
        self.notebook.add(self.progress_tab, text="开发进度")

        self._build_info_tab()
        self._build_progress_tab()
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
            value="当前阶段只读取信息，不会修改原图。"
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

    def _build_progress_tab(self) -> None:
        tab = self.progress_tab
        tk.Label(
            tab,
            text="重写进度",
            bg=SURFACE,
            fg=TEXT,
            font=(self.font_family, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            tab,
            text=PART_LABEL,
            bg=ACCENT_SOFT,
            fg=ACCENT_DARK,
            font=(self.font_family, 8, "bold"),
            padx=8,
            pady=2,
            anchor="w",
        ).pack(fill="x", pady=(6, 12))

        items = [
            ("已完成", "打开图片与错误处理", True),
            ("已完成", "文件名 / 格式 / 宽高 / 颜色模式 / 大小", True),
            ("待实现", "缩放、旋转与撤销", False),
            ("待实现", "裁剪、灰度与透明通道", False),
            ("待实现", "格式转换、原图保护与完整测试", False),
        ]
        for status, text, done in items:
            row = tk.Frame(tab, bg=SURFACE)
            row.pack(fill="x", pady=5)
            tk.Label(
                row,
                text="✓" if done else "○",
                bg=SURFACE,
                fg=SUCCESS if done else "#94A3B8",
                font=(self.font_family, 10, "bold"),
                width=2,
                anchor="w",
            ).pack(side="left")
            tk.Label(
                row,
                text=text,
                bg=SURFACE,
                fg=TEXT if done else MUTED,
                font=(self.font_family, 9),
                anchor="w",
                justify="left",
                wraplength=275,
            ).pack(side="left", fill="x", expand=True)

        note = tk.Frame(tab, bg=SURFACE_ALT, padx=11, pady=9)
        note.pack(fill="x", pady=(18, 0))
        tk.Label(
            note,
            text="说明",
            bg=SURFACE_ALT,
            fg=ACCENT_DARK,
            font=(self.font_family, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            note,
            text=(
                "这是重写计划的第 1 部分，只包含图片加载与信息展示。\n"
                "后续分支会依次补全编辑能力，最后通过 Git 合并并运行完整测试。"
            ),
            bg=SURFACE_ALT,
            fg=MUTED,
            font=(self.font_family, 8),
            justify="left",
            anchor="w",
            wraplength=310,
        ).pack(fill="x", pady=(4, 0))

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _event: self._shortcut(self._on_open))

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
            self.info_note_var.set("当前阶段只读取信息，不会修改原图。")
            self.preview_badge_var.set("未打开图片")
            return

        info = doc.info
        self.info_vars["filename"].set(info.filename)
        self.info_vars["format"].set(info.image_format)
        self.info_vars["width"].set(f"{info.width} px")
        self.info_vars["height"].set(f"{info.height} px")
        self.info_vars["mode"].set(describe_mode(info.mode))
        self.info_vars["size"].set(info.file_size_mb)
        self.info_path_var.set(str(info.path))
        self.info_state_var.set("原图")
        self.info_state_badge.configure(bg=SURFACE_ALT, fg=MUTED)
        self.info_note_var.set(
            f"原图尺寸：{info.width} × {info.height} 像素；"
            "编辑功能将在后续部分加入。"
        )
        self.preview_badge_var.set(
            f"原图 · {info.width} × {info.height} px · {info.mode}"
        )

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
        self._refresh_info()
        self.notebook.select(self.info_tab)
        self._render_preview()
        self._set_status(
            f"已打开：{document.info.filename}（{document.info.size_text}，"
            f"{describe_mode(document.info.mode)}）",
            "success",
        )

    # ----- 预览 -----------------------------------------------------------

    def _on_canvas_configure(self, _event: tk.Event) -> None:
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
        self.canvas.delete("all")
        self._preview_photo = None

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


def main() -> None:
    app = ImageEditorApp()
    if len(sys.argv) > 1:
        initial_path = sys.argv[1]
        app.after(150, lambda: app.load_path(initial_path))
    app.mainloop()


if __name__ == "__main__":
    main()
