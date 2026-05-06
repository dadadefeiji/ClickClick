```markdown
# ImgClickFlow

> 图像识别 + 流程编排 —— 让 Windows 办公自动化像写文章一样简单

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](https://www.microsoft.com/windows)

**作者知乎**：[https://www.zhihu.com/people/mhaksy](https://www.zhihu.com/people/mhaksy)

---

## 📌 简介

ImgClickFlow 是一款基于 OpenCV 图像识别和 Windows API 的办公自动化工具。你只需将按钮截图放入 `templates` 文件夹，即可通过简单的 Python 代码实现**找图点击、键盘输入、流程编排、定时任务**等功能。

无需编程基础，复制、粘贴、改参数即可使用。无论你是想自动化处理报表、批量填写表单，还是定时执行重复操作，ImgClickFlow 都能让你用最少的代码完成任务。

---

## ✨ 六大核心优势

| 优势 | 说明 |
|------|------|
| **🖥️ DPI 自适应** | 自动检测屏幕缩放系数（100%/125%/150%），图像匹配与点击在统一物理坐标系下完成。**一次编写，百台电脑通用**。 |
| **🎯 智能去重** | 内置非极大值抑制（NMS）算法，自动合并半径 5 像素内的邻近匹配点，避免同一按钮被重复点击（弹窗、提交等）。 |
| **⏱️ 零负担等待** | 图像识别方法自带超时与重试机制，无需手动编写 `while` 循环。支持等待元素**出现**或**消失**，让工作流代码极其简洁。 |
| **🔁 批量识别 → 批量循环** | `auto.find_all()` 一行代码返回屏幕上所有匹配目标的坐标列表。配合流程引擎的 `.for_data()`，轻松实现“找到几个就处理几个”的批量自动化。 |
| **📝 链式流程编排** | `auto.do()` 链式 API 将点击、输入、等待、条件分支、循环、重试串联成可读性极强的流式代码。纯线性编写，无需嵌套回调。 |
| **📸 操作自动截图** | **默认开启**的调试录像功能：每一步操作前自动截屏，并在图上标记点击位置（红圈）或匹配区域（红框），右下角嵌入任务名、时间戳与代码水印，形成完整的操作证据链。 |

---

## 📸 操作自动截图（调试录像）

### 为什么需要它？

传统自动化脚本是“黑盒”——运行时你不知道它准备点击哪里、图像识别是否找对了目标。当脚本交给非技术人员使用或出现异常时，排查极其困难。

操作自动截图功能**默认开启**，为每一步操作**执行前**自动截取全屏，并在图片上添加**红色标记**和**水印**，让你一目了然：

- 🔴 **红色圆圈**：标注鼠标即将点击的**屏幕坐标**（如 `auto.click(x, y)` 触发）。
- 🔴 **红色方框**：标注图像识别匹配到的**模板区域**（如 `auto.click("按钮名")` 触发）。
- 📝 **右下角水印**：显示 `[任务名] 时间戳 操作代码`，失败截图额外标出 `[失败]`。

一张图即可回答：“在哪个任务、何时、在哪里（红圈/红框）、要执行什么操作”。

### 视觉标记说明

| 标记类型 | 触发条件 | 样式 | 用途 |
|---------|---------|------|------|
| 🔴 红色圆圈 | 鼠标点击屏幕坐标 | 红色空心圆，圆心为点击坐标 | 确认点击位置是否准确 |
| 🔴 红色方框 | 图像识别匹配到模板 | 红色矩形框，框住匹配到的模板区域 | 验证找图是否正确，有无找错地方 |

标记直接绘制在截图上，不影响实际点击操作。仅在调试录像开启时生效。

### 智能存储管理

| 场景 | 行为 |
|------|------|
| **脚本执行中** | 实时清理：每次截图后自动检查数量，超过上限即删除最早的截图，磁盘占用始终可控 |
| **脚本成功** | 最终仅保留最后 **15 张**截图（可配置，最大 100 张） |
| **脚本失败** | **完整保留**本次全部截图 + 一张失败现场截图 + `error_summary.txt` 摘要 |
| **时间兜底** | 每次启动时自动清理超过 **7 天**的所有记录 |
| **失败容量控制** | 最多保留最近 **5 个**失败任务的完整记录 |

> 即使脚本中途崩溃，实时清理机制也能保证磁盘不会堆积大量截图文件。

### 如何关闭或调整

**默认开启**，无需任何配置即可直接使用。如需关闭或修改参数，在自己的脚本中设置 `auto.recorder` 属性：

```python
from imgclickflow import auto

