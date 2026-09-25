# 开发与维护

这份文档写给**以后要改这个项目的人**（包括几个月后的我自己）。

重点不是"代码怎么组织"，而是：**怎么确认你的改动没有破坏别的东西**，
以及**用户报了一个 bug 时，怎么最快定位**。

---

## 先跑通这三条

任何改动之前，先确认手上这份是好的：

```bash
./core/mcm deploy            # 目录完整性 + 模板能否加载
python3 -m pytest core/tests -q    # 564 个 Python 测试
npm --prefix web test        # 面板测试（需要先装依赖）
```

面板测试的依赖只装一次：

```bash
npm --prefix web install
```

> **`./core/mcm deploy` 值得先跑**：它会数模板个数。模板加载失败
> 或拷漏了分区，`pytest` 不一定报，它一定报。

---

## 目录与职责

```
core/mcmcore/
├── schemas/       数据结构（pydantic）。改字段从这里开始
├── templates.py   模板注册表与加载
├── sampledata.py  示例数据生成（按模板声明推导）
├── diyfig.py      自定图表引擎
├── mcmplot.py     绘图中文字体处理（core 侧）
├── citations.py   参考文献解析与核对
├── validate.py    审计规则
├── api.py         面板后端（全部 HTTP 端点）
├── launcher.py    启动逻辑（start / start.bat / .app 的唯一实现）
├── doctor.py      环境检查
├── deploy.py      部署自检
└── compiler/      LaTeX 编译

templates/figures/mcmplot.py    ← 注意：和 core 那份不是同一个文件
```

**`mcmplot.py` 有两份，这不是笔误。** `core/mcmcore/mcmplot.py` 给
自定图表用；`templates/figures/mcmplot.py` 给图模板用，由
`figures.py` 按显式路径加载。两份的函数不完全一样，改的时候
**看清你改的是哪一份**，别指望改一个另一个跟着变。

---

## 加一个图模板

1. 建目录 `templates/figures/<名字>/`
2. 写 `template.yaml` 和 `render.py`
3. 在 `core/tests/test_template_library.py` 的 `SAMPLE_DATA` 里补一份数据

`render.py` 的契约：

```python
def render(data: Dict[str, Any], meta: Dict[str, Any]):
    """返回 matplotlib Figure。不要 savefig，不要 plt.show。"""
```

**必须遵守的三条**：

- 数据缺失时抛**中文** `ValueError`，说清缺什么。绝不能画一张空图 ——
  空图会被当成"成功"，然后插进论文。
- 中文文本过 `mcmplot.safe()`。中文字体不含 `²`、`−`，直接写是豆腐块。
- 返回值是 Figure，不是路径。谁保存由调用方决定。

**排序不要靠人工检查**：`core/tests/test_no_text_overlap.py` 会自动量
文字 bbox 查重叠。写完跑一遍，重叠了它会告诉你是哪两个标签。

### 最容易踩的坑

`template.yaml` 的 schema 是 `extra="forbid"`。**写错字段名不会报错，
模板会静默消失。** 所以：

```bash
python3 -c "
import sys; sys.path.insert(0,'core')
from mcmcore.templates import TemplateRegistry, default_registry_root
r = TemplateRegistry(default_registry_root()).load()
print('总数', len(r), '错误', len(r._errors))
for e in r._errors: print('  ERR', e[:140])
"
```

**`错误` 必须是 0。** 加载走的是 `load_strict()`，所以真跑起来
缺模板会启动失败 —— 这是刻意的，宁可崩也不要静默少一半。

---

## 加一个代码模板

放 `templates/code/<名字>/`，两个文件：`template.yaml` + `snippet.py`。

- `snippet.py` 要能**独立运行**（`python3 snippet.py`），用模拟数据
- 输出走 `tempfile`，**不要写进模板目录**
- `entrypoint` 写 `code/<名字>/snippet.py` —— 它是相对
  `templates/` 解析的，不是相对模板目录

代码模板的验收标准不是"能跑"，是**结果对得上独立算法或手算**。
写的时候踩过：Gauss-Newton 漏了个负号，每步代价都变大 → 阻尼一路
拒绝 → 函数把初值原样返回，"看起来收敛了其实一步没动"。

---

## 面板

没有打包器，改完 `app.js` 刷新页面即可。

**加一个页面必须同时改三处**，少一处就静默不显示：

1. `renderScreen` 的 dispatch 表
2. `SCREENS`（路由名 → 处理函数）
3. `GROUPS`（侧栏分组、在哪些阶段显示）

文案统一放 `web/strings.js`，不要在 `app.js` 里写中文字面量。

### 测试面板时的两个坑

