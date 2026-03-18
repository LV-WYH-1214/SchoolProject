# 简易计算器 Python + GTK3 版本

## 项目概述

本项目是将原 C 语言的 GTK3 简易计算器改写为 **Python 语言版本**。Python 版本与 C 版本功能对标，支持基础四则运算（加、减、乘、除）、清除功能，并保持相同的界面布局逻辑。

### 技术栈
- **编程语言**：Python 3.8+
- **GUI 框架**：GTK+ 3（通过 PyGObject 对接）
- **主要特性**：
  - 对象导向设计（使用类管理状态）
  - 类型注解（提高代码可读性）
  - 信号槽机制处理事件

---

## 代码架构与核心模块

### 1. CalculatorState 类

```python
class CalculatorState:
    """
    计算器状态类：
    - display: 用于显示数字和结果的 Gtk.Label
    - current_number: 当前正在输入或当前显示的数字（字符串形式）
    - result: 已累计的运算结果（浮点数）
    - operation: 当前待执行的运算符（'+', '-', '*', '/' 或 None)
    - new_number: 标记下一次数字输入是否需要"开始新数字"
      True  -> 下一次输入数字时覆盖显示内容
      False -> 下一次输入数字时在末尾追加
    """
    
    def __init__(self) -> None:
        # 先放一个占位 Label，后续在 build_ui 中替换为界面上的真实 Label。
        self.display: Gtk.Label = Gtk.Label(label="0")
        self.current_number: str = ""
        self.result: float = 0.0
        self.operation: str | None = None
        self.new_number: bool = True

    def reset(self) -> None:
        """重置到初始状态。"""
        self.current_number = ""
        self.result = 0.0
        self.operation = None
        self.new_number = True
```

**分析：**
- 对应 C 版本的 `CalculatorState` 结构体
- Python 版本使用**类**来管理状态，更符合面向对象思想
- `reset()` 方法对应 C 的 `init_calculator_state()`
- 使用**类型注解**（`: Gtk.Label`, `: str` 等）提高代码可读性

---

### 2. 显示更新函数

```python
def update_display(state: CalculatorState) -> None:
    """
    刷新显示文本。
    
    这里做了一个小改进：
    - 当 current_number 为空时显示 "0"，避免界面出现空白。
    """
    text = state.current_number if state.current_number else "0"
    state.display.set_text(text)
```

**分析：**
- 直接对应 C 版本的 `update_display()` 函数
- 使用三元表达式简化条件判断
- Python 的 `set_text()` 对应 C 的 `gtk_label_set_text()`

---

### 3. 运算符应用函数

```python
def apply_pending_operation(state: CalculatorState, current: float) -> None:
    """
    将"当前输入值 current"应用到"累计结果 result"上。
    
    逻辑与 C 版本一致：
    - 如果已有待执行运算符，就按该运算符计算
    - 如果没有待执行运算符，说明这是第一次输入，直接把 current 赋给 result
    """
    if state.operation == "+":
        state.result += current
    elif state.operation == "-":
        state.result -= current
    elif state.operation == "*":
        state.result *= current
    elif state.operation == "/":
        # 这里处理除零，避免程序崩溃或出现不可控结果。
        # 与传统计算器类似，显示 Error 并重置运算状态。
        if current == 0:
            state.current_number = "Error"
            state.result = 0.0
            state.operation = None
            state.new_number = True
            return
        state.result /= current
    else:
        state.result = current
```

**分析：**
- 对应 C 版本的 `apply_pending_operation()` 函数
- 使用 `if-elif-else` 链处理四种运算符
- **改进**：添加了除零检查，显示 "Error" 并自动恢复状态
- Python 的 `+=`、`-=`、`*=`、`/=` 运算符比 C 的手动赋值更简洁

---

### 4. 结果格式化函数

