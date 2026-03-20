"""GTK scientific calculator with expression preview and history support."""

import gi  # type: ignore[import-not-found]

gi.require_version("Gtk", "3.0")
import logging
import math
import re
from collections.abc import Callable

from gi.repository import Gdk, GLib, Gtk, Pango  # type: ignore[attr-defined]
from simpleeval import SimpleEval  # type: ignore[import-not-found]


BACKSPACE_SYMBOL = "<="
MAX_EXPRESSION_LENGTH = 120
HISTORY_LIMIT = 12
HISTORY_EXPORT_DEFAULT_NAME = "history.txt"
DEFAULT_WINDOW_WIDTH = 640
DEFAULT_WINDOW_HEIGHT = 1080
MIN_WINDOW_WIDTH = 360
MIN_WINDOW_HEIGHT = 640
DEFAULT_BUTTON_MIN_HEIGHT = 52
LARGE_BUTTON_MIN_HEIGHT = 64
RESIZE_DEBOUNCE_MS = 120
REVEALER_TRANSITION_DURATION_MS = 200
SIZE_TIER_SMALL = "small"
SIZE_TIER_MEDIUM = "medium"
SIZE_TIER_LARGE = "large"
ELLIPSIZE_MODE = Pango.EllipsizeMode.END
ERROR_DIV_ZERO = "Div0"
ERROR_SYNTAX = "语法错误"
ERROR_DOMAIN = "域错误"
ERROR_OVERFLOW = "溢出"
ERROR_GENERIC = "错误"
ERROR_MESSAGES = {ERROR_DIV_ZERO, ERROR_SYNTAX, ERROR_DOMAIN, ERROR_OVERFLOW, ERROR_GENERIC}


LOGGER = logging.getLogger(__name__)


HistoryItem = tuple[str, str]
ButtonCallback = Callable[[Gtk.Button], None]

BINARY_OPERATORS = {"+", "-", "*", "/"}
INCOMPLETE_END_TOKENS = BINARY_OPERATORS | {"("}
FUNCTION_PREFIXES = ("sin", "cos", "tan", "sqrt", "log", "ln", "abs", "(", "pi", "e")


class CalculatorState:
    """表达式驱动状态：主屏显示表达式，预览屏显示实时结果。"""

    def __init__(self) -> None:
        self.expression: str = ""
        self.preview: str = ""
        self.last_result: str = ""
        self.history: list[HistoryItem] = []
        self.scientific_mode: bool = True
        self.history_visible: bool = False
        self.use_degrees: bool = True
        self.dark_mode: bool = True
        self.font_scale: int = 0
        self.button_min_height: int = DEFAULT_BUTTON_MIN_HEIGHT

    def clear(self) -> None:
        self.expression = ""
        self.preview = ""


