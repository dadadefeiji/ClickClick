
---

# ImgClickFlow v2.0
> 桌面图像自动化领域的「单兵作战神兵利器」—— 一个 Python 脚本，就能超越商业 RPA 的丝滑体验。

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-blue)](https://www.microsoft.com/windows)

**作者知乎**：[https://www.zhihu.com/people/mhaksy](https://www.zhihu.com/people/mhaksy)

## 设计哲学：像初代 iPhone 一样极简

我们相信，真正的力量源于极致的简单。ImgClickFlow 不依赖臃肿的编辑器、复杂的模块或繁琐的配置，**一切皆为 `auto`**。作者已将 DPI 适配、超时重试、智能去重等所有复杂逻辑内化，留给你的只有和说话一样自然的自动化代码。

**一个脚本，即开即用。极致打磨，单兵作战体验远远超越现有商业 RPA。**

## ✨ v2.0 核心特性

| 特性 | 为什么你再也回不去商业 RPA 了 |
|------|------|
| **DPI 自适应，一处编写处处运行** | 自动检测屏幕缩放系数（100%/125%/150%），图像匹配与点击在统一物理坐标系下完成。**只需替换按钮截图，同一份脚本即可在所有电脑上完美运行**，再也不用为不同分辨率重写代码。 |
| **彩色优先，精准如人眼** | 默认使用彩色模板匹配，能准确区分按钮的启用/禁用、链接的已读/未读状态。当然，你也可以随时切回极速灰度模式。 |
| **智能去重，稳如磐石** | 内置非极大值抑制（NMS），自动合并邻近匹配点，彻底告别"一个按钮被点两次"的尴尬。 |
| **区域搜索，快如闪电** | `click`、`find` 等所有核心方法均支持 `rect` 限定查找范围，效率提升一个数量级。 |
| **零负担等待，让脚本再等一会儿** | 所有找图操作自带超时与重试，等待元素出现或消失就像 `auto.wait("按钮")` 这么自然。 |
| **操作自动截图，问题无处可藏** | 每一步操作前自动截屏，并在图上标记红框/红圈，右下角嵌入任务名、时间戳与代码水印。**这不是花哨的录像，而是你的私人排错侦探——脚本哪里卡住、点到了什么东西，一眼就能定位，极大降低调试成本。** |
| **链式流程编排，写代码像写文章** | `auto.do().click("A").write("内容").if_see("B").click("C").run()` —— 极简超强的自动化代码体验，仿佛在读一段自然语言。10 分钟 auto 杀爆商业 RPA 半小时的配置工作。这就是我们追求的：连中小学生都能 10 分钟入门，职场人士更能即刻上手。 |

## 10 秒上手，一生受用

1. 把这个脚本放到任意文件夹。
2. 在同目录下创建 `templates` 文件夹，把按钮截图（PNG）放进去。
3. 写一行代码并运行：
```python
from imgclickflow import auto
auto.click("你的按钮")
```
4. 完成。连快捷键都不用配。

> 中学生 10 分钟入门，职场人 5 分钟开始提效。丝滑极简的自动化代码体验，和说话一样自然，高效。

## 文件结构
```
你的工作目录/
├── imgclickflow.py         # 这就是一切，无需安装
├── templates/              # 放你的 PNG 按钮截图
├── [脚本名]_操作截屏/      # 调试截图自动保存在此
├── logs/                   # 运行日志
├── screenshots_author/     # 你主动截的图
└── error_snapshots/        # 找不到时自动留证
```

## ⚙️ 配置参数（修改 `Config` 类）

所有调校都在脚本开头，只需改一次：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `template_dir` | `"templates"` | 模板截图存放文件夹 |
| `default_similarity` | `0.9` | 匹配相似度（0~1） |
| `default_timeout` | `10` | 找图超时（秒） |
| `default_fast_mode` | `False` | 默认彩色精准匹配，`True` 为灰度极速模式 |
| `post_click_delay` | `0.3` | 点击后让界面缓一缓 |
| `auto.recorder.enabled` | `True` | 调试截图总开关 |

## API 速查表

### 鼠标操作（万物皆可点）
| 方法 | 说明 | 示例 |
|------|------|------|
| `auto.click()` | 左键单击（无参/坐标/图片名，支持 `rect`,`fast_mode`） | `auto.click("保存")` |
| `auto.dclick()` | 双击 | `auto.dclick("文件", rect=(0,0,500,500))` |
| `auto.rclick()` | 右键 | `auto.rclick("菜单")` |
| `auto.click_multi()` | 多次点击 | `auto.click_multi("加号", k=5, wait=0.2)` |
| `auto.click_seq()` | 依次点击列表 | `auto.click_seq(["登录","确定"])` |
| `auto.drag()` | 拖拽 | `auto.drag(100,100,500,400)` |
| `auto.scroll()` | 滚轮 | `auto.scroll('down', 5)` |

### 键盘操作（粘贴即输入）
| 方法 | 说明 | 示例 |
|------|------|------|
| `auto.write()` | 剪贴板粘贴（支持中文） | `auto.write("报表.docx")` |
| `auto.press()` | 单键 | `auto.press("enter", 2)` |
| `auto.hotkey()` | 组合键 | `auto.hotkey("ctrl","v")` |

### 图像识别（眼睛与大脑）
| 方法 | 说明 |
|------|------|
| `auto.find("名", timeout, similarity, rect, fast_mode)` | 返回坐标 (x,y)，找不到返回 (-1,-1) |
| `auto.find_all("名", rect, fast_mode)` | 返回所有匹配坐标列表 |
| `auto.wait("名", timeout, fast_mode)` | 等待图片出现 |
| `auto.wait_not("名", timeout, fast_mode)` | 等待图片消失 |

### 流程引擎（真正的魔法都在这里）
```python
auto.do()
    .retry(3, wait=2)                # 整体失败重试 3 次
    .click("提交")
    .if_see("成功")
        .click("确定")
    .else_do()
        .click("重试")
    .endif()
    .for_data(["张三","李四"])       # 循环，可用 {item} 和 {index}
        .click("姓名框")
        .write("{item}")
        .click("保存")
    .end_for()
    .run()
```

### 调试与诊断
| 方法 | 说明 |
|------|------|
| `auto.debug.on()` / `.off()` | 开启/关闭操作追踪 |
| `auto.debug.report()` | 生成 HTML 执行报告 |
| `auto.step()` | 开启单步模式，每次操作前按回车 |
| `auto.check()` | 一键诊断环境 |
| `auto.recorder.enabled = False` | 关闭调试截图以加速 |

## 常见问题

**Q: 为什么截图必须是 PNG？**
A: JPG 压缩会造成像素偏移，导致匹配失败。这是 OpenCV 的要求，也是我们保障精准的底线。

**Q: 换了一台 4K 屏电脑，脚本需要改吗？**
A: 完全不用。**只要替换 `templates` 里的截图（在新电脑上截取）**，同一份脚本可以直接运行，DPI 缩放已被自动补偿。

**Q: 脚本跑着跑着就停了，怎么找原因？**
A: 打开 `[脚本名]_操作截屏` 文件夹，最后一张带红框/红圈的截图就是案发现场。水印上还印着是哪一行代码执行的，定位异常就像看监控回放。

## 许可证
Apache-2.0 license

**一行代码，让图像自动化回归它本应有的样子。**

---