# 关闭自动截图
auto.recorder.enabled = False

# 调整成功时保留张数（默认 15，最大 100）
auto.recorder.max_screenshots = 30

# 调整清理天数（默认 7 天）
auto.recorder.max_age_days = 14
```

### 典型用法

```python
from imgclickflow import auto

# 默认已开启录像，直接写操作即可，截图自动保存
auto.click("财务软件图标")
auto.wait("登录界面", timeout=10)
auto.write("admin")
auto.click("导出报表")
# 运行结束后，[脚本名]_操作截屏 文件夹下会自动生成截图
```

如果需要自定义任务名称或显式标记成功/失败，可调用以下**可选方法**：

```python
from imgclickflow import auto

# （可选）自定义任务名
auto.recorder.start(task_name="财务月报导出")

try:
    auto.click("导出报表")
    # ... 更多步骤 ...

    # （可选）显式标记成功，触发成功保留策略
    auto.recorder.success()
except Exception as e:
    # （可选）显式标记失败，生成错误摘要并保留全部截图
    auto.recorder.failure(str(e))
    raise
```

**不调用 `start()`、`success()`、`failure()` 完全没问题**，脚本会自动以文件名作为任务名，并根据运行结果执行默认存储策略。

---

## 🚀 10秒快速上手

1. **复制本脚本**到任意文件夹（支持中文路径）。
2. **准备好按钮截图**（详情见下方「截图准备」）并放入 `templates` 文件夹。
3. **写一行代码**并运行：

```python
from imgclickflow import auto
auto.click("按钮名称")   # 自动找图并点击中心
```
首次运行会自动安装依赖包（opencv-python、numpy、Pillow、pywin32），请保持网络畅通。

---

## 📸 截图准备与模板配置（必读）

图像识别的关键是一张清晰、不变形、只包含按钮本体的模板图片。请按以下步骤操作：

### 1. 创建 templates 文件夹
在与 `imgclickflow.py` 脚本相同的目录下手动创建一个名为 `templates` 的文件夹。脚本运行时会自动检查，若不存在会自动创建。

### 2. 获取按钮截图（推荐三种方式）

| 方式 | 说明 |
|------|------|
| 方法一：`auto.capture()` 自动截图 | 运行 `auto.capture("按钮名称")`，脚本会截取全屏并提示你用画图工具裁剪到只剩按钮，然后保存到 `templates` 文件夹。推荐新手使用。 |
| 方法二：手动截图 | 按 `Win+Shift+S` 或使用微信/QQ截图，只截取按钮区域，保存为 PNG 文件，放入 `templates` 文件夹。 |
| 方法三：从设计稿直接获取 | 如果有 UI 切图，直接保存为 PNG 格式放入 `templates` 文件夹。 |

### 3. 模板图片的要求
- 格式必须为 **PNG**（不支持 JPG/BMP，因为 JPG 压缩会改变像素导致匹配失败）。
- 文件名不带扩展名，例如按钮上文字是“保存”，则保存为 `保存.png`，调用时写作 `auto.click("保存")`。
- 只截取按钮本体，不要包含周围背景或其它文字。越小越独特，匹配越快越准。
- 如果按钮在不同状态下颜色会变，建议截取最常用的状态。

### 4. 验证模板是否可用
运行 `auto.check_templates()` 可以检查所有模板是否能在当前屏幕上正常识别到。如果显示“未找到”，请检查截图是否准确，或者降低相似度（见后文 API 参数）。

---

## 📁 文件结构

```
你的工作目录/
├── imgclickflow.py        # 主脚本（可改名）
├── templates/             # 按钮截图（PNG）存放处 —— 必须手动创建
├── [脚本名]_操作截屏/      # 操作自动截图（默认开启，自动生成）
├── logs/                  # 运行日志（自动生成）
├── screenshots_author/    # 手动/流程截图保存（自动生成）
├── error_snapshots/       # 识别失败时自动截图（自动生成）
└── reports/               # HTML 执行报告（由 debug.report 生成）
```

---

## ⚙️ 配置参数（修改脚本中的 Config 类）

所有可调参数都在脚本开头的 `Config` 类中，可直接修改：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `template_dir` | `"templates"` | 模板截图存放文件夹 |
| `log_dir` | `"logs"` | 运行日志文件夹 |
| `screenshot_dir` | `"screenshots_author"` | 用户主动截图保存路径（`snap`等方法） |
| `error_dir` | `"error_snapshots"` | 识别失败时自动截图保存路径 |
| `default_similarity` | `0.9` | 图像匹配相似度（0~1，越高越严格） |
| `default_timeout` | `10` | 找图默认超时时间（秒） |
| `retry_interval` | `0.2` | 找图失败重试间隔（秒） |
| `post_click_delay` | `0.3` | 点击后等待界面反应的时间（秒） |
| `dedup_radius` | `5` | 去重半径（像素），合并邻近匹配点 |
| `verbose_log` | `True` | 是否打印详细日志 |

### 录像专属配置（通过 `auto.recorder` 设置）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `auto.recorder.enabled` | `True` | 自动截图总开关 |
| `auto.recorder.max_screenshots` | `15` | 成功时保留张数（硬上限 100） |
| `auto.recorder.max_age_days` | `7` | 自动清理超过此天数的记录 |

---

## 📖 API 速查表

### 1. 鼠标操作

| 方法 | 说明 | 示例 |
|------|------|------|
| `auto.move(x, y)` / `auto.moveto(x, y)` | 移动鼠标到逻辑坐标 | `auto.move(500, 300)` |
| `auto.click()` | 左键单击（三种用法） | `auto.click("保存")` / `auto.click(100,200)` / `auto.click()` |
| `auto.dclick()` | 双击（用法同上） | `auto.dclick("文件")` |
| `auto.rclick()` | 右键单击（用法同上） | `auto.rclick("菜单")` |
| `auto.click_multi("图片"/x,y, k=5, wait=0.2)` | **多次左键点击**（必须显式指定次数和间隔） | `auto.click_multi("确认", k=5, wait=0.2)` |
| `auto.click_seq(targets, wait=0.2)` | **依次点击多个目标**（列表可为图片名或坐标） | `auto.click_seq(["登录","确定"])` |
| `auto.drag(x1,y1,x2,y2)` | 平滑拖拽 | `auto.drag(100,100,500,400)` |
| `auto.scroll(direction, clicks=3, x=None, y=None)` | **鼠标滚轮滚动** | `auto.scroll('down', clicks=5)` |
| `auto.pos()` | 实时显示鼠标坐标（Ctrl+C 停止） | `auto.pos()` |

### 2. 键盘操作

| 方法 | 说明 | 示例 |
|------|------|------|
| `auto.write(text, times=1)` | 粘贴文本（支持中文，通过剪贴板+Ctrl+V） | `auto.write("已完成")` |
| `auto.press(key, times=1)` | 按下并释放单个键 | `auto.press("enter", 2)` |
| `auto.hotkey(k1,k2,...)` | 按下组合键 | `auto.hotkey("ctrl","v")` |
| `auto.press_sequence(*keys)` | 依次按下多个键 | `auto.press_sequence("a","b","c")` |

常用键名（不区分大小写）：
`enter` `tab` `esc` `spacebar` `backspace` `del` `ins` `F1`~`F12`
`up_arrow` `down_arrow` `left_arrow` `right_arrow`
`ctrl` `alt` `shift` `left_win` `right_win`
`numpad_0`~`numpad_9` `0`~`9` `a`~`z`
`+` `-` `.` `,` `/` `;` `[` `\` `]` `'` `` ` ``