class CalculatorApp:
    def __init__(self) -> None:
        self.state = CalculatorState()
        self.evaluator = self._create_evaluator()
        self.size_tier = SIZE_TIER_MEDIUM
        self._pending_size_tier = SIZE_TIER_MEDIUM
        self._resize_debounce_id: int | None = None
        self._css_provider = Gtk.CssProvider()

        self.window = Gtk.Window(title="现代计算器")
        self.window.set_default_size(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.window.set_size_request(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.window.set_resizable(True)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("key-press-event", self.on_key_press)
        self.window.connect("configure-event", self.on_window_configure)

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.main_display, self.preview_display, self.revealer = self.build_ui(self.window)
        self.apply_css()
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

    def _determine_size_tier(self, width: int) -> str:
        if width < 420:
            return SIZE_TIER_SMALL
        if width < 700:
            return SIZE_TIER_MEDIUM
        return SIZE_TIER_LARGE

    def _get_size_profile(self) -> dict[str, int]:
        if self.size_tier == SIZE_TIER_SMALL:
            return {
                "main": 34,
                "preview": 18,
                "button": 17,
                "toggle": 13,
                "radius": 12,
                "spacing": 6,
                "edge": 10,
                "shadow": 2,
                "topbar_min": 38,
                "history_min": 110,
            }
        if self.size_tier == SIZE_TIER_LARGE:
            return {
                "main": 48,
                "preview": 24,
                "button": 21,
                "toggle": 16,
                "radius": 16,
                "spacing": 12,
                "edge": 18,
                "shadow": 4,
                "topbar_min": 48,
                "history_min": 180,
            }
        return {
            "main": 40,
            "preview": 20,
            "button": 19,
            "toggle": 14,
            "radius": 14,
            "spacing": 9,
            "edge": 14,
            "shadow": 3,
            "topbar_min": 42,
            "history_min": 140,
        }

    def apply_css(self) -> None:
        profile = self._get_size_profile()
        main_size = profile["main"] + self.state.font_scale * 2
        preview_size = profile["preview"] + self.state.font_scale
        button_size = profile["button"] + self.state.font_scale
        toggle_size = profile["toggle"] + self.state.font_scale
        radius = profile["radius"]
        shadow = profile["shadow"]
        button_min_height = max(profile["topbar_min"], self.state.button_min_height)

        css = f"""
        window,
        grid.app-root {{
            background: #f2f2f2;
        }}

        .dark-mode {{
            transition: all 200ms ease;
        }}

        .light-mode {{
            transition: all 200ms ease;
        }}

        window.dark-mode,
        grid.app-root.dark-mode {{
            background: #1e1e1e;
        }}

        window.light-mode,
        grid.app-root.light-mode {{
            background: #f2f2f2;
        }}

        button {{
            min-height: {button_min_height}px;
            border: none;
            background-image: none;
            outline: none;
            border-radius: {radius}px;
            box-shadow: 0 {shadow}px {shadow * 2}px rgba(0, 0, 0, 0.18);
            padding: 12px 0;
            font-size: {button_size}px;
            font-weight: 400;
            transition: all 180ms ease;
        }}

        button:hover {{
            box-shadow: 0 {shadow + 1}px {shadow * 2 + 2}px rgba(0, 0, 0, 0.24);
        }}

        button:active {{
            box-shadow: 0 {max(1, shadow - 1)}px {max(2, shadow)}px rgba(0, 0, 0, 0.28);
        }}

        .display-main {{
            font-family: "Segoe UI", "Helvetica Neue", "Roboto", sans-serif;
            font-size: {main_size}px;
            font-weight: 600;
            padding: 10px 2px 4px 2px;
        }}

        .display-preview {{
            font-family: "Segoe UI", "Helvetica Neue", "Roboto", sans-serif;
            font-size: {preview_size}px;
            font-weight: 400;
            padding: 0 2px 8px 2px;
        }}

        .dark-mode .display-main {{
            color: #f2f2f4;
        }}

        .dark-mode .display-preview {{
            color: #c7c7cb;
        }}

        .light-mode .display-main {{
            color: #161618;
        }}

        .light-mode .display-preview {{
            color: #5f6368;
        }}

        .btn-number {{
            background: #ffffff;
            color: #000000;
        }}

        .btn-number:hover {{
            background: #f6f7f8;
        }}

        .btn-number:active {{
            background: #eceef0;
        }}

        .btn-operator {{
            background: #ffffff;
            color: #0a84ff;
        }}

        .btn-operator:hover {{
            background: #f2f6ff;
        }}

        .btn-operator:active {{
            background: #e6efff;
        }}

        .btn-equal {{
            background: #0a84ff;
            color: #ffffff;
            font-weight: 600;
        }}

        .btn-equal:hover {{
            background: #2f9aff;
        }}

        .btn-equal:active {{
            background: #006adc;
        }}

        .dark-mode .btn-number {{
            background: #2b2b2b;
            color: #ffffff;
        }}

        .dark-mode .btn-number:hover {{
            background: #373737;
        }}

        .dark-mode .btn-number:active {{
            background: #232323;
        }}

        .dark-mode .btn-operator {{
            background: #2b2b2b;
            color: #0a84ff;
        }}

        .dark-mode .btn-operator:hover {{
            background: #373737;
        }}

        .dark-mode .btn-operator:active {{
            background: #232323;
        }}

        .dark-mode .btn-equal {{
            background: #0a84ff;
            color: #ffffff;
        }}

        .dark-mode .btn-equal:hover {{
            background: #2f9aff;
        }}

        .dark-mode .btn-equal:active {{
            background: #006adc;
        }}

        .btn-func,
        .btn-theme {{
            background: #eceef0;
            color: #2196f3;
            min-height: {profile["topbar_min"]}px;
            min-width: 72px;
            font-size: {toggle_size}px;
            font-weight: 500;
        }}

        .btn-func:hover,
        .btn-theme:hover {{
            background: #dfe3e8;
        }}

        .btn-func:active,
        .btn-theme:active {{
            background: #d2d7dd;
        }}

        .dark-mode .btn-func,
        .dark-mode .btn-theme {{
            background: #3a3a3c;
            color: #ffffff;
        }}

        .dark-mode .btn-func:hover,
        .dark-mode .btn-theme:hover {{
            background: #4a4a4d;
        }}

        .dark-mode .btn-func:active,
        .dark-mode .btn-theme:active {{
            background: #323235;
        }}

        .history-button {{
            background: #ffffff;
            color: #222325;
            border: none;
            background-image: none;
            outline: none;
            border-radius: {max(8, radius - 4)}px;
            padding: 10px 8px;
        }}

        .history-button:hover {{
            background: #f1f3f5;
        }}

        .history-button:active {{
            background: #e6e9ed;
        }}

        .dark-mode .history-button {{
            background: #252528;
            color: #f2f2f4;
        }}

        .dark-mode .history-button:hover {{
            background: #303034;
        }}

        .dark-mode .history-button:active {{
            background: #1f1f23;
        }}
        """

        self._css_provider.load_from_data(css.encode("utf-8"))
        self.apply_theme_mode()
        self._apply_layout_density(profile)

    def apply_theme_mode(self) -> None:
        if not hasattr(self, "root_grid"):
            return

        window_ctx = self.window.get_style_context()
        root_ctx = self.root_grid.get_style_context()

        window_ctx.remove_class("dark-mode")
        window_ctx.remove_class("light-mode")
        root_ctx.remove_class("dark-mode")
        root_ctx.remove_class("light-mode")

        mode_class = "dark-mode" if self.state.dark_mode else "light-mode"
        window_ctx.add_class(mode_class)
        root_ctx.add_class(mode_class)

    def _apply_layout_density(self, profile: dict[str, int]) -> None:
        if not hasattr(self, "root_grid"):
            return

        self.window.set_border_width(profile["edge"])
        self.root_grid.set_row_spacing(profile["spacing"])
        self.root_grid.set_column_spacing(profile["spacing"])
        self.top_grid.set_column_spacing(profile["spacing"])
        self.display_box.set_spacing(max(2, profile["spacing"] // 3))
        self.sci_grid.set_row_spacing(profile["spacing"])
        self.sci_grid.set_column_spacing(profile["spacing"])
        self.standard_grid.set_row_spacing(profile["spacing"])
        self.standard_grid.set_column_spacing(profile["spacing"])
        self.history_scroller.set_min_content_height(profile["history_min"])

    def on_window_configure(self, _widget: Gtk.Window, event: Gdk.EventConfigure) -> bool:
        self._pending_size_tier = self._determine_size_tier(event.width)
        if self._resize_debounce_id is not None:
            GLib.source_remove(self._resize_debounce_id)
        self._resize_debounce_id = GLib.timeout_add(RESIZE_DEBOUNCE_MS, self._on_resize_debounce)
        return False

    def _on_resize_debounce(self) -> bool:
        self._resize_debounce_id = None
        if self._pending_size_tier != self.size_tier:
            self.size_tier = self._pending_size_tier
            self.apply_css()
        return False

    def _build_top_controls(self) -> None:
        self.top_grid = Gtk.Grid()
        self.top_grid.set_hexpand(True)
        self.top_grid.set_column_homogeneous(True)
        self.root_grid.attach(self.top_grid, 0, 0, 1, 1)

        top_buttons: list[tuple[str, ButtonCallback]] = [
            ("Sci", self.on_toggle_science),
            ("Deg", self.on_toggle_angle_mode),
            ("Hist", self.on_toggle_history),
            ("Export", self.on_export_history),
            ("HC", self.on_hc_button_clicked),
            ("A-", self.on_decrease_font),
            ("A+", self.on_increase_font),
            ("Touch", self.on_toggle_touch_size),
        ]

        for index, (label, callback) in enumerate(top_buttons):
            button = self.create_button(label, callback, "btn-func")
            self.top_grid.attach(button, index, 0, 1, 1)
            if label == "Deg":
                self.angle_button = button
            elif label == "Hist":
                self.history_button = button
            elif label == "HC":
                button.get_style_context().add_class("btn-theme")
                self.contrast_button = button
            elif label == "Touch":
                self.touch_button = button

    def _build_display_area(self) -> tuple[Gtk.Label, Gtk.Label]:
        self.display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.display_box.set_hexpand(True)
        self.root_grid.attach(self.display_box, 0, 1, 1, 1)

        main_display = Gtk.Label(label="0")
        main_display.set_halign(Gtk.Align.END)
        main_display.set_xalign(1.0)
        main_display.set_ellipsize(ELLIPSIZE_MODE)
        main_display.get_style_context().add_class("display-main")
        self.display_box.pack_start(main_display, False, False, 0)

        preview_display = Gtk.Label(label="")
        preview_display.set_halign(Gtk.Align.END)
        preview_display.set_xalign(1.0)
        preview_display.get_style_context().add_class("display-preview")
        self.display_box.pack_start(preview_display, False, False, 0)

        return main_display, preview_display

    def _build_history_panel(self) -> None:
        self.history_revealer = Gtk.Revealer()
        self.history_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.history_revealer.set_transition_duration(REVEALER_TRANSITION_DURATION_MS)
        self.history_revealer.set_reveal_child(False)
        self.history_revealer.set_hexpand(True)
        self.root_grid.attach(self.history_revealer, 0, 2, 1, 1)

        self.history_scroller = Gtk.ScrolledWindow()
        self.history_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.history_revealer.add(self.history_scroller)

        self.history_list = Gtk.ListBox()
        self.history_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.history_scroller.add(self.history_list)

    def _build_scientific_panel(self) -> Gtk.Revealer:
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(REVEALER_TRANSITION_DURATION_MS)
        revealer.set_reveal_child(self.state.scientific_mode)
        revealer.set_hexpand(True)
        self.root_grid.attach(revealer, 0, 3, 1, 1)

        self.sci_grid = Gtk.Grid()
        self.sci_grid.set_hexpand(True)
        self.sci_grid.set_vexpand(True)
        self.sci_grid.set_row_homogeneous(True)
        self.sci_grid.set_column_homogeneous(True)
        revealer.add(self.sci_grid)

        sci_layout = [
            ["sin", "cos", "tan", "√"],
            ["log", "ln", "abs", "x^y"],
            ["(", ")", "π", "e"],
        ]

        for row, row_values in enumerate(sci_layout):
            for col, label in enumerate(row_values):
                button = self.create_button(label, self.on_scientific_input, "btn-func")
                self.sci_grid.attach(button, col, row, 1, 1)

        return revealer

    def _build_standard_panel(self) -> None:
        self.standard_grid = Gtk.Grid()
        self.standard_grid.set_hexpand(True)
        self.standard_grid.set_vexpand(True)
        self.standard_grid.set_row_homogeneous(True)
        self.standard_grid.set_column_homogeneous(True)
        self.root_grid.attach(self.standard_grid, 0, 4, 1, 1)

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
                self.standard_grid.attach(button, col, row, 1, 1)

    def build_ui(self, window: Gtk.Window) -> tuple[Gtk.Label, Gtk.Label, Gtk.Revealer]:
        self.root_grid = Gtk.Grid()
        self.root_grid.set_hexpand(True)
        self.root_grid.set_vexpand(True)
        self.root_grid.get_style_context().add_class("app-root")
        window.add(self.root_grid)

        self._build_top_controls()
        main_display, preview_display = self._build_display_area()
        self._build_history_panel()
        revealer = self._build_scientific_panel()
        self._build_standard_panel()

        return main_display, preview_display, revealer

    def resolve_button_style(self, label: str) -> str:
        if label.isdigit() or label == ".":
            return "btn-number"
        if label == "=":
            return "btn-equal"
        return "btn-operator"

    def create_button(
        self,
        label: str,
        callback: Callable[[Gtk.Button], None],
        style_class: str,
    ) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.set_hexpand(True)
        button.set_vexpand(True)
        button.set_can_focus(False)
        button.set_relief(Gtk.ReliefStyle.NONE)
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
        # 切换单位制状态
        self.state.use_degrees = not self.state.use_degrees
        # 关键：重新创建 evaluator，确保三角函数使用最新的单位制状态
        self.evaluator = self._create_evaluator()
        # 更新UI按钮标签
        self.angle_button.set_label("Deg" if self.state.use_degrees else "Rad")
        # 重新计算预览和显示
        self.recompute_preview()
        self.refresh_displays(show_zero_when_empty=False)

    def on_toggle_history(self, _button: Gtk.Button) -> None:
        self.state.history_visible = not self.state.history_visible
        self.history_revealer.set_reveal_child(self.state.history_visible)

    def on_export_history(self, _button: Gtk.Button) -> None:
        if not self.state.history:
            self.state.preview = "无历史可导出"
            self.refresh_displays(show_zero_when_empty=False)
            return

        export_path = self.choose_export_path()
        if not export_path:
            return

        try:
            with open(export_path, "w", encoding="utf-8") as file:
                for expression, result in self.state.history:
                    file.write(f"{expression} = {result}\n")
            self.state.preview = "导出成功"
        except OSError:
            self.state.preview = "导出失败"

        self.refresh_displays(show_zero_when_empty=False)

    def choose_export_path(self) -> str | None:
        dialog = Gtk.FileChooserDialog(
            title="导出历史记录",
            parent=self.window,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,
            Gtk.ResponseType.ACCEPT,
        )
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name(HISTORY_EXPORT_DEFAULT_NAME)

        text_filter = Gtk.FileFilter()
        text_filter.set_name("Text files (*.txt)")
        text_filter.add_pattern("*.txt")
        dialog.add_filter(text_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        response = dialog.run()
        file_path = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()

        return file_path

    def on_hc_button_clicked(self, _button: Gtk.Button) -> None:
        self.state.dark_mode = not self.state.dark_mode
        self.contrast_button.set_label("Dark" if self.state.dark_mode else "Light")
        self.apply_css()

    def on_increase_font(self, _button: Gtk.Button) -> None:
        if self.state.font_scale >= 3:
            return
        self.state.font_scale += 1
        self.apply_css()

    def on_decrease_font(self, _button: Gtk.Button) -> None:
        if self.state.font_scale <= -2:
            return
        self.state.font_scale -= 1
        self.apply_css()

    def on_toggle_touch_size(self, _button: Gtk.Button) -> None:
        if self.state.button_min_height == DEFAULT_BUTTON_MIN_HEIGHT:
            self.state.button_min_height = LARGE_BUTTON_MIN_HEIGHT
            self.touch_button.set_label("Touch+")
        else:
            self.state.button_min_height = DEFAULT_BUTTON_MIN_HEIGHT
            self.touch_button.set_label("Touch")
        self.apply_css()

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

        if token in BINARY_OPERATORS:
            self.append_operator(token)
        else:
            self.state.expression += token

        self.recompute_preview()
        self.refresh_displays()

    def append_operator(self, operator: str) -> None:
        expression = self.state.expression
        if not expression and operator != "-":
            return

        if expression.endswith(tuple(BINARY_OPERATORS)):
            self.state.expression = expression[:-1] + operator
            return

        self.state.expression += operator

    def should_insert_multiply(self, token: str) -> bool:
        expression = self.state.expression
        if not expression:
            return False

        prev = expression[-1]
        token_starts_group = token.startswith(FUNCTION_PREFIXES)
        prev_can_multiply = prev.isdigit() or prev in {")", ".", "i", "e"}

        return prev_can_multiply and token_starts_group

    def can_append_token(self, token: str) -> bool:
        if token in BINARY_OPERATORS or token == ")":
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

        return expression[-1] not in INCOMPLETE_END_TOKENS

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

        if self.state.expression.endswith(tuple(INCOMPLETE_END_TOKENS)):
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
            LOGGER.exception("Unexpected evaluation error for expression: %s", expression)
            self.state.preview = ERROR_GENERIC

    @staticmethod
    def is_expression_incomplete(expression: str) -> bool:
        if not expression:
            return True

        if expression.endswith(tuple(INCOMPLETE_END_TOKENS)):
            return True

        return expression.count("(") > expression.count(")")

    def commit_result(self) -> None:
        if not self.state.preview or self.state.preview in ERROR_MESSAGES:
            return

        self.push_history(self.state.expression, self.state.preview)
        self.state.last_result = self.state.preview
        self.state.expression = self.state.last_result
        self.state.preview = ""
        self.refresh_displays()

    def push_history(self, expression: str, result: str) -> None:
        if not expression or not result:
            return

        item = (expression, result)
        if self.state.history and self.state.history[0] == item:
            return

        self.state.history.insert(0, item)
        self.state.history = self.state.history[:HISTORY_LIMIT]
        self.refresh_history_list()

    def refresh_history_list(self) -> None:
        for row in self.history_list.get_children():
            self.history_list.remove(row)

        for expression, result in self.state.history:
            label = Gtk.Label(label=f"{expression} = {result}")
            label.set_xalign(0.0)
            label.set_ellipsize(ELLIPSIZE_MODE)

            button = Gtk.Button()
            button.add(label)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_style_context().add_class("history-button")
            button.connect("clicked", self.on_history_item_clicked, expression)

            row = Gtk.ListBoxRow()
            row.add(button)
            self.history_list.add(row)

        self.history_list.show_all()

    def on_history_item_clicked(self, _button: Gtk.Button, expression: str) -> None:
        self.state.expression = expression
        self.recompute_preview()
        self.refresh_displays(show_zero_when_empty=False)

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
        is_shift_pressed = bool(event.state & Gdk.ModifierType.SHIFT_MASK)

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

        # Handle operator keys robustly across keyboard layouts/input methods.
        if name == "plus":
            self.append_token("+")
            return True
        if name == "minus":
            self.append_token("-")
            return True
        if name in {"asterisk", "slash"}:
            self.append_token("*" if name == "asterisk" else "/")
            return True
        if name in {"parenleft", "parenright"}:
            self.append_token("(" if name == "parenleft" else ")")
            return True
        if name == "equal" and is_shift_pressed:
            self.append_token("+")
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
