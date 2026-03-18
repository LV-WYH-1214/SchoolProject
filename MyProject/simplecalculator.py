import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class CalculatorState:
    """
    计算器状态类：
    - display: 用于显示数字和结果的 Gtk.Label
    - current_number: 当前正在输入或当前显示的数字（字符串形式）
    - result: 已累计的运算结果（浮点数）
    - operation: 当前待执行的运算符（'+', '-', '*', '/' 或 None)
    - new_number: 标记下一次数字输入是否需要“开始新数字”
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
        """重置到初始状态，相当于 C 版本中的 init_calculator_state。"""
        self.current_number = ""
        self.result = 0.0
        self.operation = None
        self.new_number = True


def update_display(state: CalculatorState) -> None:
    """
    刷新显示文本。

    这里做了一个小改进：
    - 当 current_number 为空时显示 "0"，避免界面出现空白。
    """
    text = state.current_number if state.current_number else "0"
    state.display.set_text(text)


def apply_pending_operation(state: CalculatorState, current: float) -> None:
    """
    将“当前输入值 current”应用到“累计结果 result”上。

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


def format_result(value: float) -> str:
    """
    将浮点结果格式化为较短字符串，近似 C 代码中的 "%.8g" 效果。
    - 使用 8 位有效数字
    - 自动去掉不必要的末尾 0
    """
    return f"{value:.8g}"


def on_number_clicked(button: Gtk.Button, state: CalculatorState) -> None:
    """
    数字/小数点按钮回调：
    - 如果是新数字输入阶段，直接覆盖 current_number
    - 否则将数字追加到 current_number 末尾
    """
    text = button.get_label() or ""

    # 如果当前显示 Error，下一次输入数字直接开始新输入
    if state.current_number == "Error":
        state.current_number = ""
        state.new_number = True

    if text == ".":
        if state.new_number:
            # 新数字以小数点开头时，统一显示为 0.
            state.current_number = "0."
            state.new_number = False
        elif "." not in state.current_number:
            # 同一个数字中只允许一个小数点
            state.current_number += "."
    else:
        if state.new_number:
            state.current_number = text
            state.new_number = False
        else:
            state.current_number += text

    update_display(state)


def on_operator_clicked(button: Gtk.Button, state: CalculatorState) -> None:
    """
    运算符按钮回调（+ - * /):
    1. 读取当前输入数字并应用到累计结果
    2. 保存新的待执行运算符
    3. 进入“等待下一段数字输入”状态
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


def on_clear_clicked(_button: Gtk.Button, state: CalculatorState) -> None:
    """清除按钮回调：恢复初始状态并刷新显示。"""
    state.reset()
    update_display(state)


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

    # 数字按钮（1-9 按计算器常规布局）
    for i in range(10):
        button = create_button(str(i), on_number_clicked, state)
        if i == 0:
            # 0 放在底部第一列
            grid.attach(button, 0, 4, 1, 1)
        else:
            # 与原 C 代码相同的行列映射规则
            row = 3 - (i - 1) // 3
            col = (i - 1) % 3
            grid.attach(button, col, row, 1, 1)

    # 小数点按钮
    dot_button = create_button(".", on_number_clicked, state)
    grid.attach(dot_button, 1, 4, 1, 1)

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


def main() -> None:
    """程序入口。"""
    window = build_ui()
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
