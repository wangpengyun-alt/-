# 图片信息与编辑器

一个使用 **Python + Tkinter + Pillow** 编写的桌面图片查看与简单编辑工具。打开图片后会显示文件名、格式、宽高、颜色模式和文件大小，并支持缩放、裁剪、旋转、灰度转换与格式转换。所有编辑结果只能另存为新文件，原图不会被覆盖。

![程序界面](screenshots/app_info.png)

## 功能

- **读取图片信息**：文件名、图片格式、宽度、高度、颜色模式，以及按 MB 显示且保留两位小数的文件大小。
- **缩放**：
  - 只填写宽度或高度时，另一项按原图比例自动计算；
  - 同时填写宽度和高度时，精确缩放到指定尺寸；
  - 输入框下方实时显示预计输出尺寸。
- **裁剪**：
  - 输入 `X`、`Y`、区域宽度和高度；
  - 也可以直接在左侧预览图上按住鼠标拖动框选；
  - 区域越界时，输入区会变红提示，点击裁剪时还会弹出明确的错误对话框。
- **旋转**：支持顺时针 90°、180°、270° 旋转；90°/270° 会自动交换宽高。
- **灰度转换**：彩色图片转换为灰度图；带透明通道的图片会以 `LA` 模式保留透明度。
- **格式转换**：在“输出格式”下拉框中选择 PNG、JPG/JPEG、WebP、BMP、TIFF，再另存为新文件。
- **原图保护**：若选择原文件路径保存，程序会拒绝并提示更换文件名。
- **透明通道处理**：带透明通道的 PNG 保存为 JPG 时，会先把透明区域合成到白色背景，再转换为 RGB，避免出现黑底。
- **撤销/还原**：支持撤销最近若干步编辑，或一键恢复为打开时的原图。
- **错误提示**：文件不存在、文件不是有效图片、参数非法、裁剪越界、保存失败等情况均通过对话框提示，不会直接崩溃。

透明通道在预览中以棋盘格显示，转换为 JPG 时会自动合成白底：

![透明通道预览](screenshots/app_transparent.png)

## 环境要求

- Python 3.10 或更高版本
- Pillow 10.0 或更高版本
- Tkinter（Windows 官方 Python 安装包默认自带）

安装依赖：

```bash
pip install -r requirements.txt
```

> Linux 如果提示缺少 Tkinter，请安装系统包，例如 Ubuntu/Debian：`sudo apt install python3-tk`。

## 运行

### Windows 一键运行（推荐）

直接双击项目中的 `run.bat`。

启动脚本会自动查找可用的 Python 和 Pillow；如果电脑没有安装 Python，会尝试使用当前工作区自带的 Python 运行时。缺少依赖时，脚本会给出安装提示，不会一闪而过。

也可以在 PowerShell 中运行：

```powershell
cd "C:\Users\Admin1\Documents\deepseek-harness\default-workspace"
.\run.bat
```

### 使用已安装的 Python

```bash
python image_editor.py
```

也可以启动时直接打开一张图片：

```bash
python image_editor.py "samples/demo.jpg"
```

## 使用说明

1. 点击右上角 **打开图片**（或按 `Ctrl+O`），选择 PNG、JPG、BMP、WebP、TIFF、GIF 等图片。
2. 在 **图片信息** 标签页查看文件信息。
3. 切换到对应标签页进行编辑：
   - **缩放**：填写宽度或高度，至少填写一项，然后点击“应用缩放”。
   - **裁剪**：填写坐标与宽高，或在预览图上拖动框选，然后点击“应用裁剪”。
   - **旋转/灰度**：点击角度按钮，或点击“转换为灰度图”。
4. 在 **导出 / 格式转换** 区选择输出格式，点击 **另存为新文件…**（或按 `Ctrl+S`），再选择保存位置。
5. 保存成功后会弹窗显示完整保存路径；原图不会被修改。

### 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+O` | 打开图片 |
| `Ctrl+S` | 另存为新文件 |
| `Ctrl+Z` | 撤销上一步编辑 |

## 项目结构

```text
.
├── image_editor.py          # 主程序：核心逻辑 + Tkinter 图形界面
├── run.bat                  # Windows 一键启动脚本
├── test_image_editor.py     # 核心功能单元测试（23 项）
├── requirements.txt         # 第三方依赖
├── .gitignore               # 排除缓存、虚拟环境和程序输出
├── README.md
├── samples/
│   ├── demo.jpg             # 演示图片
│   └── transparent.png      # 透明通道演示图片
└── screenshots/
    ├── app_info.png         # 主界面截图
    └── app_transparent.png  # 透明通道预览截图
```

## 测试

运行核心功能测试：

```bash
python -m unittest -v test_image_editor.py
```

测试覆盖图片信息读取、文件不存在/无效图片、等比与精确缩放、参数校验、裁剪越界、三种旋转、灰度与透明通道、PNG/JPG 互转、JPG 透明区域白底合成、原图覆盖保护等。

## 实现说明

- **界面与核心分离**：`ImageDocument` 保存原图、当前状态和撤销历史；缩放、裁剪、旋转、灰度、保存等函数均为独立函数，便于测试和复用。
- **缩放**：只传一个边长给 `calculate_resize_dimensions()` 时按比例取整计算另一边；两边都给时使用指定尺寸。
- **旋转**：映射到 Pillow 的 `transpose()` 操作，90°/270° 使用无损转置，不进行重采样。
- **灰度**：普通彩色图使用 `ImageOps.grayscale()`；如果原图有透明通道，则合并灰度通道与 alpha 通道为 `LA`，以保留透明度。
- **保存**：先写入同目录临时文件，成功后用 `os.replace()` 替换目标文件，避免保存失败时留下损坏的半成品。
- **JPG 透明处理**：通过 alpha 通道将图片合成到白色背景，避免透明像素被保存成黑色。
- **原图保护**：在保存前比较目标路径与原图路径；即使目标路径写成大小写不同、相对路径或符号链接，也会尽量识别为同一个文件并拒绝覆盖。
- **EXIF 方向**：打开 JPEG 时会应用 EXIF 方向信息，预览和尺寸与图片的实际显示方向一致。

## 上传到 Git

项目已包含 `.gitignore`，不会提交 `__pycache__`、虚拟环境和编辑输出文件。

在 Windows 上先安装 Git：

```powershell
winget install --id Git.Git -e --source winget
```

重新打开 PowerShell，然后初始化仓库并提交：

```powershell
cd "C:\Users\Admin1\Documents\deepseek-harness\default-workspace"
git init
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
git add .
git commit -m "feat: Python 图片信息与编辑器"
git branch -M main
```

在 GitHub 或 Gitee 上新建一个**空仓库**，复制仓库地址，然后推送：

```powershell
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

首次推送时按提示登录 GitHub/Gitee；如果使用 GitHub 密码认证失败，请使用 Personal Access Token 作为密码。

