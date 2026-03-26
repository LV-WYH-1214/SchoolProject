"""GTK scientific calculator with expression preview and history support."""  # 文件说明：GTK 科学计算器，支持实时预览和历史记录。

import gi  # type: ignore[import-not-found]  # 导入 PyGObject（GTK 的 Python 绑定）。把 C 库翻译成 Python 能用的形式
#利用gi使用c语言库:Gdk, GLib, Gtk, Pango
gi.require_version("Gtk", "3.0")  # 指定 GTK 主版本，避免加载错误版本。
import logging  # 日志模块：用于记录异常细节。
import math  # 数学函数模块：sin、cos、log、sqrt 等。
import re  # 正则模块：用于匹配“最后一个数字”。   利用re.search从后往前找数字,配合正则表达式\d+(\.\d*)?$来匹配一个数字段,其中\d+表示整数部分至少一位,\.\d*表示可选的小数部分,整个括号表示小数部分可有可无,$表示匹配字符串末尾,确保找到的是最后一个数字。
from collections.abc import Callable  # 用于函数类型标注.  这个标注实现的是说"我这个参数需要一个函数，这个函数务必接收 Gtk.Button，而且不能返回任何东西"
# GTK:GUI 框架（按钮、窗口、菜单等）  GDK:底层图形层（事件、屏幕、颜色）  GLib:时间管理、事件循环   Pango:文本布局和渲染（字体、对齐、截断等）。  这些都是 GTK 应用开发的核心库，提供了构建界面和处理用户交互的基础功能。
from gi.repository import Gdk, GLib, Gtk, Pango  # type: ignore[attr-defined]  # GTK/GDK/GLib/Pango 核心对象。
from simpleeval import SimpleEval  # type: ignore[import-not-found]  # 安全表达式求值器（比 eval 更安全）。

# 注释分层约定：
# 新手层：行尾注释（告诉你“这一行在做什么”）。
# 进阶层：关键函数 docstring 里的“进阶”段（告诉你“为什么这样设计”）。


# ------- 常量区：把常用配置集中在文件开头，后续修改更方便 -------
BACKSPACE_SYMBOL = "<="  # 回删键在界面上的显示文本。

# 输入与历史相关配置
MAX_EXPRESSION_LENGTH = 120  # 表达式最大长度，防止输入过长影响体验。
HISTORY_LIMIT = 12  # 最多保留多少条历史记录。
HISTORY_EXPORT_DEFAULT_NAME = "history.txt"  # 导出历史记录时的默认文件名。

# 窗口与控件尺寸配置
DEFAULT_WINDOW_WIDTH = 640  # 窗口默认宽度（像素）。
DEFAULT_WINDOW_HEIGHT = 1080  # 窗口默认高度（像素）。
MIN_WINDOW_WIDTH = 360  # 允许缩放到的最小宽度。
MIN_WINDOW_HEIGHT = 640  # 允许缩放到的最小高度。
DEFAULT_BUTTON_MIN_HEIGHT = 52  # 普通模式下按钮最小高度。
LARGE_BUTTON_MIN_HEIGHT = 64  # 触控友好模式下按钮最小高度。

# 动画与响应配置
RESIZE_DEBOUNCE_MS = 120  # 窗口缩放防抖时间（毫秒），避免频繁重绘。
REVEALER_TRANSITION_DURATION_MS = 200  # 面板展开/收起的动画时长（毫秒）。

# 尺寸档位标识
SIZE_TIER_SMALL = "small"  # 小窗口档位。
SIZE_TIER_MEDIUM = "medium"  # 中窗口档位。
SIZE_TIER_LARGE = "large"  # 大窗口档位。

# 文本显示策略
ELLIPSIZE_MODE = Pango.EllipsizeMode.END  # 文本太长时，在末尾显示省略号。

# 统一错误提示文本
ERROR_DIV_ZERO = "除零错误"  # 除以 0。
ERROR_SYNTAX = "语法错误"  # 表达式格式不合法。
ERROR_DOMAIN = "域错误"  # 数学定义域错误（如 sqrt(-1)）。
ERROR_OVERFLOW = "溢出"  # 数值过大导致溢出。
ERROR_GENERIC = "错误"  # 其他未分类错误。
ERROR_MESSAGES = {ERROR_DIV_ZERO, ERROR_SYNTAX, ERROR_DOMAIN, ERROR_OVERFLOW, ERROR_GENERIC}  # 所有错误文本集合。


LOGGER = logging.getLogger(__name__)  # 获取当前模块的日志器。


HistoryItem = tuple[str, str]  # 历史项类型：("表达式", "结果")。
ButtonCallback = Callable[[Gtk.Button], None]  # 按钮回调类型：接收一个 Gtk.Button，无返回值。

BINARY_OPERATORS = {"+", "-", "*", "/"}  # 四则运算符集合。
INCOMPLETE_END_TOKENS = BINARY_OPERATORS | {"("}  # 若表达式以这些 token 结尾，视为“未输入完整”。
FUNCTION_PREFIXES = ("sin", "cos", "tan", "sqrt", "log", "ln", "abs", "(", "pi", "e")  # 可触发自动补乘号的前缀。


class CalculatorState:
    """新手：这是“数据仓库”，专门保存当前表达式、预览、历史和界面开关状态。
    进阶：把状态从 UI 代码里抽离，属于轻量的状态分层，便于维护和测试。
    """  # 状态类只存数据，不做 UI 创建。

    def __init__(self) -> None:
        self.expression: str = ""  # 当前表达式（主屏显示内容）。
        self.preview: str = ""  # 实时预览结果（副屏显示内容）。
        self.last_result: str = ""  # 最近一次“等号提交”的结果。
        self.history: list[HistoryItem] = []  # 历史记录列表，新记录放前面。
        self.scientific_mode: bool = True  # 是否显示科学函数面板。
        self.history_visible: bool = False  # 是否显示历史记录面板。
        self.use_degrees: bool = True  # 三角函数是否用角度制（True=Deg，False=Rad）。
        self.dark_mode: bool = True  # 是否为深色模式。
        self.font_scale: int = 0  # 字号缩放，允许范围 -2 到 3。
        self.button_min_height: int = DEFAULT_BUTTON_MIN_HEIGHT  # 按钮最小高度，可切换触控模式。

    def clear(self) -> None:
        self.expression = ""  # 清空表达式。
        self.preview = ""  # 清空预览。