### 3. 图像识别

| 方法 | 说明 | 示例 |
|------|------|------|
| `auto.find("按钮名", timeout=None, similarity=None, rect=None)` | 返回坐标 (x,y) 或 (-1,-1) | `x, y = auto.find("确定")` |
| `auto.find_all("按钮名", ...)` | 返回所有匹配坐标列表 | `points = auto.find_all("图标")` |
| `auto.wait("按钮名", timeout=30)` | 等待图片出现，成功返回 True | `auto.wait("加载完成", 60)` |
| `auto.wait_not("按钮名", timeout=30)` | 等待图片消失，成功返回 True | `auto.wait_not("loading")` |

可选参数说明：
- `timeout`：超时秒数，默认 `Config.default_timeout`
- `similarity`：匹配相似度（0~1），默认 `Config.default_similarity`
- `rect`：限定搜索区域，格式 `(left, top, width, height)`（逻辑坐标）

### 4. 流程引擎（链式调用）

创建流程：`auto.do()` → 添加步骤 → 最后 `.run()` 执行。

**基础步骤**

| 方法 | 说明 |
|------|------|
| `.click(目标)` | 点击（图片名或坐标） |
| `.dclick(目标)` | 双击 |
| `.rclick(目标)` | 右键 |
| `.click_multi(目标, k=次数, wait=间隔)` | **多次左键点击**（k、wait 必须显式指定） |
| `.click_seq(列表, wait=0.2)` | **依次点击多个目标** |
| `.moveto(x, y)` | **移动鼠标到坐标** |
| `.drag(x1, y1, x2, y2, duration=0.5)` | **拖拽** |
| `.scroll(direction, clicks=3, x, y)` | **鼠标滚轮** |
| `.snap(note="")` | **截取屏幕并保存** |
| `.write(文本)` | 粘贴文本 |
| `.press(键名, times=1)` | 按键 |
| `.hotkey(k1,k2,...)` | 组合键 |
| `.wait(目标, timeout=None)` | 等待出现 |
| `.wait_not(目标, timeout=None)` | 等待消失 |
| `.pause(秒数)` | 暂停 |
| `.retry(次数, wait=1)` | 设置整个流程失败重试 |

