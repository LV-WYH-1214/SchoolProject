import gi  # type: ignore[import-not-found]

gi.require_version("Gtk", "3.0")
import math
import re

from gi.repository import Gdk, Gtk  # type: ignore[attr-defined]
from simpleeval import SimpleEval  # type: ignore[import-not-found]


BACKSPACE_SYMBOL = "<="
MAX_EXPRESSION_LENGTH = 120
ERROR_DIV_ZERO = "Div0"
ERROR_SYNTAX = "语法错误"
ERROR_DOMAIN = "域错误"
ERROR_OVERFLOW = "溢出"
ERROR_GENERIC = "错误"
ERROR_MESSAGES = {ERROR_DIV_ZERO, ERROR_SYNTAX, ERROR_DOMAIN, ERROR_OVERFLOW, ERROR_GENERIC}


class CalculatorState:
    """表达式驱动状态：主屏显示表达式，预览屏显示实时结果。"""

    def __init__(self) -> None:
        self.expression: str = ""
        self.preview: str = ""
        self.last_result: str = ""
        self.scientific_mode: bool = False
        self.use_degrees: bool = True

    def clear(self) -> None:
        self.expression = ""
        self.preview = ""


class CalculatorApp:
    def __init__(self) -> None:
        self.state = CalculatorState()
        self.evaluator = self._create_evaluator()

        self.window = Gtk.Window(title="现代计算器")
        self.window.set_default_size(360, 580)
        self.window.set_border_width(12)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("key-press-event", self.on_key_press)

        self.apply_css()
        self.main_display, self.preview_display, self.revealer = self.build_ui(self.window)
        self.refresh_displays()

    def _create_evaluator(self) -> SimpleEval:
        def to_radians(value: float) -> float:
            return math.radians(value) if self.state.use_degrees else value

        def sin_fn(value: float) -> float:
            return math.sin(to_radians(value))

        def cos_fn(value: float) -> float:
            return math.cos(to_radians(value))

        def tan_fn(value: float) -> float:
            return math.tan(to_radians(value))

        evaluator = SimpleEval()
        evaluator.functions = {
            "sin": sin_fn,
            "cos": cos_fn,
            "tan": tan_fn,
            "sqrt": math.sqrt,
            "log": math.log10,
            "ln": math.log,
            "abs": abs,
        }
        evaluator.names = {
            "pi": math.pi,
            "e": math.e,
        }
        return evaluator

    def apply_css(self) -> None:
        css = """
        window {
            background: #f1f3f5;
        }

        .display-main {
            font-size: 38px;
            font-weight: 700;
            color: #1f2933;
            padding: 8px 0;
        }

        .display-preview {
            font-size: 20px;
            color: #7b8794;
            padding: 0 0 10px 0;
        }

        button {
            min-height: 52px;
            border-radius: 16px;
            border: 1px solid #d7dde5;
            font-size: 18px;
            font-weight: 600;
        }

        .number-button {
            background: #ffffff;
            color: #1f2933;
        }

        .operator-button {
            background: #e9edf2;
            color: #1f2933;
        }

        .function-button {
            background: #eef6ff;
            color: #0b4f8c;
        }

        .equals-button {
            background: #0078d7;
            color: #ffffff;
            border-color: #0078d7;
        }

        .toggle-button {
            background: #e1e8f0;
            color: #243b53;
            min-height: 40px;
            min-width: 64px;
        }
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def build_ui(self, window: Gtk.Window) -> tuple[Gtk.Label, Gtk.Label, Gtk.Revealer]:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        window.add(root)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(top_bar, False, False, 0)

        sci_button = self.create_button("Sci", self.on_toggle_science, "toggle-button")
        top_bar.pack_start(sci_button, False, False, 0)
        self.angle_button = self.create_button("Deg", self.on_toggle_angle_mode, "toggle-button")
        top_bar.pack_start(self.angle_button, False, False, 6)

        display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        root.pack_start(display_box, False, False, 0)

        main_display = Gtk.Label(label="0")
        main_display.set_halign(Gtk.Align.END)
        main_display.set_xalign(1.0)
        main_display.set_ellipsize(3)
        main_display.get_style_context().add_class("display-main")
        display_box.pack_start(main_display, False, False, 0)

        preview_display = Gtk.Label(label="")
        preview_display.set_halign(Gtk.Align.END)
        preview_display.set_xalign(1.0)
        preview_display.get_style_context().add_class("display-preview")
        display_box.pack_start(preview_display, False, False, 0)

        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(200)
        revealer.set_reveal_child(False)
        root.pack_start(revealer, False, False, 0)

        sci_grid = Gtk.Grid()
        sci_grid.set_row_spacing(6)
        sci_grid.set_column_spacing(6)
        revealer.add(sci_grid)

        sci_layout = [
            ["sin", "cos", "tan", "√"],
            ["log", "ln", "abs", "x^y"],
            ["(", ")", "π", "e"],
        ]

        for row, row_values in enumerate(sci_layout):
            for col, label in enumerate(row_values):
                button = self.create_button(label, self.on_scientific_input, "function-button")
                sci_grid.attach(button, col, row, 1, 1)

        standard_grid = Gtk.Grid()
        standard_grid.set_row_spacing(8)
        standard_grid.set_column_spacing(8)
        root.pack_start(standard_grid, True, True, 0)

        layout = [
            ["C", BACKSPACE_SYMBOL, "%", "/"],
            ["7", "8", "9", "*"],
            ["4", "5", "6", "-"],
            ["1", "2", "3", "+"],
            ["+/-", "0", ".", "="],
        ]

        for row, row_values in enumerate(layout):
            for col, label in enumerate(row_values):
                if not label:
                    continue

                style_class = self.resolve_button_style(label)
                button = self.create_button(label, self.on_standard_input, style_class)

                standard_grid.attach(button, col, row, 1, 1)

        return main_display, preview_display, revealer

    def resolve_button_style(self, label: str) -> str:
        if label.isdigit() or label == ".":
            return "number-button"
        if label == BACKSPACE_SYMBOL:
            return "function-button"
        if label == "=":
            return "equals-button"
        return "operator-button"

    def create_button(self, label: str, callback, style_class: str) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.get_style_context().add_class(style_class)
        button.connect("clicked", callback)
        return button

    def on_standard_input(self, button: Gtk.Button) -> None:
        label = button.get_label() or ""
        if label == "C":
            self.clear_all()
        elif label == BACKSPACE_SYMBOL:
            self.backspace()
        elif label == "%":
            self.apply_percent_last_number()
        elif label == "+/-":
            self.toggle_sign_last_number()
        elif label == "=":
            self.commit_result()
        else:
            self.append_token(label)

    def on_scientific_input(self, button: Gtk.Button) -> None:
        label = button.get_label() or ""
        mapping = {
            "sin": "sin(",
            "cos": "cos(",
            "tan": "tan(",
            "√": "sqrt(",
            "log": "log(",
            "ln": "ln(",
            "abs": "abs(",
            "π": "pi",
            "e": "e",
            "x^y": "**",
        }
        self.append_token(mapping.get(label, label))

    def on_toggle_science(self, _button: Gtk.Button) -> None:
        self.state.scientific_mode = not self.state.scientific_mode
        self.revealer.set_reveal_child(self.state.scientific_mode)

    def on_toggle_angle_mode(self, _button: Gtk.Button) -> None:
        self.state.use_degrees = not self.state.use_degrees
        self.angle_button.set_label("Deg" if self.state.use_degrees else "Rad")
        self.recompute_preview()
        self.refresh_displays(show_zero_when_empty=False)

    def clear_all(self) -> None:
        self.state.clear()
        self.refresh_displays()

    def backspace(self) -> None:
        if not self.state.expression:
            self.state.preview = ""
            self.refresh_displays(show_zero_when_empty=False)
            return

        if self.state.expression.endswith("**"):
            self.state.expression = self.state.expression[:-2]
        else:
            self.state.expression = self.state.expression[:-1]
        self.recompute_preview()
        self.refresh_displays(show_zero_when_empty=False)

    def append_token(self, token: str) -> None:
        if token == "^":
            token = "**"

        if not self.can_append_token(token):
            return

        if token == "." and not self.can_append_decimal():
            return

        if token == ")" and not self.can_append_right_parenthesis():
            return

        if self.should_insert_multiply(token):
            self.state.expression += "*"

        if token in {"+", "-", "*", "/"}:
            self.append_operator(token)
        else:
            self.state.expression += token

        self.recompute_preview()
        self.refresh_displays()

    def append_operator(self, operator: str) -> None:
        expression = self.state.expression
        if not expression and operator != "-":
            return

        if expression.endswith(("+", "-", "*", "/")):
            self.state.expression = expression[:-1] + operator
            return

        self.state.expression += operator

    def should_insert_multiply(self, token: str) -> bool:
        expression = self.state.expression
        if not expression:
            return False

        prev = expression[-1]
        token_starts_group = token.startswith(("sin", "cos", "tan", "sqrt", "log", "ln", "abs", "(", "pi", "e"))
        prev_can_multiply = prev.isdigit() or prev in {")", ".", "i", "e"}

        return prev_can_multiply and token_starts_group

    def can_append_token(self, token: str) -> bool:
        if token in {"+", "-", "*", "/", ")"}:
            return True
        return len(self.state.expression) + len(token) <= MAX_EXPRESSION_LENGTH

    def can_append_right_parenthesis(self) -> bool:
        expression = self.state.expression
        if not expression:
            return False

        opens = expression.count("(")
        closes = expression.count(")")
        if opens <= closes:
            return False

        return expression[-1] not in {"+", "-", "*", "/", "("}

    def find_last_number_span(self) -> tuple[int, int] | None:
        expression = self.state.expression
        match = re.search(r"-?\d+(?:\.\d+)?$", expression)
        if match:
            return match.start(), match.end()

        return None

    def apply_percent_last_number(self) -> None:
        span = self.find_last_number_span()
        if not span:
            return

        start, end = span
        value = float(self.state.expression[start:end])
        replacement = self.format_result(value / 100)
        self.state.expression = f"{self.state.expression[:start]}{replacement}{self.state.expression[end:]}"
        self.recompute_preview()
        self.refresh_displays(show_zero_when_empty=False)

    def toggle_sign_last_number(self) -> None:
        if not self.state.expression:
            self.state.expression = "-"
            self.refresh_displays(show_zero_when_empty=False)
            return

        span = self.find_last_number_span()
        if span:
            start, end = span
            token = self.state.expression[start:end]
            if token.startswith("-"):
                replacement = token[1:]
            else:
                replacement = f"-{token}"
            self.state.expression = f"{self.state.expression[:start]}{replacement}{self.state.expression[end:]}"
            self.recompute_preview()
            self.refresh_displays(show_zero_when_empty=False)
            return

        if self.state.expression.endswith(("+", "-", "*", "/", "(")):
            if len(self.state.expression) < MAX_EXPRESSION_LENGTH:
                self.state.expression += "-"
                self.refresh_displays(show_zero_when_empty=False)

    def can_append_decimal(self) -> bool:
        expression = self.state.expression
        if not expression:
            self.state.expression = "0"
            return True

        index = len(expression) - 1
        while index >= 0 and (expression[index].isdigit() or expression[index] == "."):
            index -= 1
        segment = expression[index + 1 :]
        return "." not in segment

    def recompute_preview(self) -> None:
        expression = self.state.expression
        if not expression:
            self.state.preview = ""
            return

        if self.is_expression_incomplete(expression):
            self.state.preview = ""
            return

        try:
            value = self.evaluator.eval(expression)
            self.state.preview = self.format_result(value)
        except ZeroDivisionError:
            self.state.preview = ERROR_DIV_ZERO
        except OverflowError:
            self.state.preview = ERROR_OVERFLOW
        except ValueError:
            self.state.preview = ERROR_DOMAIN
        except (SyntaxError, TypeError):
            self.state.preview = ERROR_SYNTAX
        except Exception:
            self.state.preview = ERROR_GENERIC

    @staticmethod
    def is_expression_incomplete(expression: str) -> bool:
        if not expression:
            return True

        if expression.endswith(("+", "-", "*", "/", "(")):
            return True

        return expression.count("(") > expression.count(")")

    def commit_result(self) -> None:
        if not self.state.preview or self.state.preview in ERROR_MESSAGES:
            return

        self.state.last_result = self.state.preview
        self.state.expression = self.state.last_result
        self.state.preview = ""
        self.refresh_displays()

    def refresh_displays(self, show_zero_when_empty: bool = True) -> None:
        if self.state.expression:
            expression_text = self.state.expression
        else:
            expression_text = "0" if show_zero_when_empty else ""
        self.main_display.set_text(expression_text)
        self.preview_display.set_text(self.state.preview)

    def on_key_press(self, _widget: Gtk.Window, event: Gdk.EventKey) -> bool:
        name = Gdk.keyval_name(event.keyval) or ""
        char = event.string or ""

        if name in {"Return", "KP_Enter"}:
            self.commit_result()
            return True
        if name == "BackSpace":
            self.backspace()
            return True
        if name == "Escape":
            self.clear_all()
            return True

        keypad_map = {
            "KP_0": "0",
            "KP_1": "1",
            "KP_2": "2",
            "KP_3": "3",
            "KP_4": "4",
            "KP_5": "5",
            "KP_6": "6",
            "KP_7": "7",
            "KP_8": "8",
            "KP_9": "9",
            "KP_Decimal": ".",
            "KP_Add": "+",
            "KP_Subtract": "-",
            "KP_Multiply": "*",
            "KP_Divide": "/",
        }

        if name in keypad_map:
            self.append_token(keypad_map[name])
            return True

        if char in "0123456789.+-*/()%":
            if char == "%":
                self.apply_percent_last_number()
                return True
            self.append_token(char)
            return True

        if char == "^":
            self.append_token("**")
            return True

        return False

    @staticmethod
    def format_result(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.10g}"
        return str(value)

    def run(self) -> None:
        self.window.show_all()
        Gtk.main()


def main() -> None:
    app = CalculatorApp()
    app.run()


if __name__ == "__main__":
    main()