```python
def format_result(value: float) -> str:
    """
    将浮点结果格式化为较短字符串，近似 C 代码中的 "%.8g" 效果。
    - 使用 8 位有效数字
    - 自动去掉不必要的末尾 0
    """
    return f"{value:.8g}"
```

**分析：**
- 对应 C 的 `snprintf(buffer, size, "%.8g", value)`
- Python 使用 f-string 和格式说明符 `.8g` 实现相同效果
- `g` 格式会自动选择固定点或指数表示，避免过长的小数

---

### 5. 按钮回调函数 - 数字按钮

```python
def on_number_clicked(button: Gtk.Button, state: CalculatorState) -> None:
    """
    数字按钮回调：
    - 如果是新数字输入阶段，直接覆盖 current_number
    - 否则将数字追加到 current_number 末尾
    """
    text = button.get_label() or ""

    # 如果当前显示 Error，下一次输入数字直接开始新输入
    if state.current_number == "Error":
        state.current_number = ""
        state.new_number = True

    if state.new_number:
        state.current_number = text
        state.new_number = False
    else:
        state.current_number += text

    update_display(state)
```

**分析：**
- 对应 C 版本的 `on_number_clicked()` 回调函数
- `button.get_label()` 获取按钮上的文字
- `or ""` 是 Python 的防守式编程，避免 None 导致的错误
- **改进**：当显示 Error 时自动重置为新输入模式，提升用户体验

---

### 6. 按钮回调函数 - 运算符按钮

```python
def on_operator_clicked(button: Gtk.Button, state: CalculatorState) -> None:
    """
    运算符按钮回调（+ - * /）：
    1. 读取当前输入数字并应用到累计结果
    2. 保存新的待执行运算符
    3. 进入"等待下一段数字输入"状态
    4. 显示当前累计结果
    """
    text = button.get_label() or ""

    # 若当前内容不可用于数值计算（如 Error），忽略本次操作
    if state.current_number == "Error":
        return

    if state.current_number:
        current = float(state.current_number)
        apply_pending_operation(state, current)

        # 如果在 apply_pending_operation 内触发了 Error，则直接刷新后返回
        if state.current_number == "Error":
            update_display(state)
            return

        state.operation = text[:1] if text else None
        state.new_number = True
        state.current_number = format_result(state.result)
        update_display(state)
```

**分析：**
- 对应 C 版本的 `on_operator_clicked()` 回调函数
- `float(state.current_number)` 将字符串转换为浮点数
- `text[:1]` 确保只取第一个字符作为运算符（防止按钮标签包含多个字符的情况）
- **改进**：检查 Error 状态，避免可能的异常

---

### 7. 按钮回调函数 - 等号按钮

```python
def on_equals_clicked(_button: Gtk.Button, state: CalculatorState) -> None:
    """
    等号按钮回调：
    - 将当前输入应用到累计结果
    - 显示最终结果
    - 清空待执行运算符，下一次数字输入将开启新数字
    """
    if state.current_number == "Error":
        return

    if state.current_number:
        current = float(state.current_number)
        apply_pending_operation(state, current)

        if state.current_number == "Error":
            update_display(state)
            return

        state.current_number = format_result(state.result)
        update_display(state)

        state.operation = None
        state.new_number = True
```

**分析：**
- 对应 C 版本的 `on_equals_clicked()` 回调函数
- 参数名 `_button` 前缀下划线表示该参数未被使用（Python 惯例）
- 设置 `state.operation = None` 清空待执行运算符
- 设置 `state.new_number = True` 准备下一次输入

---

### 8. 按钮回调函数 - 清除按钮

```python
def on_clear_clicked(_button: Gtk.Button, state: CalculatorState) -> None:
    """清除按钮回调：恢复初始状态并刷新显示。"""
    state.reset()
    update_display(state)
```

**分析：**
- 对应 C 版本的 `on_clear_clicked()` 回调函数
- 简洁地调用 `state.reset()` 和 `update_display()` 恢复初始状态

---