**条件分支**

```python
.if_see(目标)         # 如果看到则执行后续
.else_do()            # 否则执行后续
.endif()              # 结束条件块

.if_not_see(目标)     # 如果没有看到则执行后续
```

**循环**

```python
.for_data(列表)       # 遍历数据列表，循环体中可使用 {item} 和 {index} 占位符
   ...
.end_for()
```

**调试链式流程**

| 方法 | 说明 |
|------|------|
| `auto.step()` | 开启/关闭单步模式（每步暂停，按回车继续） |
| `auto.pace(秒数)` | 设置步骤间隔，方便观察执行过程 |

**示例**

```python
# 多次点击
(auto.do()
    .moveto(500, 300)
    .click_multi("确认按钮", k=3, wait=0.2)
    .scroll('down', clicks=5)
    .snap("操作完成")
    .run())

# 连续点击序列
(auto.do()
    .click_seq(["登录", "确定", "欢迎"], wait=0.3)
    .run())
```

### 5. 调试工具

| 方法 | 说明 |
|------|------|
| `auto.debug.on()` | 开启操作追踪 |
| `auto.debug.off()` | 关闭追踪 |
| `auto.debug.report()` | 生成 HTML 执行报告 |
| `auto.debug.replay()` | 控制台回放记录 |

### 6. 环境诊断

| 方法 | 说明 |
|------|------|
| `auto.check()` | 全面诊断（分辨率、缩放、依赖、模板） |
| `auto.check_templates()` | 逐一检查所有模板是否可见 |

### 7. 截图工具

| 方法 | 说明 |
|------|------|
| `auto.shot("文件名")` | 全屏截图，保存至 `screenshots_author/` |
| `auto.snip(x, y, w, h, "文件名")` | 区域截图 |
| `auto.snap(note="")` | **轻量全屏截图**，保存到 `screenshots_author/`，无需文件名 |
| `auto.capture("按钮名称")` | 交互式生成模板截图（推荐新手使用） |

### 8. 定时任务

| 方法 | 说明 |
|------|------|
| `auto.cron("时间", 任务函数)` | 每天定时执行 |
| `auto.cron1("时间", 任务函数)` | 一次性定时执行 |

### 9. 文件查找（独立函数）

```python
from imgclickflow import search
folders, files = search(r"D:\工作", "报告,2025,doc")
```

### 10. 日期工具（独立函数）

```python
from imgclickflow import monthends
days = monthends(2025)   # 返回 [['2025-02-01','2025-02-28'], ...]
```

---

## 💡 经典实战案例