class CalculatorApp:
    """新手：这是应用主类，负责搭界面、接收输入、计算结果、刷新显示。
    进阶:相当于“协调器(orchestrator)”，把 UI 层、状态层、计算层串起来。
    """  # 这是应用入口核心类。

    def __init__(self) -> None:  # 构造函数：创建 CalculatorApp 实例时自动执行。
        self.state = CalculatorState()  # 创建状态对象，集中保存数据状态。
        self.evaluator = self._create_evaluator()  # 创建表达式求值器。
        self.size_tier = SIZE_TIER_MEDIUM  # 当前窗口尺寸档位（small/medium/large）。
        self._pending_size_tier = SIZE_TIER_MEDIUM  # 待应用档位（用于 resize 防抖）。
        self._resize_debounce_id: int | None = None  # 防抖定时器 ID；None 表示当前没有定时器。
        self._css_provider = Gtk.CssProvider()  # CSS 提供器：用于运行时动态注入样式。

        self.window = Gtk.Window(title="现代计算器")  # 创建主窗口并设置标题。
        self.window.set_default_size(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)  # 设默认窗口大小。
        self.window.set_size_request(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)  # 设窗口最小可缩放尺寸。
        self.window.set_resizable(True)  # 允许用户拖拽改变窗口大小。
        self.window.connect("destroy", Gtk.main_quit)  # 关闭窗口时退出 GTK 主循环。
        self.window.connect("key-press-event", self.on_key_press)  # 键盘输入事件绑定。
        self.window.connect("configure-event", self.on_window_configure)  # 窗口尺寸变化事件绑定。

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),  # 默认屏幕对象。
            self._css_provider,  # 我们自定义的 CSS 样式源。
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,  # 应用级优先级。
        )

        self.main_display, self.preview_display, self.revealer = self.build_ui(self.window)  # 构建全部 UI 控件。
        # 上面先调用方法，再把返回值“拆包”到3个实例属性里。
        self.apply_css()  # 首次应用样式 。
        self.refresh_displays()  # 首次刷新显示文本。

    def _create_evaluator(self) -> SimpleEval:# 这里的意思是返回一个配置好的 SimpleEval 实例，供后续计算表达式时使用。真正创建对象在138行,后续计算使用的是self.evaluator.eval(expression),952行
        """新手:创建计算引擎,并告诉它能用哪些函数(sin/log 等)和常量(pi/e)。
        进阶：用白名单注册函数是安全策略，避免执行任意 Python 代码。
        """  # 所有可用函数都在这里白名单注册。只有白名单里面的函数和常量才能在表达式里使用，增强安全性。

        def to_radians(value: float) -> float:
            return math.radians(value) if self.state.use_degrees else value  # 角度制转弧度；弧度制原样返回。

        def sin_fn(value: float) -> float:
            return math.sin(to_radians(value))  # sin 包装，兼容 Deg/Rad 两种模式。

        def cos_fn(value: float) -> float:
            return math.cos(to_radians(value))  # cos 包装。

        def tan_fn(value: float) -> float:
            return math.tan(to_radians(value))  # tan 包装。

        evaluator = SimpleEval()  # 新建求值器。
        evaluator.functions = { #这里是利用SimpleEval自带的函数白名单能力,告诉计算器有些什么可以使用
            "sin": sin_fn,  # 注册 sin。
            "cos": cos_fn,  # 注册 cos。
            "tan": tan_fn,  # 注册 tan。
            "sqrt": math.sqrt,  # 注册平方根。
            "log": math.log10,  # 注册常用对数 log10。
            "ln": math.log,  # 注册自然对数。
            "abs": abs,  # 注册绝对值。
        }
        evaluator.names = {
            "pi": math.pi,  # 注册常量 pi。
            "e": math.e,  # 注册常量 e。
        }
        return evaluator  # 返回配置好的求值器。

    def _determine_size_tier(self, width: int) -> str:
        """根据窗口宽度返回尺寸档位（小/中/大）。"""  # 用于响应式布局。但是対大小有最小限制
        if width < 420:  # 宽度小于 420。
            return SIZE_TIER_SMALL  # 使用小档位。
        if width < 700:  # 宽度在 [420, 700) 区间。
            return SIZE_TIER_MEDIUM  # 使用中档位。
        return SIZE_TIER_LARGE  # 其余情况使用大档位。

    def _get_size_profile(self) -> dict[str, int]:
        """按当前尺寸档位返回一组 UI 尺寸参数。"""  # 用一个 dict 统一管理字号、间距等。
        if self.size_tier == SIZE_TIER_SMALL:  # 小档位参数。
            return {
                "main": 34,  # 主显示字号。
                "preview": 18,  # 预览字号。
                "button": 17,  # 按钮字号。
                "toggle": 13,  # 顶部开关按钮字号。
                "radius": 12,  # 圆角大小。
                "spacing": 6,  # 网格间距。
                "edge": 10,  # 窗口边距。
                "shadow": 2,  # 阴影强度。
                "topbar_min": 38,  # 顶部按钮最小高度。
                "history_min": 110,  # 历史区域最小高度。
            }
        if self.size_tier == SIZE_TIER_LARGE:  # 大档位参数。
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
        return {  # 中档位参数（默认）。
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
        """新手：把字号、主题、间距等参数写进 CSS人,然后立即应用到界面。
        进阶：采用“状态 -> 样式字符串 -> 一次性注入”的方式，能集中管理视觉规则。
        """  # 每次主题/字号/尺寸变化都会调用。
        profile = self._get_size_profile()  # 获取当前档位尺寸参数。
        main_size = profile["main"] + self.state.font_scale * 2  # 主显示字号：缩放影响更明显。通过利用这个front_scale参数,用户可以在原有基础上微调字号,满足个性化需求,并且实现不同区域不同程度的调节功能。因为主显示通常是界面视觉焦点，所以放大效果更明显一些。
        preview_size = profile["preview"] + self.state.font_scale  # 预览字号。
        button_size = profile["button"] + self.state.font_scale  # 普通按钮字号。
        toggle_size = profile["toggle"] + self.state.font_scale  # 顶部按钮字号。
        radius = profile["radius"]  # 圆角值。
        shadow = profile["shadow"]  # 阴影级别。
        button_min_height = max(profile["topbar_min"], self.state.button_min_height)  # 最小按钮高度取两者较大值。
        # 这里下面其实就是外观设计,通过使用比如button_min_height这样的变量,我们可以让界面在不同尺寸和用户偏好下都保持美观和易用。CSS 模板字符串，里面可以用 {变量} 来插入 Python 变量值。
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
        """  # CSS 模板字符串结束。

        self._css_provider.load_from_data(css.encode("utf-8"))  # 把 CSS 字符串加载给 GTK。
        self.apply_theme_mode()  # 同步深浅色类名。
        self._apply_layout_density(profile)  # 同步边距/间距等布局参数。

    def apply_theme_mode(self) -> None: # 这个下面的root是根容器(root_grid),window是窗口,切换主题需要同时改两者的类名
        """切换 root 和 window 的主题类名(dark-mode / light-mode)。"""  # 主题切换只改 class，不重建控件。
        if not hasattr(self, "root_grid"):  # 防御：界面尚未构建时直接返回。  hasattr: python 内置函数，检查对象是否有指定属性。这里用来判断界面是否已经构建完成，因为切主题需要改样式类，如果界面还没构建好就改类会出问题，所以先检查一下 root_grid 属性是否存在，不存在就直接返回
            return

        window_ctx = self.window.get_style_context()  # 窗口样式上下文。
        root_ctx = self.root_grid.get_style_context()  # 根网格样式上下文。

        window_ctx.remove_class("dark-mode")  # 先清掉旧主题类。有三个目的:1.防止冲突（万一之前是 dark 模式，现在要切 light，如果不先移除 dark-mode 类，两个主题类就会共存，导致样式混乱）。2.保证结果稳定(先清空再添加目标类，最后一定只有一个主题类，切换行为每次都一致)。3.避免历史残留用户连续点多次切换时，不会越切越乱，逻辑是幂等的（每次都重置到干净状态）。
        window_ctx.remove_class("light-mode")
        root_ctx.remove_class("dark-mode")
        root_ctx.remove_class("light-mode")

        mode_class = "dark-mode" if self.state.dark_mode else "light-mode"  # 依据状态决定目标主题类。
        window_ctx.add_class(mode_class)  # 给窗口添加主题类。
        root_ctx.add_class(mode_class)  # 给根网格添加主题类。  网格:1.管布局(谁在第几行几列) 2.管间距(行距列距) 3.管样式范围(给网格加类，网格里所有控件都受影响)。所以切主题时给根网格加类，整个界面都能跟着变。

    def _apply_layout_density(self, profile: dict[str, int]) -> None:
        """把 spacing、边距、历史区高度等布局参数应用到控件。"""  # 响应式布局参数统一在这里更新。
        if not hasattr(self, "root_grid"):  # 防御判断。
            return

        self.window.set_border_width(profile["edge"])  # 设置窗口边距。
        self.root_grid.set_row_spacing(profile["spacing"])  # 根网格行间距。
        self.root_grid.set_column_spacing(profile["spacing"])  # 根网格列间距。
        self.top_grid.set_column_spacing(profile["spacing"])  # 顶部按钮列间距。
        self.display_box.set_spacing(max(2, profile["spacing"] // 3))  # 显示区上下间距。
        self.sci_grid.set_row_spacing(profile["spacing"])  # 科学面板行间距。
        self.sci_grid.set_column_spacing(profile["spacing"])  # 科学面板列间距。
        self.standard_grid.set_row_spacing(profile["spacing"])  # 标准面板行间距。
        self.standard_grid.set_column_spacing(profile["spacing"])  # 标准面板列间距。
        self.history_scroller.set_min_content_height(profile["history_min"])  # 历史区最小高度。

    def on_window_configure(self, _widget: Gtk.Window, event: Gdk.EventConfigure) -> bool:
        """窗口尺寸变化时触发：记录目标档位并开启防抖。"""  # 避免拖拽时频繁重算样式。
        self._pending_size_tier = self._determine_size_tier(event.width)  # 根据新宽度计算待应用档位。
        if self._resize_debounce_id is not None:  # 如果已有定时器在等。   这里利用了 GLib(GTK + library).timeout_add 返回的 ID 来判断是否已有防抖定时器在等待执行，如果有就先取消它，确保在持续调整窗口大小时不会积累多个定时器，导致过多无效调用。
            GLib.source_remove(self._resize_debounce_id)  # 先取消旧定时器。
        self._resize_debounce_id = GLib.timeout_add(RESIZE_DEBOUNCE_MS, self._on_resize_debounce)  # 启动新定时器。  这句的含义:安排一个 120ms 后执行的回调任务，并把这个任务的 ID 保存到 self._resize_debounce_id 里，以便后续可能需要取消它。回调函数是 self._on_resize_debounce，这个函数会在 120ms 后被调用，来检查是否真的需要更新界面布局。
        return False  # 返回 False 让事件继续传递给 GTK 默认处理。

    def _on_resize_debounce(self) -> bool:
        """防抖定时器回调：只在档位变化时重刷 CSS。"""  # 这是 timeout_add 的回调函数。
        self._resize_debounce_id = None  # 标记当前没有挂起的防抖任务。
        if self._pending_size_tier != self.size_tier:  # 仅当档位真的变化才执行。
            self.size_tier = self._pending_size_tier  # 更新当前档位。
            self.apply_css()  # 重新应用样式和布局。
        return False  # False 表示定时器执行一次后不再重复。

    def _build_top_controls(self) -> None:
        """创建顶部功能按钮区。"""  # 包含 Sci、Deg、Hist、Export、HC、A-/A+、Touch。
        self.top_grid = Gtk.Grid()  # 创建网格容器。
        self.top_grid.set_hexpand(True)  # 横向可扩展。
        self.top_grid.set_column_homogeneous(True)  # 每列等宽。
        self.root_grid.attach(self.top_grid, 0, 0, 1, 1)  # 挂到根网格第 0 行。

        top_buttons: list[tuple[str, ButtonCallback]] = [  # 顶部按钮定义列表。
            ("Sci", self.on_toggle_science),  # 科学面板开关。
            ("Deg", self.on_toggle_angle_mode),  # 角度/弧度开关。
            ("Hist", self.on_toggle_history),  # 历史面板开关。
            ("Export", self.on_export_history),  # 导出历史。
            ("HC", self.on_hc_button_clicked),  # 高对比（深浅色）开关。
            ("A-", self.on_decrease_font),  # 减小字号。
            ("A+", self.on_increase_font),  # 增大字号。
            ("Touch", self.on_toggle_touch_size),  # 触控大按钮开关。
        ]

        for index, (label, callback) in enumerate(top_buttons):  # 遍历每个按钮配置。
            button = self.create_button(label, callback, "btn-func")  # 创建按钮并套上功能按钮样式。
            self.top_grid.attach(button, index, 0, 1, 1)  # 按顺序放到网格中。
            if label == "Deg":  # 保存引用：后面要改按钮文本（Deg/Rad）。
                self.angle_button = button
            elif label == "Hist":  # 保存历史按钮引用（便于后续扩展）。
                self.history_button = button
            elif label == "HC":  # HC 单独添加一个主题类。
                button.get_style_context().add_class("btn-theme") # 给这个按钮额外加了 btn-theme 样式类，让它外观和普通功能按钮有区分。
                self.contrast_button = button  # 保存引用：切主题时要改文字。  把按钮对象保存到 self.contrast_button，后面切换主题时要改它的文字（Dark/Light）。
            elif label == "Touch":  # 保存触控按钮引用：切换时改文字。
                self.touch_button = button

    def _build_display_area(self) -> tuple[Gtk.Label, Gtk.Label]:
        """创建主显示区（表达式）和预览区（实时结果）。"""  # 返回两个 Label 供后续刷新。
        self.display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)  # 竖直布局容器。
        self.display_box.set_hexpand(True)  # 横向可扩展。
        self.root_grid.attach(self.display_box, 0, 1, 1, 1)  # 放到根网格第 1 行。

        main_display = Gtk.Label(label="0")  # 主显示初始值为 0。
        main_display.set_halign(Gtk.Align.END)  # 控件靠右。
        main_display.set_xalign(1.0)  # 文本右对齐。
        main_display.set_ellipsize(ELLIPSIZE_MODE)  # 太长时末尾省略。
        main_display.get_style_context().add_class("display-main")  # 主显示样式类。
        self.display_box.pack_start(main_display, False, False, 0)  # 放入容器。

        preview_display = Gtk.Label(label="")  # 预览初始为空。
        preview_display.set_halign(Gtk.Align.END)  # 控件靠右。
        preview_display.set_xalign(1.0)  # 文本右对齐。
        preview_display.get_style_context().add_class("display-preview")  # 预览样式类。
        self.display_box.pack_start(preview_display, False, False, 0)  # 放入容器。

        return main_display, preview_display  # 返回两个显示控件。

    def _build_history_panel(self) -> None:
        """创建历史记录面板（默认隐藏）。"""  # 使用 Revealer(可折叠容器) 实现平滑展开收起。
        self.history_revealer = Gtk.Revealer()  # 可折叠容器。
        self.history_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)  # 动画：向下滑出。
        self.history_revealer.set_transition_duration(REVEALER_TRANSITION_DURATION_MS)  # 动画时长。
        self.history_revealer.set_reveal_child(False)  # 初始隐藏。
        self.history_revealer.set_hexpand(True)  # 横向扩展。
        self.root_grid.attach(self.history_revealer, 0, 2, 1, 1)  # 放到第 2 行。

        self.history_scroller = Gtk.ScrolledWindow()  # 滚动容器，防止历史太长撑爆界面。
        self.history_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)  # 仅垂直滚动。
        self.history_revealer.add(self.history_scroller)  # 滚动容器放入 revealer。

        self.history_list = Gtk.ListBox()  # 历史列表控件。
        self.history_list.set_selection_mode(Gtk.SelectionMode.NONE)  # 禁用默认选中效果。
        self.history_scroller.add(self.history_list)  # 把列表放进滚动容器。

    def _build_scientific_panel(self) -> Gtk.Revealer:
        """创建科学函数面板（可显示/隐藏）。"""  # 包括 sin/cos/tan/ln/log 等按钮。
        revealer = Gtk.Revealer()  # 创建可折叠容器。
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)  # 设置展开动画。
        revealer.set_transition_duration(REVEALER_TRANSITION_DURATION_MS)  # 设置动画时长。
        revealer.set_reveal_child(self.state.scientific_mode)  # 初始是否显示由状态决定。
        revealer.set_hexpand(True)  # 横向扩展。
        self.root_grid.attach(revealer, 0, 3, 1, 1)  # 放到第 3 行。

        self.sci_grid = Gtk.Grid()  # 科学按钮网格。
        self.sci_grid.set_hexpand(True)  # 横向扩展。
        self.sci_grid.set_vexpand(True)  # 纵向扩展。
        self.sci_grid.set_row_homogeneous(True)  # 行等高。
        self.sci_grid.set_column_homogeneous(True)  # 列等宽。
        revealer.add(self.sci_grid)  # 网格放进 revealer。

        sci_layout = [  # 科学按钮布局矩阵。
            ["sin", "cos", "tan", "√"],
            ["log", "ln", "abs", "x^y"],
            ["(", ")", "π", "e"],
        ]

        for row, row_values in enumerate(sci_layout):  # 遍历每一行。
            for col, label in enumerate(row_values):  # 遍历每一列。
                button = self.create_button(label, self.on_scientific_input, "btn-func")  # 创建功能按钮。
                self.sci_grid.attach(button, col, row, 1, 1)  # 放入网格对应位置。

        return revealer  # 返回 revealer 以便外部控制显隐。

    def _build_standard_panel(self) -> None:
        """创建标准数字与运算按钮面板。"""  # 包括 0-9、四则、清空、等号。
        self.standard_grid = Gtk.Grid()  # 标准面板网格。
        self.standard_grid.set_hexpand(True)  # 横向扩展。
        self.standard_grid.set_vexpand(True)  # 纵向扩展。
        self.standard_grid.set_row_homogeneous(True)  # 行等高。
        self.standard_grid.set_column_homogeneous(True)  # 列等宽。
        self.root_grid.attach(self.standard_grid, 0, 4, 1, 1)  # 放到第 4 行。

        layout = [  # 标准键盘布局。
            ["C", BACKSPACE_SYMBOL, "%", "/"],
            ["7", "8", "9", "*"],
            ["4", "5", "6", "-"],
            ["1", "2", "3", "+"],
            ["+/-", "0", ".", "="],
        ]

        for row, row_values in enumerate(layout):  # 遍历行。
            for col, label in enumerate(row_values):  # 遍历列。
                if not label:  # 预留空位时跳过。
                    continue

                style_class = self.resolve_button_style(label)  # 根据文本决定样式。
                button = self.create_button(label, self.on_standard_input, style_class)  # 创建标准按钮。
                self.standard_grid.attach(button, col, row, 1, 1)  # 放入网格。

    def build_ui(self, window: Gtk.Window) -> tuple[Gtk.Label, Gtk.Label, Gtk.Revealer]:
        """组装整套界面，并返回关键显示控件引用。"""  # 统一在一个方法里构建结构。
        self.root_grid = Gtk.Grid()  # 创建根网格。
        self.root_grid.set_hexpand(True)  # 横向扩展。
        self.root_grid.set_vexpand(True)  # 纵向扩展。
        self.root_grid.get_style_context().add_class("app-root")  # 添加根样式类。
        window.add(self.root_grid)  # 根网格挂到窗口。

        self._build_top_controls()  # 构建顶部按钮区。
        main_display, preview_display = self._build_display_area()  # 构建显示区。
        self._build_history_panel()  # 构建历史面板。
        revealer = self._build_scientific_panel()  # 构建科学面板。
        self._build_standard_panel()  # 构建标准面板。

        return main_display, preview_display, revealer  # 返回关键控件。

    def resolve_button_style(self, label: str) -> str:
        """根据按钮文本决定样式类型。"""  # 数字、运算符、等号颜色不同。
        if label.isdigit() or label == ".":  # 数字或小数点。
            return "btn-number"  # 返回数字按钮样式。
        if label == "=":  # 等号按钮。
            return "btn-equal"  # 返回等号样式。
        return "btn-operator"  # 其余默认运算符样式。

    def create_button(
        self,
        label: str,
        callback: Callable[[Gtk.Button], None],
        style_class: str,
    ) -> Gtk.Button:
        """创建一个按钮并绑定样式与点击事件。"""  # 按钮创建逻辑集中，避免重复代码。
        button = Gtk.Button(label=label)  # 创建按钮并设置文本。
        button.set_hexpand(True)  # 横向填充。
        button.set_vexpand(True)  # 纵向填充。
        button.set_can_focus(False)  # 点击后不抢焦点。
        button.set_relief(Gtk.ReliefStyle.NONE)  # 去掉默认凸起边框。
        button.get_style_context().add_class(style_class)  # 添加 CSS 类。
        button.connect("clicked", callback)  # 绑定点击事件。
        return button  # 返回按钮对象。

    def on_standard_input(self, button: Gtk.Button) -> None:
        """处理标准按键（数字、运算符、清空、回删、等号）。"""  # 所有标准区按钮都走这里。
        label = button.get_label() or ""  # 读取按钮文本，兜底空字符串。
        if label == "C":  # 清空键。
            self.clear_all()  # 清空表达式与预览。
        elif label == BACKSPACE_SYMBOL:  # 回删键。
            self.backspace()  # 删除末尾 token。
        elif label == "%":  # 百分号。
            self.apply_percent_last_number()  # 最后一个数字除以 100。
        elif label == "+/-":  # 正负切换。
            self.toggle_sign_last_number()  # 切换最后一个数字符号。
        elif label == "=":  # 等号。
            self.commit_result()  # 提交预览结果。
        else:  # 其余（数字、点、运算符）。
            self.append_token(label)  # 统一追加 token。

    def on_scientific_input(self, button: Gtk.Button) -> None:
        """把科学面板按钮映射成内部表达式 token。"""  # 比如 x^y 映射到 **。
        label = button.get_label() or ""  # 读取按钮文本。
        mapping = {  # UI 文本 -> 计算表达式 token 映射。
            "sin": "sin(",  # 自动补左括号，便于继续输入参数。
            "cos": "cos(",
            "tan": "tan(",
            "√": "sqrt(",
            "log": "log(",
            "ln": "ln(",
            "abs": "abs(",
            "π": "pi",  # 内部常量名使用 pi。
            "e": "e",  # e 与内部常量同名。
            "x^y": "**",  # 幂运算用 Python 的 **。
        }
        self.append_token(mapping.get(label, label))  # 映射不到时原样使用。

    def on_toggle_science(self, _button: Gtk.Button) -> None:
        """显示/隐藏科学函数面板。"""  # 点击 Sci 按钮调用。
        self.state.scientific_mode = not self.state.scientific_mode  # 取反开关状态。
        self.revealer.set_reveal_child(self.state.scientific_mode)  # 按状态显示/隐藏。

    def on_toggle_angle_mode(self, _button: Gtk.Button) -> None:
        """切换三角函数角度制/弧度制。"""  # Deg <-> Rad。
        self.state.use_degrees = not self.state.use_degrees  # 反转单位制状态。
        self.evaluator = self._create_evaluator()  # 重新构建 evaluator，让 sin/cos/tan 读取新状态。
        self.angle_button.set_label("Deg" if self.state.use_degrees else "Rad")  # 同步按钮文本。
        self.recompute_preview()  # 立刻重算预览。
        self.refresh_displays(show_zero_when_empty=False)  # 刷新显示，不强制显示 0。

    def on_toggle_history(self, _button: Gtk.Button) -> None:
        """显示/隐藏历史记录面板。"""  # 点击 Hist 按钮调用。
        self.state.history_visible = not self.state.history_visible  # 反转可见状态。
        self.history_revealer.set_reveal_child(self.state.history_visible)  # 设置面板显隐。

    def on_export_history(self, _button: Gtk.Button) -> None:
        """导出历史记录到文本文件。"""  # 点击 Export 按钮调用。
        if not self.state.history:  # 没有历史可导出。
            self.state.preview = "无历史可导出"  # 在预览区提示用户。
            self.refresh_displays(show_zero_when_empty=False)  # 刷新界面。
            return  # 结束函数。

        export_path = self.choose_export_path()  # 打开保存对话框，让用户选路径。
        if not export_path:  # 用户取消保存。
            return  # 直接返回。

        try:  # 尝试写文件。
            with open(export_path, "w", encoding="utf-8") as file:  # 以 UTF-8 文本写入。
                for expression, result in self.state.history:  # 遍历每条历史。
                    file.write(f"{expression} = {result}\n")  # 按“表达式 = 结果”写一行。
            self.state.preview = "导出成功"  # 成功提示。
        except OSError:  # 文件权限、路径等系统错误。
            self.state.preview = "导出失败"  # 失败提示。

        self.refresh_displays(show_zero_when_empty=False)  # 导出后刷新显示。

    def choose_export_path(self) -> str | None:
        """打开“另存为”对话框，让用户选择导出路径。"""  # 返回路径或 None。
        dialog = Gtk.FileChooserDialog(
            title="导出历史记录",  # 对话框标题。
            parent=self.window,  # 父窗口。
            action=Gtk.FileChooserAction.SAVE,  # 保存模式。
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,  # 取消按钮文案。
            Gtk.ResponseType.CANCEL,  # 取消返回码。
            Gtk.STOCK_SAVE,  # 保存按钮文案。
            Gtk.ResponseType.ACCEPT,  # 保存返回码。
        )
        dialog.set_do_overwrite_confirmation(True)  # 若文件存在，要求覆盖确认。
        dialog.set_current_name(HISTORY_EXPORT_DEFAULT_NAME)  # 预填默认文件名。

        text_filter = Gtk.FileFilter()  # 文本文件过滤器。
        text_filter.set_name("Text files (*.txt)")  # 过滤器名称。
        text_filter.add_pattern("*.txt")  # 匹配规则。
        dialog.add_filter(text_filter)  # 添加到对话框。

        all_filter = Gtk.FileFilter()  # 全部文件过滤器。
        all_filter.set_name("All files")  # 名称。
        all_filter.add_pattern("*")  # 匹配全部。
        dialog.add_filter(all_filter)  # 添加到对话框。

        response = dialog.run()  # 阻塞等待用户操作。
        file_path = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None  # 接受则取路径。
        dialog.destroy()  # 释放对话框资源。

        return file_path  # 返回用户选择结果。

    def on_hc_button_clicked(self, _button: Gtk.Button) -> None:
        """切换明/暗主题并立即刷新样式。"""  # HC 按钮点击回调。
        self.state.dark_mode = not self.state.dark_mode  # 切换深浅色。
        self.contrast_button.set_label("Dark" if self.state.dark_mode else "Light")  # 更新按钮文字。
        self.apply_css()  # 重新应用样式。

    def on_increase_font(self, _button: Gtk.Button) -> None:
        """增大字号(上限 3)。"""  # A+ 按钮点击回调。
        if self.state.font_scale >= 3:  # 到达上限。
            return  # 不再增加。
        self.state.font_scale += 1  # 字号缩放 +1。
        self.apply_css()  # 重新套用样式。

    def on_decrease_font(self, _button: Gtk.Button) -> None:
        """减小字号（下限 -2)。"""  # A- 按钮点击回调。
        if self.state.font_scale <= -2:  # 到达下限。
            return  # 不再减小。
        self.state.font_scale -= 1  # 字号缩放 -1。
        self.apply_css()  # 重新套用样式。

    def on_toggle_touch_size(self, _button: Gtk.Button) -> None:
        """切换按钮高度，提升触屏点击体验。"""  # Touch 按钮点击回调。
        if self.state.button_min_height == DEFAULT_BUTTON_MIN_HEIGHT:  # 当前是普通高度。
            self.state.button_min_height = LARGE_BUTTON_MIN_HEIGHT  # 切到更大按钮。
            self.touch_button.set_label("Touch+")  # 按钮文本提示已增强。
        else:  # 当前已是增强高度。
            self.state.button_min_height = DEFAULT_BUTTON_MIN_HEIGHT  # 切回默认高度。
            self.touch_button.set_label("Touch")  # 恢复文本。
        self.apply_css()  # 应用新高度。

    def clear_all(self) -> None:
        """清空表达式与预览。"""  # C 键功能。
        self.state.clear()  # 调用状态对象清空。
        self.refresh_displays()  # 更新显示。

    def backspace(self) -> None:
        """回删一个 token;若末尾是 **，一次删两位。"""  # 解决幂运算符删一半的问题。
        if not self.state.expression:  # 没有可删内容。
            self.state.preview = ""  # 清空预览。
            self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。
            return  # 直接结束。

        if self.state.expression.endswith("**"):  # 末尾是幂运算符。
            self.state.expression = self.state.expression[:-2]  # 删除两个字符。
        else:  # 其他普通情况。
            self.state.expression = self.state.expression[:-1]  # 删除一个字符。
        self.recompute_preview()  # 删除后重算预览。
        self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。

    def append_token(self, token: str) -> None:
        """新手：把按键转换成表达式字符，做合法性检查后再追加，并实时计算预览。
        进阶：这里是“输入网关”，统一处理自动补乘号、括号规则和运算符替换。
        """  # 所有输入最终都走这里。
        if token == "^":  # 如果是 ^。
            token = "**"  # 转成 Python 幂运算符。

        if not self.can_append_token(token):  # 长度或规则不允许。
            return  # 拒绝追加。

        if token == "." and not self.can_append_decimal():  # 小数点合法性检查失败。
            return  # 拒绝追加。

        if token == ")" and not self.can_append_right_parenthesis():  # 右括号检查失败。
            return  # 拒绝追加。

        if self.should_insert_multiply(token):  # 需要自动补乘号。
            self.state.expression += "*"  # 先补一个 *。

        if token in BINARY_OPERATORS:  # 若是二元运算符。
            self.append_operator(token)  # 用专门逻辑处理（可替换末尾运算符）。
        else:  # 若不是二元运算符。
            self.state.expression += token  # 直接追加。

        self.recompute_preview()  # 输入后实时重算预览。
        self.refresh_displays()  # 输入后刷新显示。

    def append_operator(self, operator: str) -> None:
        """追加二元运算符；若末尾已是运算符则直接替换。"""  # 防止出现 ++、+- 这种连续符号混乱。
        expression = self.state.expression  # 取当前表达式。
        if not expression and operator != "-":  # 开头只允许负号，不允许 +*/。
            return  # 非法则返回。

        if expression.endswith(tuple(BINARY_OPERATORS)):  # 末尾已经是运算符。
            self.state.expression = expression[:-1] + operator  # 替换末尾运算符。
            return  # 结束。

        self.state.expression += operator  # 正常追加运算符。

    def should_insert_multiply(self, token: str) -> bool:
        """判断是否需要自动补乘号。"""  # 例如 2( -> 2*(，2sin( -> 2*sin(。
        expression = self.state.expression  # 取当前表达式。
        if not expression:  # 空表达式无需补乘。
            return False

        prev = expression[-1]  # 取当前末尾字符。
        token_starts_group = token.startswith(FUNCTION_PREFIXES)  # 新 token 是否以函数/括号/常量开头。
        prev_can_multiply = prev.isdigit() or prev in {")", ".", "i", "e"}  # 前一位是否可与后面隐式相乘。

        return prev_can_multiply and token_starts_group  # 同时满足才补乘号。

    def can_append_token(self, token: str) -> bool:
        """控制表达式最大长度，避免输入过长。"""  # 运算符和右括号允许继续输入。
        if token in BINARY_OPERATORS or token == ")":  # 运算符和右括号先放行。
            return True
        return len(self.state.expression) + len(token) <= MAX_EXPRESSION_LENGTH  # 其他 token 做长度限制。

    def can_append_right_parenthesis(self) -> bool:
        """右括号合法性检查：右括号数量不能超过左括号。"""  # 同时不能跟在不完整 token 后。
        expression = self.state.expression  # 当前表达式。
        if not expression:  # 空表达式不能直接加右括号。
            return False

        opens = expression.count("(")  # 左括号数量。
        closes = expression.count(")")  # 右括号数量。
        if opens <= closes:  # 若左括号不多于右括号。
            return False  # 说明再加右括号会不平衡。

        return expression[-1] not in INCOMPLETE_END_TOKENS  # 末尾不能是运算符或左括号。

    def find_last_number_span(self) -> tuple[int, int] | None:
        """查找表达式尾部最后一个数字片段的位置范围。"""  # 用于 % 和 +/-。
        expression = self.state.expression  # 当前表达式。
        match = re.search(r"-?\d+(?:\.\d+)?$", expression)  # 匹配结尾处的整数/小数（可负号）。
        if match:  # 匹配成功。
            return match.start(), match.end()  # 返回 [start, end) 区间。

        return None  # 没找到数字片段。

    def apply_percent_last_number(self) -> None:
        """把最后一个数字转换成百分数（除以 100)。"""  # 例如 50 -> 0.5。
        span = self.find_last_number_span()  # 找最后一个数字范围。
        if not span:  # 如果找不到数字。
            return  # 直接返回。

        start, end = span  # 解包范围。
        value = float(self.state.expression[start:end])  # 把数字片段转 float。
        replacement = self.format_result(value / 100)  # 计算百分数并格式化。
        self.state.expression = f"{self.state.expression[:start]}{replacement}{self.state.expression[end:]}"  # 替换原数字片段。
        self.recompute_preview()  # 重算预览。
        self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。

    def toggle_sign_last_number(self) -> None:
        """切换最后一个数字的正负号。"""  # +/- 键逻辑。
        if not self.state.expression:  # 空表达式时。
            self.state.expression = "-"  # 直接输入负号起头。
            self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。
            return  # 结束。

        span = self.find_last_number_span()  # 找最后一个数字。
        if span:  # 找到了数字。
            start, end = span  # 解包范围。
            token = self.state.expression[start:end]  # 取出该数字文本。
            if token.startswith("-"):  # 如果本来是负数。
                replacement = token[1:]  # 去掉负号变正数。
            else:  # 如果本来是正数。
                replacement = f"-{token}"  # 加上负号变负数。
            self.state.expression = f"{self.state.expression[:start]}{replacement}{self.state.expression[end:]}"  # 替换回原表达式。
            self.recompute_preview()  # 重算预览。
            self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。
            return  # 完成后结束。

        if self.state.expression.endswith(tuple(INCOMPLETE_END_TOKENS)):  # 如果末尾是不完整 token。
            if len(self.state.expression) < MAX_EXPRESSION_LENGTH:  # 仍未超长。
                self.state.expression += "-"  # 允许继续输入一个负号。
                self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。

    def can_append_decimal(self) -> bool: # 从后往前扫描当前数字段，只在意最后的数字,确保没有重复小数点。
        """同一段数字里只允许一个小数点。"""  # 防止出现 1.2.3。
        expression = self.state.expression  # 当前表达式。
        if not expression:  # 空表达式输入小数点。
            self.state.expression = "0"  # 先补 0，形成 0.
            return True  # 允许继续加点。

        index = len(expression) - 1  # 从末尾开始扫描。
        while index >= 0 and (expression[index].isdigit() or expression[index] == "."):  # 向左找当前数字段起点。
            index -= 1
        segment = expression[index + 1 :]  # 当前数字段（不含运算符）。
        return "." not in segment  # 段内未出现过小数点才允许再加。

    def recompute_preview(self) -> None:
        """新手：尝试计算当前表达式，成功就显示结果，失败就显示友好错误信息。
        进阶：异常被映射为稳定错误码文本，能保证 UI 显示逻辑简单且一致。
        """  # 主计算流程。
        expression = self.state.expression  # 当前表达式。
        if not expression:  # 空表达式。
            self.state.preview = ""  # 预览清空。
            return  # 结束。

        if self.is_expression_incomplete(expression):  # 表达式未完成。
            self.state.preview = ""  # 不显示结果，避免误导。
            return  # 结束。

        try:  # 尝试求值。
            value = self.evaluator.eval(expression)  # 调用 SimpleEval 计算。
            self.state.preview = self.format_result(value)  # 成功后格式化显示。
        except ZeroDivisionError:  # 除零。
            self.state.preview = ERROR_DIV_ZERO
        except OverflowError:  # 溢出。
            self.state.preview = ERROR_OVERFLOW
        except ValueError:  # 定义域等值错误。
            self.state.preview = ERROR_DOMAIN
        except (SyntaxError, TypeError):  # 语法或类型错误。
            self.state.preview = ERROR_SYNTAX
        except Exception:  # 兜底异常。
            LOGGER.exception("Unexpected evaluation error for expression: %s", expression)  # 打日志方便排查。
            self.state.preview = ERROR_GENERIC  # 给用户通用错误提示。

    @staticmethod # 把下面的方法声明为静态方法，因为它不依赖于实例状态。
    def is_expression_incomplete(expression: str) -> bool:
        """判断表达式是否“还没输入完”（例如以运算符结尾或括号未闭合）。"""  # 不完整则不计算。
        if not expression:  # 空串。
            return True

        if expression.endswith(tuple(INCOMPLETE_END_TOKENS)):  # 以 + - * / ( 结尾。
            return True

        return expression.count("(") > expression.count(")")  # 左括号多于右括号也算未完成。

    def commit_result(self) -> None:
        """按下等号后提交预览结果，并写入历史。"""  # = 键主流程。
        if not self.state.preview or self.state.preview in ERROR_MESSAGES:  # 无预览或预览是错误。
            return  # 不提交。

        self.push_history(self.state.expression, self.state.preview)  # 把本次计算写入历史。
        self.state.last_result = self.state.preview  # 记录最后结果。
        self.state.expression = self.state.last_result  # 把结果回填到主表达式，便于继续算。
        self.state.preview = ""  # 清空预览区。
        self.refresh_displays()  # 刷新显示。

    def push_history(self, expression: str, result: str) -> None:
        """插入历史记录（新记录在最前），并限制总条数。"""  # 历史管理。
        if not expression or not result:  # 空数据不入历史。
            return

        item = (expression, result)  # 组装历史项。
        if self.state.history and self.state.history[0] == item:  # 若与上一条完全相同。
            return  # 去重：不重复插入。

        self.state.history.insert(0, item)  # 新记录插入最前。
        self.state.history = self.state.history[:HISTORY_LIMIT]  # 截断到最大条数。
        self.refresh_history_list()  # 刷新历史 UI。

    def refresh_history_list(self) -> None:
        """根据 state.history 重新渲染历史列表。"""  # 每次历史变化都重建列表行。
        for row in self.history_list.get_children():  # 先拿到现有行。  这个get_children()是GTK的方法,位于556行
            self.history_list.remove(row)  # 全部移除。

        for expression, result in self.state.history:  # 遍历历史数据。
            label = Gtk.Label(label=f"{expression} = {result}")  # 文本标签。
            label.set_xalign(0.0)  # 左对齐。
            label.set_ellipsize(ELLIPSIZE_MODE)  # 太长省略。

            button = Gtk.Button()  # 用按钮包裹标签，便于点击回填表达式。
            button.add(label)  # 标签放进按钮。
            button.set_relief(Gtk.ReliefStyle.NONE)  # 去掉按钮边框。
            button.get_style_context().add_class("history-button")  # 添加历史按钮样式类。
            button.connect("clicked", self.on_history_item_clicked, expression)  # 点击时把表达式传给回调。

            row = Gtk.ListBoxRow()  # 新建列表行。
            row.add(button)  # 按钮放入行。
            self.history_list.add(row)  # 行加入列表。

        self.history_list.show_all()  # 显示所有新行。

    def on_history_item_clicked(self, _button: Gtk.Button, expression: str) -> None:
        """点击历史项后把表达式放回主屏，方便继续计算。"""  # 历史回填功能。
        self.state.expression = expression  # 回填表达式。
        self.recompute_preview()  # 重新计算预览。
        self.refresh_displays(show_zero_when_empty=False)  # 刷新显示。

    def refresh_displays(self, show_zero_when_empty: bool = True) -> None:
        """刷新主显示区与预览区文本。"""  # 显示层统一出口。
        if self.state.expression:  # 如果表达式非空。
            expression_text = self.state.expression  # 主屏显示表达式。
        else:  # 表达式为空。
            expression_text = "0" if show_zero_when_empty else ""  # 根据参数决定显示 0 还是空。
        self.main_display.set_text(expression_text)  # 更新主显示。
        self.preview_display.set_text(self.state.preview)  # 更新预览显示。

    def on_key_press(self, _widget: Gtk.Window, event: Gdk.EventKey) -> bool:
        """新手：把键盘按键转换成和按钮点击一样的行为（回车、数字、小键盘等）。
        进阶：通过统一走 append_token/commit_result,确保键盘与鼠标逻辑完全一致。
        """  # 键盘输入入口。
        name = Gdk.keyval_name(event.keyval) or ""  # 获取按键名（如 KP_1、Return）。
        char = event.string or ""  # 获取字符输入（如 1、+）。
        is_shift_pressed = bool(event.state & Gdk.ModifierType.SHIFT_MASK)  # 是否按住 Shift。

        if name in {"Return", "KP_Enter"}:  # 回车键。
            self.commit_result()  # 等同点击等号。
            return True  # 告诉 GTK：事件已处理。
        if name == "BackSpace":  # 退格键。
            self.backspace()  # 执行回删。
            return True
        if name == "Escape":  # Esc 键。
            self.clear_all()  # 清空。
            return True

        keypad_map = {  # 小键盘按键名到 token 的映射。
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

        if name in keypad_map:  # 命中小键盘映射。
            self.append_token(keypad_map[name])  # 复用统一输入逻辑。
            return True

        if name == "plus":  # 主键盘 +（部分布局可能只给 key name）。
            self.append_token("+")
            return True
        if name == "minus":  # 主键盘 -。
            self.append_token("-")
            return True
        if name == "equal" and is_shift_pressed:  # 英文键盘 Shift+= 通常表示 +。
            self.append_token("+")
            return True

        if char in "0123456789.+-*/()%":  # 普通可输入字符。
            if char == "%":  # 百分号特殊处理。
                self.apply_percent_last_number()  # 作用于最后数字。
                return True
            self.append_token(char)  # 其他字符直接走追加。
            return True

        if char == "^":  # 幂运算符。
            self.append_token("**")  # 转成 **。
            return True

        return False  # 未处理按键，交给 GTK 默认流程。

    @staticmethod
    def format_result(value: object) -> str:
        """格式化结果文本：浮点数保留有效数字，其他类型转字符串。"""  # 统一展示格式。
        if isinstance(value, float):  # 浮点数。
            return f"{value:.10g}"  # 保留 10 位有效数字。
        return str(value)  # 非浮点直接转字符串。

    def run(self) -> None:
        """显示窗口并启动 GTK 事件循环。"""  # 应用真正开始运行的地方。
        self.window.show_all()  # 显示窗口及所有子控件。
        Gtk.main()  # 启动 GTK 消息循环（阻塞直到窗口关闭）。


def main() -> None:
    app = CalculatorApp()  # 创建应用实例。
    app.run()  # 运行应用。


if __name__ == "__main__":  # 仅当作为脚本直接运行时执行。
    main()  # 调用入口函数。