### 9. 按钮创建工厂函数

```python
def create_button(label: str, callback, state: CalculatorState) -> Gtk.Button:
    """
    创建按钮并绑定 clicked 信号。
    
    参数：
    - label: 按钮文本
    - callback: 点击回调函数
    - state: 作为用户数据传给回调，便于共享计算器状态
    """
    button = Gtk.Button(label=label)
    button.connect("clicked", callback, state)
    return button
```

**分析：**
- 对应 C 版本的 `create_button()` 工厂函数
- `Gtk.Button(label=label)` 创建带标签的按钮
- `button.connect("clicked", callback, state)` 对应 C 的 `g_signal_connect()`
- Python 直接传递 `state` 对象，不需要像 C 那样转换为 `gpointer`

---

### 10. UI 构建函数

```python
def build_ui() -> Gtk.Window:
    """创建主窗口和全部控件，返回窗口对象。"""
    state = CalculatorState()

    # 主窗口
    window = Gtk.Window(title="简易计算器")
    window.set_default_size(300, 400)
    window.set_border_width(10)

    # 关闭窗口时退出 GTK 主循环
    window.connect("destroy", Gtk.main_quit)

    # 垂直布局容器
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    window.add(vbox)

    # 显示标签：右对齐，初始值为 0
    state.display = Gtk.Label(label="0")
    state.display.set_halign(Gtk.Align.END)
    vbox.pack_start(state.display, False, False, 5)

    # 按钮网格
    grid = Gtk.Grid()
    grid.set_row_spacing(5)
    grid.set_column_spacing(5)
    vbox.pack_start(grid, True, True, 5)

    # 清除按钮（第一行占满 4 列）
    clear_button = create_button("C", on_clear_clicked, state)
    grid.attach(clear_button, 0, 0, 4, 1)

    # 数字按钮（1-9 按计算器常规布局，0 占两列）
    for i in range(10):
        button = create_button(str(i), on_number_clicked, state)
        if i == 0:
            # 0 放在底部第一、二列
            grid.attach(button, 0, 4, 2, 1)
        else:
            # 与原 C 代码相同的行列映射规则
            row = 3 - (i - 1) // 3
            col = (i - 1) % 3
            grid.attach(button, col, row, 1, 1)

    # 运算符按钮（右侧一列）
    add_button = create_button("+", on_operator_clicked, state)
    grid.attach(add_button, 3, 1, 1, 1)

    sub_button = create_button("-", on_operator_clicked, state)
    grid.attach(sub_button, 3, 2, 1, 1)

    mul_button = create_button("*", on_operator_clicked, state)
    grid.attach(mul_button, 3, 3, 1, 1)

    div_button = create_button("/", on_operator_clicked, state)
    grid.attach(div_button, 3, 4, 1, 1)

    # 等号按钮
    equals_button = create_button("=", on_equals_clicked, state)
    grid.attach(equals_button, 2, 4, 1, 1)

    return window
```

**分析：**
- 对应 C 版本的 `main()` 函数中的界面创建部分
- 构建流程：创建主窗口 → 创建垂直层 → 创建显示标签 → 创建网格 → 添加按钮
- `Gtk.Window()` 对应 C 的 `gtk_window_new()`
- `Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)` 对应 C 的 `gtk_box_new()`
- `Gtk.Grid()` 对应 C 的 `gtk_grid_new()`
- 数字按钮的行列映射公式与 C 版本完全相同：
  - 1-9：`row = 3 - (i-1)//3`, `col = (i-1)%3`
  - 0：占据第一行（row=4）的前两列

---

### 11. 主函数

```python
def main() -> None:
    """程序入口。"""
    window = build_ui()
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
```

**分析：**
- `main()` 函数是程序入口点
- `build_ui()` 构建用户界面
- `window.show_all()` 显示所有控件（对应 C 的 `gtk_widget_show_all()`）
- `Gtk.main()` 启动 GTK 事件循环（对应 C 的 `gtk_main()`）
- `if __name__ == "__main__":` 是 Python 的标准惯例，确保仅在直接运行时执行