### 案例1：保存并关闭
```python
auto.click("保存按钮")
time.sleep(1)
auto.click("关闭按钮")
```

### 案例2：填表提交
```python
auto.click("姓名输入框")
auto.write("张三")
auto.click("年龄输入框")
auto.write("28")
auto.click("提交按钮")
```

### 案例3：等待加载后操作
```python
auto.wait("加载完成", timeout=60)
auto.click("下一步")
auto.wait("页面就绪")
auto.click("确定")
```

### 案例4：链式流程（含多次点击、滚动、截图）
```python
(auto.do()
    .click("新建按钮")
    .write("内容")
    .click_multi("保存按钮", k=2, wait=0.2)
    .scroll('down', 3)
    .snap("保存完成")
    .run())
```

### 案例5：条件分支
```python
(auto.do()
    .click("提交")
    .if_see("成功")
        .click("确定")
    .else_do()
        .click("重试")
    .endif()
    .run())
```

### 案例6：批量循环
```python
data = ["张三", "李四"]
(auto.do()
    .for_data(data)
        .click("姓名框")
        .write("{item}")
        .click("保存")
    .end_for()
    .run())
```

### 案例7：连续点击多个按钮（动态序列）
```python
# 实际使用时，列表可通过 find_all 生成或手动指定
targets = ["登录", "确定", (300, 400), "关闭"]
auto.click_seq(targets, wait=0.3)
```

### 案例8：批量找图处理
```python
points = auto.find_all("编辑按钮")
for x, y in points:
    auto.click(x, y)
    auto.write("已处理")
    auto.click("保存")
```

### 案例9：每日定时截图
```python
def daily_job():
    auto.click("刷新")
    auto.shot("日报")
auto.cron("17:30", daily_job)
```

---

## ❓ 常见问题

**Q1：找图总是失败怎么办？**
- 确认截图是 PNG 格式（不能用 JPG）。
- 确认文件名与调用时完全一致（不包含扩展名）。
- 确认按钮在屏幕上完全可见（未被遮挡）。
- 运行 `auto.check()` 查看 DPI 缩放系数是否正确。
- 尝试放宽相似度：`auto.find("按钮", similarity=0.85)`。

**Q2：点击位置有偏差？**
脚本已自动适配 DPI。如仍有偏差，运行 `auto.check()` 确认缩放系数。

**Q3：流程运行到一半卡住？**
开启调试模式排查：

```python
auto.debug.on()
auto.step()
auto.pace(1.0)
auto.debug.report()
```

**Q4：定时任务为什么不执行？**
定时任务需要脚本一直保持运行（不能退出），且计算机不能进入休眠。

**Q5：如何生成按钮模板？**
运行 `auto.capture("按钮名称")`，截取全屏后用画图工具裁剪到只保留按钮区域，保存覆盖即可。

**Q6：提示“pip 安装依赖失败”？**
手动安装：

```bash
pip install opencv-python numpy Pillow pywin32 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Q7：自动截图会占用很多磁盘空间吗？**
不会。默认仅保留成功流程的最后 15 张截图（约 3-5MB）；失败流程完整保留，但最多保留最近 5 个失败任务的记录。超过 7 天的记录会自动清理，且执行过程中有实时清理机制，确保磁盘占用可控。

**Q8：如何关闭自动截图功能？**
在脚本中添加：

```python
auto.recorder.enabled = False
```

**Q9：截图上为什么是“操作前”而不是“操作后”？**
操作前截图记录的是“决策现场”：按钮是否可见、页面是否加载完成、是否有弹窗遮挡。这比操作后截图更能帮助定位问题的根本原因。

**Q10：截图上的红色圆圈/方框是什么？**
- **红色圆圈**：标注鼠标即将点击的屏幕坐标位置（`auto.click(x, y)` 触发）。
- **红色方框**：标注图像识别匹配到的模板截图区域（`auto.click("按钮名称")` 触发）。
这些标记直接画在截图上，方便调试时一眼看出自动化“准备操作哪里”，不会影响实际点击。仅在调试录像开启时生效。

---

## 📄 许可证

Apache-2.0 license

作者知乎：https://www.zhihu.com/people/mhaksy
项目地址：https://github.com/honggescripts/ImgClickFlow

**一行代码，让办公自动化触手可及。**
```