**一、必须用 `go()`，不能直接调 `renderScreen()`。**

```js
probe.go('diy');          // 对
probe.renderScreen('diy'); // 错：渲染的是别的页面
```

`renderScreen()` 读的是模块内的 `ROUTE`，只有 `go()` 会更新它。
直接调它，你 querySelector 拿到的是上一次遗留的 DOM —— 表现是
结果时对时错、还冒出毫不相关的元素，非常难查。

**二、`go()` 之前要先等 boot 完成。**

```js
await wait(1200);   // 等面板自己的 refresh() 填上 STATE
probe.go('diy');
await wait(2500);   // 等页面渲染
```

`renderSidebar` 读 `STATE.phase`，STATE 还是 null 时调 `go()` 会抛
`Cannot read properties of null`。

---

## 用户报 bug 时

先让他跑这个，把现场一次性收集齐：

```bash
./core/mcm report --out ~/Desktop/mcmtools-diag.txt
```

报告含版本号（带 git 提交号）、系统、依赖、模板数、项目结构计数。
**不含论文正文** —— 只报数量，不报内容。

拿到报告先看三件事：

1. **版本对得上吗** —— `0.5.0+git.a1b2c3d` 能直接定位到提交
2. **模板数对不对** —— 少于 101 就是拷贝不完整，不是代码问题
3. **依赖齐吗** —— 没有 pdflatex 只是不能出 PDF，别的照常

### 几个"报错信息指向错误方向"的已知案例

这几个都真实发生过，报错文本和真正的原因**完全不在一处**：

| 现象 | 真正的原因 |
|---|---|
| `Undefined control sequence` 指向某个宏 | 存档里的宏被换行劈开，反斜杠被吃掉 |
| 中文报 `Unicode character not set up` | 正文里混进了中文，LaTeX 需要 xelatex |
| 模板"不见了" | YAML 字段名写错，`extra="forbid"` 静默丢弃 |
| 图上中文变方块 | 没调用 `mcmplot.setup()` |
| 面板某页空白 | 页面没注册进 `SCREENS` / `GROUPS` / dispatch 表 |

---

## 发一个版本

1. 改 `core/mcmcore/__init__.py` 的 `__version__`（**只有这一处**）
2. 跑全量测试
3. `git tag v<版本号> && git push --tags`

`./core/mcm --version` 会打印 `版本+git.提交号`，报 bug 时让对方附上。

---

## 打补丁的几个原则

这些是踩出来的，不是理论上应该怎样：

**一、宁可启动失败，不要静默降级。**
模板加载失败就让启动失败。曾经因为 schema 不认识一个字段，
74 个模板掉了 28 个，而服务照常启动、接口照常响应、**全程不报错**。

**二、错误信息说人话。**
用户看不懂 `Undefined control sequence`。报错要说"缺哪个输入、
该怎么填"。

**三、数字只有一个来源。**
正文引用宏（`\numBetaFit{}`），不手抄数值。改参数重跑，正文自动跟着变。

**四、改渲染入口时留个自愈。**
`compiler/renderer.py` 的 `normalise()` 会修被劈开的宏。
已经写坏的存档能自愈，用户不必为了改一句话去手工编辑 YAML。
注意顺序：**先收数学里的换行，再修宏**，反过来会把刚补上的
反斜杠一起吞掉。

**五、测试要能真的失败。**
`test_no_text_overlap.py` 里有一组检测器自检 —— 故意叠两段文字
必须能被查出来。规则本身失效时，测试会一片全绿，那种绿毫无意义。

---

## 常见任务速查

```bash
# 全量测试
python3 -m pytest core/tests -q && npm --prefix web test

# 只测模板相关
python3 -m pytest core/tests/test_template_library.py \
                  core/tests/test_sampledata.py \
                  core/tests/test_no_text_overlap.py -q

# 模板能否加载（必须是 0 错误）
./core/mcm template list

# 部署自检
./core/mcm deploy

# 诊断报告
./core/mcm report --project ~/我的项目

# 起面板调试
./start ~/我的项目 --port 8420
```

### 本地调试用的样例项目

`examples/demo_pcql` 是完整项目，`examples/mcm2023_C` 是真实赛题
样例论文（含 16 页 PDF 成品）。

它们的 `build/` 和 `runs/` **不入库**（是运行产物）。需要时重建：

```bash
./core/mcm --dir examples/demo_pcql exp run EXP-001
./core/mcm --dir examples/demo_pcql paper build
```

> 面板测试就是跑在 `examples/demo_pcql` 上的。如果它缺了
> `runs/`，某些测试的期望值会变 —— 那不是 bug，是"还没跑过实验"。