---

## 程序执行流程

### 1. 程序启动
1. 执行 `main()` 函数
2. 调用 `build_ui()` 构建用户界面
3. 创建 `CalculatorState` 对象管理状态
4. 创建并布局所有按钮和显示标签
5. 显示所有控件：`window.show_all()`
6. 进入 GTK 事件循环：`Gtk.main()`，等待用户交互

### 2. 用户输入数字
1. 点击数字按钮
2. 触发 `on_number_clicked()` 回调
3. 获取按钮上的数字
4. 根据 `new_number` 状态决定是替换还是追加
5. 更新显示

### 3. 用户选择运算符
1. 点击运算符按钮（+、-、*、/）
2. 触发 `on_operator_clicked()` 回调
3. 获取当前输入的数字
4. 根据之前的运算符执行计算
5. 保存新的运算符
6. 显示计算结果
7. 准备输入新数字

### 4. 用户计算结果
1. 点击等号按钮
2. 触发 `on_equals_clicked()` 回调
3. 获取当前输入的数字
4. 根据运算符执行最终计算
5. 显示计算结果
6. 重置运算符状态

### 5. 用户清除输入
1. 点击清除按钮（C）
2. 触发 `on_clear_clicked()` 回调
3. 重新初始化计算器状态（调用 `state.reset()`）
4. 更新显示为初始状态（"0"）

---

## 代码特点与改进

### 相比 C 版本的优势

| 特性 | Python 版本 | C 版本 |
|------|-----------|--------|
| **代码行数** | ~250 行 | ~400 行 |
| **类型管理** | 类（OOP）| 结构体 + 函数 |
| **内存管理** | 自动（GC） | 手动 malloc/free |
| **字符串处理** | 原生支持 | 需要 strcpy/strcat |
| **除零处理** | ✓ 有 | ✗ 无 |
| **Error 恢复** | ✓ 自动 | ✗ 手动 |
| **可读性** | 高（注解、文档） | 相对较低 |

### 核心设计模式

1. **状态管理**
   - 使用 `CalculatorState` 类统一管理计算器全部状态
   - 便于多个函数间传递和修改状态

2. **事件驱动编程**
   - 通过 GTK 的信号机制处理用户交互
   - 每个按钮对应一个回调函数

3. **工厂模式**
   - `create_button()` 函数简化按钮创建流程
   - 减少重复代码

4. **责任分离**
   - `apply_pending_operation()` 负责计算
   - `update_display()` 负责显示
   - 各函数职责清晰

---

## 运行和打包

### 方法 1：直接运行（需要 Python + PyGObject）
```bash
cd MyProject
python simplecalculator.py
```

### 方法 2：打包为独立 .exe 文件（PyInstaller）
```bash
pip install pyinstaller
pyinstaller --onefile --windowed simplecalculator.py
```
生成的 `.exe` 文件位于 `dist/` 文件夹，可在任何 Windows 机器上运行（无需 Python）。

### 方法 3：创建批处理脚本简化重复打包
创建 `build.bat` 文件：
```batch
@echo off
cd /d "%~dp0"
pyinstaller --onefile --windowed simplecalculator.py
echo.
echo Build complete! The .exe is in the dist/ folder
pause
```
以后修改代码后，直接双击 `build.bat` 即可重新生成 `.exe`。

---

## 总结

本项目成功将 C 语言的 GTK3 计算器改写为 Python 版本，保持了功能的完全对标，同时充分利用 Python 的特性（如自动内存管理、原生字符串处理、面向对象编程）提高了代码的可读性和可维护性。Python 版本还在错误处理方面做了改进，提供更好的用户体验。

通过 PyInstaller 可以轻松将 Python 脚本打包为可执行文件，方便最终用户使用。
