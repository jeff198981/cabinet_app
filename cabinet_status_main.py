from __future__ import annotations

import configparser
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

from config import config_path, load_sqlserver_config
from db_cabinet import CabinetDB, DoorStatus
from logger_utils import get_logger, setup_logging


log = get_logger(__name__)


class FlowLayout(QtWidgets.QLayout):
    """Left-to-right flow layout with wrapping.

    Used to place shoe-cabinet groups horizontally instead of a vertical list.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, margin: int = 0, spacing: int = -1):
        super().__init__(parent)
        self._items: List[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item: QtWidgets.QLayoutItem):
        self._items.append(item)

    def addWidget(self, w: QtWidgets.QWidget):  # type: ignore[override]
        self.addItem(QtWidgets.QWidgetItem(w))

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientations:
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QtCore.QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0

        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())

        space_x = self.spacing()
        if space_x < 0:
            space_x = self.smartSpacing(QtWidgets.QStyle.PM_LayoutHorizontalSpacing)
        space_y = self.spacing()
        if space_y < 0:
            space_y = self.smartSpacing(QtWidgets.QStyle.PM_LayoutVerticalSpacing)

        x = effective.x()
        y = effective.y()
        right = effective.right()

        for item in self._items:
            w = item.widget()
            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > right and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return (y + line_height + m.bottom()) - rect.y()

    def smartSpacing(self, pm: QtWidgets.QStyle.PixelMetric) -> int:
        parent = self.parent()
        if parent is None:
            return 6
        if isinstance(parent, QtWidgets.QWidget):
            return parent.style().pixelMetric(pm, None, parent)
        return 6


@dataclass
class CabinetItem:
    cabinet_type: str  # 'cupboard'
    key: str
    name: str


def _parse_int_list(val: str) -> List[str]:
    parts = [p.strip() for p in (val or '').replace('，', ',').split(',')]
    return [p for p in parts if p]


def load_disshoe_device_groups() -> Tuple[List[str], List[str]]:
    """Backward-compatible config, now optional.

    New logic prefers classifying DisShoeGoods by OperRoom.dbo.Device.Name (男发鞋柜/女发鞋柜),
    so config is not required.
    """
    path = config_path()
    cp = configparser.ConfigParser()
    # tolerate non-utf8 ini written by external tools
    read_ok = False
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            with open(path, 'r', encoding=enc) as f:
                cp.read_file(f)
            read_ok = True
            break
        except UnicodeDecodeError:
            continue
    if not read_ok:
        with open(path, 'rb') as f:
            data = f.read().decode('utf-8', errors='replace')
        cp.read_string(data)
    if 'disshoe' not in cp:
        return [], []
    sec = cp['disshoe']
    return _parse_int_list(sec.get('male_device_ids', '')), _parse_int_list(sec.get('female_device_ids', ''))


def ensure_slipper_icon(asset_dir: str) -> QtGui.QIcon:
    """Ensure a slipper image exists and return it as QIcon."""
    os.makedirs(asset_dir, exist_ok=True)
    # Use a clear "pair of slippers" icon so it's obvious at a glance.
    png_path = os.path.join(asset_dir, 'slippers.png')
    if os.path.exists(png_path):
        return QtGui.QIcon(png_path)
    # (No external downloads, safe for offline deployment.)
    try:
        from PIL import Image, ImageDraw, ImageFilter

        W, H = 256, 256
        im = Image.new('RGBA', (W, H), (255, 255, 255, 0))
        d = ImageDraw.Draw(im)

        # soft shadow
        shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse((54, 150, 220, 232), fill=(0, 0, 0, 90))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        im.alpha_composite(shadow)

        # Draw a single slipper with clear silhouette (no external assets required)
        sole = (230, 230, 230, 255)
        sole2 = (140, 140, 140, 255)
        upper = (70, 135, 220, 255)
        upper2 = (40, 90, 170, 255)

        # sole
        d.rounded_rectangle([40, 96, 216, 228], radius=36, fill=sole, outline=sole2, width=6)
        # upper strap (thick)
        d.rounded_rectangle([64, 120, 208, 182], radius=26, fill=upper, outline=upper2, width=6)
        # toe cut to suggest slipper opening
        d.ellipse((54, 112, 108, 154), fill=(255, 255, 255, 120))

        im.save(png_path)
    except Exception:
        return QtGui.QIcon()
    return QtGui.QIcon(png_path)


def ensure_cycle_icon(asset_dir: str) -> QtGui.QIcon:
    """Ensure a green cycle icon exists and return it as QIcon."""
    os.makedirs(asset_dir, exist_ok=True)
    png_path = os.path.join(asset_dir, 'cycle.png')
    if os.path.exists(png_path):
        return QtGui.QIcon(png_path)
    try:
        size = 128
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor('#148B3A'))
        pen.setWidth(10)
        p.setPen(pen)
        rect = QtCore.QRect(16, 16, size - 32, size - 32)
        p.drawArc(rect, 40 * 16, 280 * 16)
        # arrow head
        p.setBrush(QtGui.QColor('#148B3A'))
        arrow = QtGui.QPolygon([
            QtCore.QPoint(size - 30, 42),
            QtCore.QPoint(size - 10, 40),
            QtCore.QPoint(size - 22, 60),
        ])
        p.drawPolygon(arrow)
        p.end()
        pm.save(png_path)
    except Exception:
        return QtGui.QIcon()
    return QtGui.QIcon(png_path)


def ensure_pin_icon(asset_dir: str) -> QtGui.QIcon:
    """Ensure a pin icon exists and return it as QIcon."""
    os.makedirs(asset_dir, exist_ok=True)
    png_path = os.path.join(asset_dir, 'pin.png')
    if os.path.exists(png_path):
        return QtGui.QIcon(png_path)
    try:
        size = 128
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        # pin head
        p.setBrush(QtGui.QColor('#D32F2F'))
        p.setPen(QtGui.QPen(QtGui.QColor('#8E0000'), 2))
        p.drawEllipse(QtCore.QPoint(64, 36), 20, 20)
        # pin body
        p.setPen(QtGui.QPen(QtGui.QColor('#8E0000'), 6))
        p.drawLine(64, 54, 64, 100)
        # pin tip
        p.setBrush(QtGui.QColor('#8E0000'))
        p.drawPolygon(QtGui.QPolygon([
            QtCore.QPoint(58, 100),
            QtCore.QPoint(70, 100),
            QtCore.QPoint(64, 118),
        ]))
        p.end()
        pm.save(png_path)
    except Exception:
        return QtGui.QIcon()
    return QtGui.QIcon(png_path)


def ensure_shirt_icon(asset_dir: str) -> QtGui.QIcon:
    """Ensure a shirt icon exists and return it as QIcon."""
    os.makedirs(asset_dir, exist_ok=True)
    png_path = os.path.join(asset_dir, 'shirt.png')
    if os.path.exists(png_path):
        return QtGui.QIcon(png_path)
    try:
        from PIL import Image, ImageDraw

        W, H = 256, 256
        im = Image.new('RGBA', (W, H), (255, 255, 255, 0))
        d = ImageDraw.Draw(im)
        body = (80, 140, 220, 255)
        edge = (50, 100, 180, 255)

        # sleeves and body
        d.polygon([(40, 60), (90, 60), (120, 90), (136, 90), (166, 60), (216, 60),
                   (240, 120), (210, 150), (190, 120), (190, 220), (66, 220), (66, 120),
                   (46, 150), (16, 120)], fill=body, outline=edge)
        # collar
        d.polygon([(110, 60), (128, 84), (146, 60)], fill=(240, 240, 240, 255), outline=edge)

        im.save(png_path)
    except Exception:
        return QtGui.QIcon()
    return QtGui.QIcon(png_path)


class CupboardDoorButton(QtWidgets.QPushButton):
    """Door button for Cupboard/Box."""

    def __init__(self, door: DoorStatus, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.door: DoorStatus = door
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumSize(110, 56)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setCheckable(True)

    def set_door(self, door: DoorStatus):
        self.door = door
        self.overlay_icon = None
        self.overlay_text = None
        self.label_text = None

    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            icon = getattr(self, 'overlay_icon', None)
            text = getattr(self, 'overlay_text', None)
            label = getattr(self, 'label_text', None)
            if (icon is None or icon.isNull()) and not text and not label:
                return
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if label:
                font = p.font()
                font.setPointSize(max(8, int(font.pointSize() * 0.9)))
                p.setFont(font)
                p.setPen(QtGui.QColor('#333'))
                p.drawText(QtCore.QRect(6, 4, self.width() - 12, 16),
                           QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, str(label))
            if icon is not None and not icon.isNull():
                size = max(14, int(min(self.width(), self.height()) * 0.22))
                pm = icon.pixmap(size, size)
                x = self.width() - size - 6
                y = 4
                p.drawPixmap(x, y, pm)
            if text:
                base_font = p.font()
                base_font.setPointSize(max(8, int(base_font.pointSize() * 0.9)))
                p.setPen(QtGui.QColor('#333'))
                text_str = str(text)
                avail_w = max(10, self.width() - 12)
                font = QtGui.QFont(base_font)
                metrics = QtGui.QFontMetrics(font)
                # shrink font if needed to fit
                while metrics.horizontalAdvance(text_str) > avail_w and font.pointSize() > 6:
                    font.setPointSize(font.pointSize() - 1)
                    metrics = QtGui.QFontMetrics(font)
                p.setFont(font)
                align = QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom
                if metrics.horizontalAdvance(text_str) > avail_w:
                    align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom
                p.drawText(QtCore.QRect(6, 0, self.width() - 12, self.height() - 4),
                           align, text_str)
            p.end()
        except Exception:
            pass


class ShoeDoorButton(QtWidgets.QToolButton):
    """Door button for DisShoeGoods: icon + text."""

    doubleClicked = QtCore.pyqtSignal(object)

    def __init__(self, door: DoorStatus, slipper_icon: QtGui.QIcon, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.door: DoorStatus = door
        self.slipper_icon = slipper_icon
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        # let the layout stretch buttons; only keep a small minimum
        self.setMinimumSize(32, 32)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setIconSize(QtCore.QSize(22, 22))
        self.setAutoRaise(False)
        self.setCheckable(False)

    def set_door(self, door: DoorStatus):
        self.door = door
        self.overlay_icon = None
        self.overlay_text = None
        self.label_text = None

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        self.doubleClicked.emit(self)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            icon = getattr(self, 'overlay_icon', None)
            text = getattr(self, 'overlay_text', None)
            label = getattr(self, 'label_text', None)
            if (icon is None or icon.isNull()) and not text and not label:
                return
            size = max(14, int(min(self.width(), self.height()) * 0.25))
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if label:
                font = p.font()
                font.setPointSize(max(7, int(font.pointSize() * 0.85)))
                p.setFont(font)
                p.setPen(QtGui.QColor('#333'))
                p.drawText(QtCore.QRect(6, 4, self.width() - 12, 16),
                           QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, str(label))
            if icon is not None and not icon.isNull():
                pm = icon.pixmap(size, size)
                x = self.width() - size - 6
                y = 4
                p.drawPixmap(x, y, pm)
            if text:
                font = p.font()
                font.setPointSize(max(7, int(font.pointSize() * 0.8)))
                p.setFont(font)
                metrics = QtGui.QFontMetrics(font)
                max_w = max(10, self.width() - 10)
                elided = metrics.elidedText(str(text), QtCore.Qt.ElideRight, max_w)
                p.setPen(QtGui.QColor('#333'))
                text_y = size + 6
                p.drawText(QtCore.QRect(6, text_y, self.width() - 12, self.height() - text_y - 4),
                           QtCore.Qt.AlignRight | QtCore.Qt.AlignTop, elided)
            p.end()
        except Exception:
            pass


class CabinetStatusWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._install_exception_hook()
        self.setWindowTitle('柜子状态看板')

        try:
            self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'app_icon.ico')))
        except Exception:
            pass

        cfg = load_sqlserver_config()
        self.db = CabinetDB(cfg.to_odbc_conn_str())

        # cupboard state
        self.current_cabinet: Optional[CabinetItem] = None
        self.cup_buttons: Dict[str, CupboardDoorButton] = {}
        self.selected_door_no: Optional[int] = None

        # disshoe state
        self.disshoe_male_ids, self.disshoe_female_ids = load_disshoe_device_groups()
        self.shoe_icon = ensure_slipper_icon(os.path.join(os.path.dirname(__file__), 'assets'))
        self.cycle_icon = ensure_cycle_icon(os.path.join(os.path.dirname(__file__), 'assets'))
        self.pin_icon = ensure_pin_icon(os.path.join(os.path.dirname(__file__), 'assets'))
        self.shirt_icon = ensure_shirt_icon(os.path.join(os.path.dirname(__file__), 'assets'))
        # 固定拖鞋图标/按钮尺寸：避免定时刷新时因布局抖动导致大小变化
        self.shoe_icon_px = 26
        self.shoe_btn_size = 48
        # shoe grid target: 120 doors = 10 cols x 12 rows
        self.shoe_grid_cols = 10
        self.shoe_grid_rows = 12
        self.shoe_addr_start = 64
        self.shoe_addr_count = 5
        # DeviceId -> Cupboard.No mapping
        self.shoe_device_cupboard_no = {'5': 5, '9': 9}


        # cache shoe buttons to avoid layout jitter on timer refresh
        self.shoe_btns_by_tab: Dict[str, Dict[Tuple[int,int], ShoeDoorButton]] = {}
        self._user_cache: Optional[List[Tuple[str, str, Optional[str]]]] = None
        # timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh_view)

        self._build_ui()
        # default to 发鞋柜
        self.cmb_type.setCurrentIndex(0)
        self._on_type_changed_impl()
        self.on_auto_changed()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        root.addLayout(top)

        self.cmb_type = QtWidgets.QComboBox()
        self.cmb_type.addItem('发鞋柜', userData='disshoegoods')
        self.cmb_type.addItem('更鞋柜', userData='cupboard')
        self.cmb_type.addItem('更衣柜', userData='cupboard')
        self.cmb_type.currentIndexChanged.connect(self.on_type_changed)
        top.addWidget(QtWidgets.QLabel('柜子类型：'))
        top.addWidget(self.cmb_type)

        self.lbl_cabinet = QtWidgets.QLabel('柜子：')
        top.addWidget(self.lbl_cabinet)

        self.cmb_cabinet = QtWidgets.QComboBox()
        self.cmb_cabinet.setMinimumWidth(360)
        self.cmb_cabinet.currentIndexChanged.connect(self.on_cabinet_changed)
        top.addWidget(self.cmb_cabinet, 1)

        self.btn_refresh = QtWidgets.QPushButton('刷新')
        self.btn_refresh.clicked.connect(self.refresh_view)
        top.addWidget(self.btn_refresh)

        self.chk_auto = QtWidgets.QCheckBox('自动刷新')
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(self.on_auto_changed)
        top.addWidget(self.chk_auto)

        self.spin_interval = QtWidgets.QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(3)
        self.spin_interval.setSuffix(' 秒')
        self.spin_interval.valueChanged.connect(self.on_interval_changed)
        top.addWidget(self.spin_interval)

        top.addStretch(1)

        self.stack = QtWidgets.QStackedWidget()
        root.addWidget(self.stack, 1)

        # -------- page: cupboard --------
        self.page_cup = QtWidgets.QWidget()
        cup_root = QtWidgets.QVBoxLayout(self.page_cup)
        cup_root.setContentsMargins(0, 0, 0, 0)
        cup_root.setSpacing(8)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        cup_root.addWidget(splitter, 1)
        self.cup_splitter = splitter

        left = QtWidgets.QWidget()
        l = QtWidgets.QVBoxLayout(left)
        l.setContentsMargins(0, 0, 0, 0)
        self.lbl_hint = QtWidgets.QLabel('请选择柜子')
        self.lbl_hint.setStyleSheet('color: #666;')
        self.lbl_hint.setVisible(False)
        l.addWidget(self.lbl_hint)

        # cupboard tabs (for grouped cupboards)
        self.cup_tabs = QtWidgets.QTabWidget()
        self.cup_tabs.currentChanged.connect(self.on_cup_tab_changed)
        l.addWidget(self.cup_tabs)

        self.scroll_cup = QtWidgets.QScrollArea()
        self.scroll_cup.setWidgetResizable(True)
        l.addWidget(self.scroll_cup, 1)

        self.cup_host = QtWidgets.QWidget()
        self.cup_host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.cup_grid = QtWidgets.QGridLayout(self.cup_host)
        self.cup_grid.setContentsMargins(6, 6, 6, 6)
        self.cup_grid.setSpacing(12)
        self.scroll_cup.setWidget(self.cup_host)

        splitter.addWidget(left)

        # right: details (only for cupboard)
        right = QtWidgets.QWidget()
        self.cup_detail_panel = right
        r = QtWidgets.QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        grp = QtWidgets.QGroupBox('门详情')
        form = QtWidgets.QFormLayout(grp)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self.v_cabinet = QtWidgets.QLabel('-')
        self.v_door = QtWidgets.QLabel('-')
        self.v_status = QtWidgets.QLabel('-')
        self.v_user = QtWidgets.QLabel('-')
        self.v_last = QtWidgets.QLabel('-')
        for w in (self.v_cabinet, self.v_door, self.v_status, self.v_user, self.v_last):
            w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        form.addRow('柜子：', self.v_cabinet)
        form.addRow('门：', self.v_door)
        form.addRow('状态：', self.v_status)
        form.addRow('使用人：', self.v_user)
        form.addRow('更新时间：', self.v_last)
        r.addWidget(grp)
        r.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.stack.addWidget(self.page_cup)

        # -------- page: disshoe (show all on ONE page, no scrollbars, no right detail) --------
        self.page_shoe = QtWidgets.QWidget()
        shoe_root = QtWidgets.QVBoxLayout(self.page_shoe)
        shoe_root.setContentsMargins(0, 0, 0, 0)
        shoe_root.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        shoe_root.addWidget(self.tabs, 1)

        # 男/女发鞋柜
        self.tab_names = ['男发鞋柜', '女发鞋柜']
        self.tab_hosts: Dict[str, QtWidgets.QWidget] = {}
        # NOTE: Do NOT use a custom FlowLayout here.
        # On some Windows machines, custom layouts may lead to hard crashes (Qt native assertions).
        # We use a plain QGridLayout and compute the best cabinet grid (cols/rows) + door tile size
        # to keep everything on ONE page without scrollbars.
        self.tab_layouts: Dict[str, QtWidgets.QLayout] = {}
        self.tab_grid_layouts: Dict[str, QtWidgets.QGridLayout] = {}
        for name in self.tab_names:
            # IMPORTANT: Do NOT use QScrollArea here.
            # User requires "one page" display without scrollbars.
            w = QtWidgets.QWidget()
            vbox = QtWidgets.QVBoxLayout(w)
            vbox.setContentsMargins(6, 6, 6, 6)
            vbox.setSpacing(6)
            vbox.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

            grid_host = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
            vbox.addWidget(grid_host, 1)
            self.tabs.addTab(w, name)
            self.tab_hosts[name] = w
            self.tab_layouts[name] = vbox
            self.tab_grid_layouts[name] = grid

        self.stack.addWidget(self.page_shoe)

        self.statusBar().showMessage('就绪')

    # ---------------- type / cabinet loading ----------------
    def on_type_changed(self):
        return self._safe_call('切换柜子类型失败', lambda: self._on_type_changed_impl())

    def _on_type_changed_impl(self):
        t = self.cmb_type.currentData()
        if t == 'cupboard':
            self.stack.setCurrentWidget(self.page_cup)
            self._setup_cup_tabs()
            # hide right detail panel and let grid fill the page
            if hasattr(self, 'cup_detail_panel'):
                self.cup_detail_panel.hide()
            if hasattr(self, 'cup_splitter'):
                self.cup_splitter.setSizes([1000, 0])
            self.refresh_view()
        else:
            self.stack.setCurrentWidget(self.page_shoe)
            self.lbl_cabinet.hide()
            self.cmb_cabinet.hide()
            # defer refresh until layout is realized to avoid first-paint jitter
            QtCore.QTimer.singleShot(0, self.refresh_view)

    def _load_cupboards(self):
        self.cmb_cabinet.blockSignals(True)
        self.cmb_cabinet.clear()
        try:
            rows = self.db.list_cupboards()
            for cid, name in rows:
                self.cmb_cabinet.addItem(name, userData=CabinetItem('cupboard', cid, name))
            self.statusBar().showMessage(f'加载更衣/更鞋柜：{len(rows)} 个')
        except Exception as e:
            log.exception('Load cupboards failed')
            self._show_error('加载更衣/更鞋柜失败', e)
        finally:
            self.cmb_cabinet.blockSignals(False)

        if self.cmb_cabinet.count() > 0:
            self.cmb_cabinet.setCurrentIndex(0)
            self.on_cabinet_changed()
        else:
            self.current_cabinet = None
            self._clear_cup_grid()
            self._show_cup_detail(None)

    def on_cabinet_changed(self):
        it = self.cmb_cabinet.currentData()
        if not isinstance(it, CabinetItem):
            return
        self.current_cabinet = it
        self.selected_door_no = None
        self.refresh_view()

    # ---------------- refresh ----------------
    def refresh_view(self):
        return self._safe_call('刷新失败', lambda: self._refresh_view_impl())

    def _refresh_view_impl(self):
        t = self.cmb_type.currentData()
        if t == 'cupboard':
            self.refresh_cupboard_group()
        else:
            self.refresh_disshoe_all()

    def _setup_cup_tabs(self):
        # hide cabinet dropdown; use tabs instead
        self.lbl_cabinet.hide()
        self.cmb_cabinet.hide()
        self.cup_tabs.clear()
        self.cup_tab_nos = {}
        t_text = self.cmb_type.currentText()
        if '更鞋柜' in t_text:
            groups = [('男更鞋柜', [1]), ('女更鞋柜', [7])]
        else:
            groups = []
            for no in [2, 3, 5, 11]:
                groups.append((f"{no}号男更衣柜", [no]))
            for no in [8, 9, 10]:
                groups.append((f"{no}号女更衣柜", [no]))
        for name, nos in groups:
            self.cup_tab_nos[name] = nos
            self.cup_tabs.addTab(QtWidgets.QWidget(), name)

    def on_cup_tab_changed(self):
        if self.cmb_type.currentData() == 'cupboard':
            self.refresh_view()
            # re-apply layout after tab switch
            QtCore.QTimer.singleShot(0, lambda: self._apply_cup_grid_stretch(getattr(self, '_cup_last_doors', [])))

    def refresh_cupboard_group(self):
        tab_name = self.cup_tabs.tabText(self.cup_tabs.currentIndex()) if self.cup_tabs.count() > 0 else ''
        self.current_cup_tab = tab_name
        nos = getattr(self, 'cup_tab_nos', {}).get(tab_name, [])
        if not nos:
            self._clear_cup_grid()
            return
        self.cup_host.setUpdatesEnabled(False)
        self.scroll_cup.setUpdatesEnabled(False)
        try:
            doors = self.db.list_doors_by_cupboard_nos(nos)
            self._cup_last_doors = doors
            # always rebuild for grouped cupboards
            self._clear_cup_grid()
            self._render_cup_doors(doors)
            # defer stretch until layout/viewport is ready
            QtCore.QTimer.singleShot(0, lambda d=doors: self._apply_cup_grid_stretch(d))
            QtCore.QTimer.singleShot(50, lambda d=doors: self._apply_cup_grid_stretch(d))
            # re-enable updates after layout settles to avoid flicker
            QtCore.QTimer.singleShot(70, self._resume_cup_updates)
            self.statusBar().showMessage(f'刷新完成：{tab_name}（{len(doors)} 门）')
        except Exception as e:
            log.exception('Refresh cupboard group failed')
            self._show_error('刷新更衣/更鞋柜失败', e)
        finally:
            # updates resumed by timer (see _resume_cup_updates)
            pass

    def _resume_cup_updates(self):
        try:
            self.cup_host.setUpdatesEnabled(True)
            self.scroll_cup.setUpdatesEnabled(True)
            self.cup_host.update()
            self.scroll_cup.viewport().update()
        except Exception:
            pass

    def refresh_cupboard(self):
        if not self.current_cabinet:
            return
        try:
            doors = self.db.list_doors_by_cupboard(self.current_cabinet.key)
            self._render_cup_doors(doors)
            self.statusBar().showMessage(f'刷新完成：{self.current_cabinet.name}（{len(doors)} 门）')
        except Exception as e:
            log.exception('Refresh cupboard failed')
            self._show_error('刷新更衣/更鞋柜失败', e)


    def refresh_disshoe_all(self):
        """Show all shoe doors at once.

        Split into male/female by Device.Name (男发鞋柜/女发鞋柜).
        Inside each tab, further group by physical cabinet address (DeviceId|Address) so the UI matches
        the real locker blocks.
        """
        try:
            doors = self.db.list_disshoe_doors_all()
        except Exception as e:
            log.exception('Refresh disshoe failed')
            self._show_error('刷新发鞋柜失败', e)
            return

        # backfill user names if missing
        missing_ids = [d.user_id for d in doors if d.user_id and not d.user_name]
        if missing_ids:
            try:
                name_map = {uid: uname for uid, uname in self.db.list_user_names_by_ids(missing_ids)}
                for d in doors:
                    if d.user_id and not d.user_name:
                        d.user_name = name_map.get(d.user_id)
            except Exception:
                pass

        male: List[DoorStatus] = []
        female: List[DoorStatus] = []
        for d in doors:
            if str(d.device_id) == '5':
                d.is_cycle = (not d.user_id)
                male.append(d)
            elif str(d.device_id) == '9':
                d.is_cycle = (not d.user_id)
                female.append(d)

        self._render_shoe_tab('男发鞋柜', male)
        self._render_shoe_tab('女发鞋柜', female)
        self.statusBar().showMessage(f'刷新完成：男发鞋柜（{len(male)} 门），女发鞋柜（{len(female)} 门）')

    def _clear_cup_grid(self):
        while self.cup_grid.count():
            item = self.cup_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cup_buttons.clear()

    def _render_cup_doors(self, doors: List[DoorStatus]):
        doors = sorted(doors, key=lambda x: x.door_no)
        if not doors:
            self._clear_cup_grid()
            self.lbl_hint.setText('该柜子没有门数据')
            return

        # clear any previous separator lines
        for line in getattr(self, 'cup_sep_lines', []):
            try:
                line.deleteLater()
            except Exception:
                pass
        self.cup_sep_lines = []

        self.lbl_hint.setText('点击门查看详情')

        existing = set(self.cup_buttons.keys())
        current = set(f"{d.cabinet_key}|{d.door_no}" for d in doors)
        for door_no in list(existing - current):
            btn = self.cup_buttons.pop(door_no, None)
            if btn:
                btn.deleteLater()

        rebuild = (len(existing) == 0) or (len(existing) != len(current))
        if rebuild:
            self._clear_cup_grid()

        def shoe_pos(no: int):
            # 9 rows per column; odd/even pairs by column
            group = (no - 1) // 18
            pos = (no - 1) % 18
            col = group * 2 + (pos % 2)
            row = pos // 2
            return row, col

        def wardrobe_pos(no: int):
            # 2 rows per column; odd/even pairs by column
            group = (no - 1) // 4
            pos = (no - 1) % 4
            col = group * 2 + (pos % 2)
            row = pos // 2
            return row, col

        tab = getattr(self, 'current_cup_tab', '')
        is_male_shoe = tab == '男更鞋柜'
        is_female_shoe = tab == '女更鞋柜'
        is_shoe_tab = tab in ('男更鞋柜', '女更鞋柜')
        is_wardrobe_tab = ('更衣柜' in tab)
        max_no = max([d.door_no for d in doors] or [0])
        rows_per_col = 12
        for idx, d in enumerate(doors):
            key = f"{d.cabinet_key}|{d.door_no}"
            btn = self.cup_buttons.get(key)
            if btn is None:
                btn = CupboardDoorButton(d)
                self.cup_buttons[key] = btn
                btn.clicked.connect(self.on_cup_door_clicked)
            btn.set_door(d)
            if is_shoe_tab:
                btn.setText("")
                btn.label_text = str(d.door_no)
                btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                ending = int(d.ending) if d.ending is not None else 0
                is_fixed = (ending == 1)
                if is_fixed:
                    btn.overlay_icon = self.pin_icon
                    # show fixed user name at bottom-right
                    btn.overlay_text = d.user_name or ''
                    bg = '#FFF4B3'
                else:
                    btn.overlay_icon = self.cycle_icon
                    btn.overlay_text = ''
                    bg = '#CFE7DB'
                # empty vs non-empty by UserId
                    occupied = bool(d.user_id)
                    btn.setIcon(self.shoe_icon if occupied else QtGui.QIcon())
                    btn.setText("" if occupied else "空")
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {bg};
                        border: 1px solid #999;
                        border-radius: 6px;
                        padding: 4px;
                        font-size: 12px;
                    }}
                    QPushButton:checked {{
                        border: 2px solid #1976D2;
                        background-color: {bg};
                    }}
                    """
                )
            else:
                if is_wardrobe_tab:
                    # same fixed/cycle logic as shoe柜
                    btn.setText("")
                    btn.label_text = str(d.door_no)
                    btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                    btn.setMinimumHeight(40)
                    ending = int(d.ending) if d.ending is not None else 0
                    is_fixed = (ending == 1)
                    if is_fixed:
                        btn.overlay_icon = self.pin_icon
                        btn.overlay_text = d.user_name or ''
                        bg = '#FFF4B3'
                    else:
                        btn.overlay_icon = self.cycle_icon
                        btn.overlay_text = ''
                        bg = '#CFE7DB'
                    occupied = bool(d.user_id)
                    if occupied:
                        btn.overlay_text = d.user_name or ''
                    btn.setIcon(self.shirt_icon if occupied else QtGui.QIcon())
                    btn.setText("" if occupied else "空")
                    btn.setStyleSheet(
                        f"""
                        QPushButton {{
                            background-color: {bg};
                            border: 1px solid #999;
                            border-radius: 6px;
                            padding: 4px;
                            font-size: 12px;
                        }}
                        QPushButton:checked {{
                            border: 2px solid #1976D2;
                        }}
                        """
                    )
                else:
                    if d.user_name:
                        btn.setText(f"{d.door_name}\n{d.user_name}")
                    else:
                        btn.setText(f"{d.door_name}\n空")

                    occupied = bool(d.user_name)
                    bg = '#A5D6A7' if occupied else '#EEEEEE'
                    btn.setStyleSheet(
                        f"""
                        QPushButton {{
                            background-color: {bg};
                            border: 1px solid #999;
                            border-radius: 6px;
                            padding: 4px;
                            font-size: 12px;
                        }}
                        QPushButton:checked {{
                            border: 2px solid #1976D2;
                        }}
                        """
                    )

            if rebuild:
                if is_shoe_tab:
                    row, col = shoe_pos(d.door_no)
                    # insert separator columns between each 2 columns
                    data_cols = 10 if is_male_shoe else 12 if is_female_shoe else 10
                    groups = data_cols // 2
                    sep_cols = max(0, groups - 1)
                    total_cols = data_cols + sep_cols
                    grid_col = col + (col // 2)
                    for c in range(total_cols):
                        self.cup_grid.setColumnStretch(c, 1)
                    for r in range(9):
                        self.cup_grid.setRowStretch(r, 1)
                    # add separator lines in dedicated columns
                    if not getattr(self, 'cup_sep_lines', None):
                        for g in range(1, groups):
                            sep_col = g * 3 - 1
                            line = QtWidgets.QFrame()
                            line.setFrameShape(QtWidgets.QFrame.VLine)
                            line.setFrameShadow(QtWidgets.QFrame.Sunken)
                            line.setStyleSheet("QFrame{background:#6d8d9b;}")
                            line.setFixedWidth(2)
                            self.cup_grid.addWidget(line, 0, sep_col, 9, 1)
                            self.cup_grid.setColumnStretch(sep_col, 0)
                            self.cup_sep_lines.append(line)
                elif is_wardrobe_tab:
                    row, col = wardrobe_pos(d.door_no)
                    data_cols = max(1, ((max_no - 1) // 4 + 1) * 2)
                    groups = data_cols // 2
                    sep_cols = max(0, groups - 1)
                    total_cols = data_cols + sep_cols
                    # spacing like 更鞋柜
                    self.cup_grid.setHorizontalSpacing(6)
                    self.cup_grid.setVerticalSpacing(6)
                    for c in range(total_cols):
                        self.cup_grid.setColumnStretch(c, 1)
                    for r in range(2):
                        self.cup_grid.setRowStretch(r, 1)
                    # add separator lines between every two columns
                    if not getattr(self, 'cup_sep_lines', None):
                        for g in range(1, groups):
                            sep_col = g * 3 - 1
                            line = QtWidgets.QFrame()
                            line.setFrameShape(QtWidgets.QFrame.VLine)
                            line.setFrameShadow(QtWidgets.QFrame.Sunken)
                            line.setStyleSheet("QFrame{background:#6d8d9b;}")
                            line.setFixedWidth(2)
                            self.cup_grid.addWidget(line, 0, sep_col, 2, 1)
                            self.cup_grid.setColumnStretch(sep_col, 0)
                            self.cup_sep_lines.append(line)
                else:
                    row = idx % rows_per_col
                    col = idx // rows_per_col
                if is_shoe_tab:
                    self.cup_grid.addWidget(btn, row, grid_col)
                elif is_wardrobe_tab:
                    grid_col = col + (col // 2)
                    self.cup_grid.addWidget(btn, row, grid_col)
                else:
                    self.cup_grid.addWidget(btn, row, col)

        if self.selected_door_no is not None:
            sel_key = self.selected_door_no
            for k, b in self.cup_buttons.items():
                b.setChecked(k == sel_key)
            if sel_key in self.cup_buttons:
                self._show_cup_detail(self.cup_buttons[sel_key].door)
        else:
            self._show_cup_detail(None)

        self.cup_host.adjustSize()
        self.cup_host.update()

    def _apply_cup_grid_stretch(self, doors: List[DoorStatus]):
        tab = getattr(self, 'current_cup_tab', '')
        if ('更衣柜' not in tab) and ('更鞋柜' not in tab):
            return
        # guard against stale timer events from previous tab refresh
        current_doors = getattr(self, '_cup_last_doors', None)
        if current_doors is not None and doors is not current_doors:
            doors = current_doors
        is_shoe_tab = tab in ('男更鞋柜', '女更鞋柜')
        if is_shoe_tab:
            rows = 9
            data_cols = 10 if tab == '男更鞋柜' else 12
            groups = data_cols // 2
            sep_cols = max(0, groups - 1)
            total_cols = data_cols + sep_cols
            # reset stretches (clear old tab constraints)
            for c in range(40):
                self.cup_grid.setColumnStretch(c, 0)
                self.cup_grid.setColumnMinimumWidth(c, 0)
            for r in range(20):
                self.cup_grid.setRowStretch(r, 0)
                self.cup_grid.setRowMinimumHeight(r, 0)

            # spacing like 发鞋柜
            h_spacing = 6
            v_spacing = 6
            self.cup_grid.setHorizontalSpacing(h_spacing)
            self.cup_grid.setVerticalSpacing(v_spacing)

            # compute target cell size to fill viewport
            try:
                vp = self.scroll_cup.viewport().size()
                if vp.width() > 0 and vp.height() > 0:
                    m = self.cup_grid.contentsMargins()
                    sep_w = 2
                    avail_w = max(10, vp.width() - m.left() - m.right()
                                  - h_spacing * (total_cols - 1)
                                  - sep_w * sep_cols)
                    avail_h = max(10, vp.height() - m.top() - m.bottom()
                                  - v_spacing * (rows - 1))
                    cell_w = max(36, int(avail_w / data_cols))
                    cell_h = max(44, int(avail_h / rows))
                    # set minimums so buttons can expand to fill
                    for b in self.cup_buttons.values():
                        b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                        b.setMinimumSize(cell_w, cell_h)
                    for r in range(rows):
                        self.cup_grid.setRowMinimumHeight(r, cell_h)
                        self.cup_grid.setRowStretch(r, 1)
                    for c in range(total_cols):
                        self.cup_grid.setColumnStretch(c, 1)
                    # set min width for data columns only
                    for dc in range(data_cols):
                        actual_col = dc + (dc // 2)
                        self.cup_grid.setColumnMinimumWidth(actual_col, cell_w)
                    # keep separator columns fixed
                    for g in range(1, groups):
                        sep_col = g * 3 - 1
                        self.cup_grid.setColumnStretch(sep_col, 0)
                        self.cup_grid.setColumnMinimumWidth(sep_col, sep_w)
                    # force host to fill viewport (prevents collapse after tab switch)
                    self.cup_host.setMinimumSize(vp)
                    self.cup_host.resize(vp)
            except Exception:
                pass
            self.cup_host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.cup_host.updateGeometry()
            self._resize_cup_icons(is_shoe_tab=True)
            return
        max_no = max([d.door_no for d in doors] or [0])
        data_cols = max(1, ((max_no - 1) // 4 + 1) * 2)
        groups = data_cols // 2
        sep_cols = max(0, groups - 1)
        total_cols = data_cols + sep_cols
        rows = 2
        # spacing like 更鞋柜
        h_spacing = 6
        v_spacing = 6
        self.cup_grid.setHorizontalSpacing(h_spacing)
        self.cup_grid.setVerticalSpacing(v_spacing)
        # reset stretches
        for c in range(40):
            self.cup_grid.setColumnStretch(c, 0)
            self.cup_grid.setColumnMinimumWidth(c, 0)
        for r in range(10):
            self.cup_grid.setRowStretch(r, 0)
            self.cup_grid.setRowMinimumHeight(r, 0)
        # force host to fill viewport + compute cell size
        try:
            vp = self.scroll_cup.viewport().size()
            if vp.width() > 0 and vp.height() > 0:
                m = self.cup_grid.contentsMargins()
                sep_w = 2
                avail_w = max(10, vp.width() - m.left() - m.right()
                              - h_spacing * (total_cols - 1)
                              - sep_w * sep_cols)
                avail_h = max(10, vp.height() - m.top() - m.bottom()
                              - v_spacing * (rows - 1))
                cell_w = max(40, int(avail_w / data_cols))
                cell_h = max(60, int(avail_h / rows))
                for b in self.cup_buttons.values():
                    b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                    b.setMinimumSize(cell_w, cell_h)
                for r in range(rows):
                    self.cup_grid.setRowMinimumHeight(r, cell_h)
                    self.cup_grid.setRowStretch(r, 1)
                for c in range(total_cols):
                    self.cup_grid.setColumnStretch(c, 1)
                # set min width for data columns only
                for dc in range(data_cols):
                    actual_col = dc + (dc // 2)
                    self.cup_grid.setColumnMinimumWidth(actual_col, cell_w)
                # separator columns fixed width
                for g in range(1, groups):
                    sep_col = g * 3 - 1
                    self.cup_grid.setColumnStretch(sep_col, 0)
                    self.cup_grid.setColumnMinimumWidth(sep_col, sep_w)
                self.cup_host.setMinimumSize(vp)
                self.cup_host.resize(vp)
        except Exception:
            pass
        self.cup_host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.cup_host.updateGeometry()
        self._resize_cup_icons(is_shoe_tab=False)

    def _resize_cup_icons(self, is_shoe_tab: bool):
        for b in self.cup_buttons.values():
            if not isinstance(b, CupboardDoorButton):
                continue
            side = max(22, int(min(b.width(), b.height()) * (0.55 if is_shoe_tab else 0.7)))
            b.setIconSize(QtCore.QSize(side, side))

    def on_cup_door_clicked(self):
        btn = self.sender()
        if not isinstance(btn, CupboardDoorButton):
            return
        self.selected_door_no = f"{btn.door.cabinet_key}|{btn.door.door_no}"
        for k, b in self.cup_buttons.items():
            b.setChecked(k == self.selected_door_no)
        self._show_cup_detail(btn.door)

    def _show_cup_detail(self, d: Optional[DoorStatus]):
        if not d:
            self.v_cabinet.setText('-')
            self.v_door.setText('-')
            self.v_status.setText('-')
            self.v_user.setText('-')
            self.v_last.setText('-')
            return

        self.v_cabinet.setText(d.cabinet_name)
        self.v_door.setText(d.door_name)
        self.v_user.setText(d.user_name or '—')
        self.v_last.setText(d.last_update_time or '—')
        self.v_status.setText('占用' if d.user_name else '空')


    def _safe_call(self, title: str, fn):
        try:
            return fn()
        except Exception as e:
            log.exception(title)
            try:
                self._show_error(title, e)
            except Exception:
                pass
            return None

    def _install_exception_hook(self):
        # Catch uncaught exceptions and show them instead of silently exiting
        def _hook(exc_type, exc, tb):
            try:
                log.error('Unhandled exception', exc_info=(exc_type, exc, tb))
            except Exception:
                pass
            try:
                import traceback as _tb
                # Keep this as a single string literal (avoid accidental newlines in source)
                msg = f"{exc_type.__name__}: {exc}\n\n" + ''.join(_tb.format_tb(tb))
                QtWidgets.QMessageBox.critical(None, 'Unhandled exception', msg)
            except Exception:
                pass
        sys.excepthook = _hook

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.stack.currentWidget() == self.page_shoe:
            self._resize_shoe_buttons(self.tabs.tabText(self.tabs.currentIndex()))
        elif self.stack.currentWidget() == self.page_cup:
            QtCore.QTimer.singleShot(0, lambda: self._apply_cup_grid_stretch(getattr(self, '_cup_last_doors', [])))

    def showEvent(self, event):
        super().showEvent(event)
        # ensure first paint uses correct sizes after layout is shown
        QtCore.QTimer.singleShot(0, lambda: self._resize_shoe_buttons(self.tabs.tabText(self.tabs.currentIndex())))

    # ---------------- shoe rendering ----------------
    def _clear_layout_widgets(self, layout: QtWidgets.QLayout):
        # remove all widgets/items
        while layout.count() > 0:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                # spacer item
                pass


    
    def _render_shoe_tab(self, tab_name: str, doors: List[DoorStatus]):
        """Render shoe doors on one page (male cabinet = 120 doors)."""

        grid = self.tab_grid_layouts[tab_name]
        btn_cache = self.shoe_btns_by_tab.setdefault(tab_name, {})

        # group by address (cabinet_key = DeviceId|Address)
        by_addr: Dict[int, List[DoorStatus]] = {}
        for d in doors or []:
            try:
                parts = (d.cabinet_key or '').split('|', 1)
                addr = int(parts[1]) if len(parts) > 1 else None
            except Exception:
                addr = None
            if addr is None:
                continue
            by_addr.setdefault(addr, []).append(d)

        # male cabinet fixed addresses
        if tab_name == '男发鞋柜':
            addrs = list(range(self.shoe_addr_start, self.shoe_addr_start + self.shoe_addr_count))
        elif tab_name == '女发鞋柜':
            addrs = list(range(self.shoe_addr_start, self.shoe_addr_start + 4))
        else:
            addrs = sorted(by_addr.keys())

        # layout: each address is 2 columns x 12 rows, arranged horizontally
        # plus separator columns between groups
        sep_cols = max(0, len(addrs) - 1)
        grid_cols = max(2, len(addrs) * 2 + sep_cols)
        grid_rows = 12
        # build once to avoid jitter
        if not btn_cache:
            while grid.count():
                it = grid.takeAt(0)
                w = it.widget()
                if w:
                    w.deleteLater()

            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            # stretch evenly to fill available area (separator columns do not stretch)
            for c in range(grid_cols):
                grid.setColumnStretch(c, 1)
            for r in range(grid_rows):
                grid.setRowStretch(r, 1)

            for ai, addr in enumerate(addrs):
                base_col = ai * 2 + ai  # add separator column before each group except first
                for no in range(1, 25):
                    r = (no - 1) // 2
                    c = base_col + ((no - 1) % 2)
                    placeholder = DoorStatus(
                        cabinet_type='disshoegoods',
                        cabinet_key=f"0|{addr}",
                        cabinet_name=f"{addr}",
                        door_no=no,
                        door_name=f"{addr}-{no:02d}",
                        user_id=None,
                        user_name=None,
                        lock_state=None,
                        lock_name=None,
                        size_name=None,
                        style_name=None,
                        device_name=None,
                        is_cycle=True,
                        amount=0,
                    )
                    btn = ShoeDoorButton(placeholder, self.shoe_icon)
                    btn.doubleClicked.connect(self.on_shoe_door_double_clicked)
                    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
                    grid.addWidget(btn, r, c)
                    btn_cache[(addr, no)] = btn

                # add vertical separator line after this group (except last)
                if ai < len(addrs) - 1:
                    sep_col = base_col + 2
                    line = QtWidgets.QFrame()
                    line.setFrameShape(QtWidgets.QFrame.VLine)
                    line.setFrameShadow(QtWidgets.QFrame.Sunken)
                    line.setStyleSheet("QFrame{background:#6d8d9b;}")
                    line.setFixedWidth(3)
                    grid.addWidget(line, 0, sep_col, grid_rows, 1)
                    grid.setColumnStretch(sep_col, 0)

        host = grid.parentWidget()
        if host:
            host.setUpdatesEnabled(False)

        try:
            for addr in addrs:
                door_map: Dict[int, DoorStatus] = {int(d.door_no): d for d in by_addr.get(addr, []) if d.door_no}
                for no in range(1, 25):
                    d = door_map.get(no)
                    if d is None:
                        d = DoorStatus(
                            cabinet_type='disshoegoods',
                            cabinet_key=f"0|{addr}",
                            cabinet_name=f"{addr}",
                            door_no=no,
                            door_name=f"{addr}-{no:02d}",
                            user_id=None,
                            user_name=None,
                            lock_state=None,
                            lock_name=None,
                            size_name=None,
                            style_name=None,
                            device_name=None,
                            is_cycle=True,
                            amount=0,
                        )
                    btn = btn_cache[(addr, no)]
                    btn.set_door(d)
                    if not btn.receivers(btn.doubleClicked):
                        btn.doubleClicked.connect(self.on_shoe_door_double_clicked)

                    occupied = bool(getattr(d, 'amount', 0) and getattr(d, 'amount', 0) > 0)

                    label = f"{addr}-{no:02d}"
                    if d.lock_state == 20:
                        btn.setText("")
                        btn.setIcon(QtGui.QIcon())
                        btn.overlay_icon = None
                        btn.overlay_text = None
                        btn.label_text = label
                    elif d.is_cycle:
                        btn.setText("空" if not occupied else "")
                        btn.setIcon(self.shoe_icon if occupied else QtGui.QIcon())
                        btn.overlay_icon = self.cycle_icon
                        btn.overlay_text = None
                        btn.label_text = label
                    else:
                        name = d.user_name or ''
                        btn.setText("" if occupied else "空")
                        btn.setIcon(self.shoe_icon if occupied else QtGui.QIcon())
                        btn.overlay_icon = self.pin_icon
                        btn.overlay_text = name
                        btn.label_text = label

                    self._apply_shoe_button_style(btn, d)
        finally:
            if host:
                host.setUpdatesEnabled(True)
            # ensure resize happens after layout pass
            QtCore.QTimer.singleShot(0, lambda: self._resize_shoe_buttons(tab_name))

    def on_shoe_door_double_clicked(self, btn):
        if not isinstance(btn, ShoeDoorButton):
            return
        # only allow edit on 女发鞋柜 (DeviceId=9)
        if self.tabs.tabText(self.tabs.currentIndex()) != '女发鞋柜':
            return
        d = btn.door
        if str(getattr(d, 'device_id', '')) != '9':
            return
        if d.address is None or d.door_no is None:
            return
        choice = self._pick_user_for_female_shoe()
        if choice is None:
            return
        try:
            if choice == '__CYCLE__':
                self.db.update_disshoe_user(str(d.device_id), int(d.address), int(d.door_no), None)
            else:
                self.db.update_disshoe_user(str(d.device_id), int(d.address), int(d.door_no), choice)
            self.refresh_view()
        except Exception as e:
            log.exception('Update disshoe user failed')
            self._show_error('更新女发鞋柜用户失败', e)

    def _pick_user_for_female_shoe(self) -> Optional[str]:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('设置女发鞋柜为固定/循环')
        dlg.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        dlg.setModal(True)
        dlg.resize(420, 520)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search = QtWidgets.QLineEdit()
        search.setPlaceholderText('搜索姓名...')
        layout.addWidget(search)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['LoginName', '姓名'])
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        layout.addWidget(table, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_cycle = QtWidgets.QPushButton('设为循环柜')
        btn_ok = QtWidgets.QPushButton('确定')
        btn_cancel = QtWidgets.QPushButton('取消')
        btn_row.addWidget(btn_cycle)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if self._user_cache is None:
            try:
                # female users only (sex=0) for 女发鞋柜
                self._user_cache = self.db.list_users_by_sex(0)
            except Exception:
                self._user_cache = []

        def refill(filter_text: str):
            table.setRowCount(0)
            ft = (filter_text or '').strip()
            for uid, name, login in (self._user_cache or []):
                if ft and (ft not in name) and (login is None or ft not in login):
                    continue
                r = table.rowCount()
                table.insertRow(r)
                item_login = QtWidgets.QTableWidgetItem(login or '')
                item_name = QtWidgets.QTableWidgetItem(name)
                item_login.setData(QtCore.Qt.UserRole, uid)
                item_name.setData(QtCore.Qt.UserRole, uid)
                table.setItem(r, 0, item_login)
                table.setItem(r, 1, item_name)

        refill('')
        search.textChanged.connect(refill)

        result: Dict[str, Optional[str]] = {'val': None}

        def accept_selected():
            row = table.currentRow()
            if row < 0:
                return
            item = table.item(row, 0) or table.item(row, 1)
            if item is None:
                return
            result['val'] = item.data(QtCore.Qt.UserRole)
            dlg.accept()

        btn_ok.clicked.connect(accept_selected)
        btn_cancel.clicked.connect(dlg.reject)
        btn_cycle.clicked.connect(lambda: (result.__setitem__('val', '__CYCLE__'), dlg.accept()))
        table.itemDoubleClicked.connect(lambda *_: accept_selected())

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            return result['val']
        return None

    def _resize_shoe_buttons(self, tab_name: str):
        grid = self.tab_grid_layouts.get(tab_name)
        if not grid:
            return
        for i in range(grid.count()):
            w = grid.itemAt(i).widget()
            if isinstance(w, ShoeDoorButton):
                size = w.size()
                side = max(28, min(size.width(), size.height()))
                icon_px = max(24, int(side * 0.8))
                w.setIconSize(QtCore.QSize(icon_px, icon_px))


    def _build_shoe_cabinet_widget(self, cabinet_key: str, doors: List[DoorStatus], target_w: int, target_h: int) -> QtWidgets.QWidget:
        """Build a widget for one physical shoe cabinet (DeviceId|Address).

        We try to mimic the real cabinet layout:
        - 24-door shoe cabinet: 2 rows x 12 columns, numbering pattern matches the physical sticker numbers.
        - Colors: locked=gray, empty=yellow, occupied=green (with slippers icon).
        """
        # Parse address for a simple title like the real controller screen number.
        addr = None
        dev = None
        try:
            parts = (cabinet_key or '').split('|', 1)
            dev = parts[0] if len(parts) > 0 else None
            addr = parts[1] if len(parts) > 1 else None
        except Exception:
            pass

        title = f"{addr}" if addr is not None else cabinet_key

        # Use a lightweight frame + label instead of QGroupBox (saves vertical space).
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setStyleSheet('QFrame{border:1px solid #cfcfcf; border-radius:6px; background:#ffffff;}')
        frame.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        # Fix the size so the outer grid can compute a stable layout (no scrollbars).
        try:
            frame.setFixedSize(int(target_w), int(target_h))
        except Exception:
            pass
        v = QtWidgets.QVBoxLayout(frame)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        lbl = QtWidgets.QLabel(str(title))
        lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        lbl.setStyleSheet('font-weight:600; color:#333;')
        v.addWidget(lbl)

        grid_host = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_host)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        v.addWidget(grid_host)

        # Decide layout style.
        n = len(doors)
        max_no = max([d.door_no for d in doors] or [0])
        # 24-door (2 rows) layout matches the physical cabinet photos:
        # Top row: 1,2,5,6,9,10,...  Bottom row: 3,4,7,8,11,12,...
        use_2row_24 = (n >= 20 and max_no <= 24)
        if use_2row_24:
            rows = 2
            cols = 12
            # compute tile size from both target width and height so it fits on one page
            avail_grid_w = max(200, target_w - 12)
            avail_grid_h = max(120, target_h - 32)  # minus label/spacing
            btn_w_by_w = int((avail_grid_w - 6 * (cols - 1)) / cols)
            btn_h_by_h = int((avail_grid_h - 6 * (rows - 1)) / rows)
            btn_w = max(30, min(btn_w_by_w, int(btn_h_by_h * 1.15)))
            btn_h = max(32, int(btn_w * 0.95))

            def pos_for(no: int):
                base = no - 1
                g = base // 4
                within = base % 4
                c = g * 2 + (within // 2)
                r = 0 if within < 2 else 1
                return r, c

            icon_px = self.shoe_icon_px
            for d in doors:
                r, c = pos_for(d.door_no)
                if c >= cols or r >= rows:
                    continue
                btn = ShoeDoorButton(d, self.shoe_icon)
                btn.setFixedSize(btn_w, btn_h)
                btn.setIconSize(QtCore.QSize(icon_px, icon_px))
                self._apply_shoe_button_style(btn, d)
                grid.addWidget(btn, r, c)
        else:
            # Fallback: compact grid by BoxNo
            # Determine columns by target width
            cols = max(6, min(20, target_w // 64))
            rows = (n + cols - 1) // cols
            avail_grid_w = max(200, target_w - 12)
            avail_grid_h = max(120, target_h - 32)
            btn_w_by_w = int((avail_grid_w - 6 * (cols - 1)) / cols)
            btn_h_by_h = int((avail_grid_h - 6 * (rows - 1)) / rows)
            btn_w = max(30, min(btn_w_by_w, int(btn_h_by_h * 1.2)))
            btn_h = max(30, int(btn_w * 0.9))
            icon_px = self.shoe_icon_px
            for idx, d in enumerate(sorted(doors, key=lambda x: x.door_no)):
                r = idx // cols
                c = idx % cols
                btn = ShoeDoorButton(d, self.shoe_icon)
                btn.setFixedSize(btn_w, btn_h)
                btn.setIconSize(QtCore.QSize(icon_px, icon_px))
                self._apply_shoe_button_style(btn, d)
                grid.addWidget(btn, r, c)

        frame.adjustSize()
        # lock to target so FlowLayout can pack tightly
        frame.setFixedSize(min(target_w, frame.sizeHint().width() + 4), min(target_h, frame.sizeHint().height() + 4))
        return frame

    def _calc_best_grid(self, n: int, avail_w: int, avail_h: int):
        """Choose (cols, rows, btn_w, btn_h) so all items fit without scrollbars."""
        if n <= 0:
            return 1, 1, 80, 70

        margin = 12
        h_space = 6
        v_space = 6
        # Allow smaller buttons to guarantee "one page" without scrollbars.
        min_w = 46
        min_h = 42

        best = None  # (score, cols, rows, btn_w, btn_h)
        for cols in range(6, 31):
            rows = (n + cols - 1) // cols
            btn_w = int((avail_w - margin * 2 - h_space * (cols - 1)) / cols)
            btn_h = int((avail_h - margin * 2 - v_space * (rows - 1)) / rows)
            if btn_w <= 0 or btn_h <= 0:
                continue
            # Must be readable
            if btn_w < min_w or btn_h < min_h:
                continue
            score = min(btn_w, btn_h)
            if best is None or score > best[0]:
                best = (score, cols, rows, btn_w, btn_h)

        if best is None:
            # fallback: force more columns and clamp to a small but usable size
            cols = 14
            rows = (n + cols - 1) // cols
            btn_w = max(48, int((avail_w - margin * 2 - h_space * (cols - 1)) / cols))
            btn_h = max(44, int((avail_h - margin * 2 - v_space * (rows - 1)) / rows))
            return cols, rows, btn_w, btn_h

        _, cols, rows, btn_w, btn_h = best
        return cols, rows, btn_w, btn_h

    def _apply_shoe_button_style(self, btn: 'ShoeDoorButton', d: DoorStatus):
        """只负责样式（颜色/边框/tooltip），不在这里改文本和图标。

        规则：
        - 锁定（DisShoeGoods.State==20）：灰色
        - 空（未占用）：黄色
        - 非空（占用）：绿色 + 显示拖鞋（由调用方决定是否设置 icon）
        """
        # Occupied means amount > 0
        occupied = bool(getattr(d, 'amount', 0) and getattr(d, 'amount', 0) > 0)
        locked = (d.lock_state == 20)

        # Tooltip for extra info（方便鼠标悬停查看）
        tip_parts = [f"门号: {d.door_no}"]
        if d.device_name:
            tip_parts.append(f"设备: {d.device_name}")
        if d.cabinet_key:
            tip_parts.append(f"柜体: {d.cabinet_key}")
        if d.lock_name:
            tip_parts.append(f"锁状态: {d.lock_name}")
        if d.user_name:
            tip_parts.append(f"占用人: {d.user_name}")
        if d.size_name or d.style_name:
            tip_parts.append(f"鞋码: {d.size_name or '—'}")
            tip_parts.append(f"款式: {d.style_name or '—'}")
        btn.setToolTip("\n".join(tip_parts))

        # Colors
        is_cycle = getattr(d, 'is_cycle', None)
        if locked:
            bg = ('#F5F5F5', '#CFCFCF')
            bd = '#8a8a8a'
        elif is_cycle is True:
            bg = ('#CFE7DB', '#8FC8AB')  # deeper misty green for cycle
            bd = '#5F9C80'
        elif is_cycle is False:
            bg = ('#FFF8D6', '#F0E096')  # light yellow for fixed
            bd = '#d6a800'
        elif occupied:
            bg = ('#BFF1C0', '#7DDC82')  # green
            bd = '#3b9b3e'
        else:
            bg = ('#FFF1BF', '#F5D46A')  # yellow
            bd = '#d6a800'

        style = (
            "QToolButton {"
            f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {bg[0]}, stop:1 {bg[1]});"
            f"border:1px solid {bd};"
            "border-top:1px solid rgba(255,255,255,0.9);"
            "border-bottom:2px solid rgba(0,0,0,0.18);"
            "border-radius:6px;"
            "padding:2px;"
            "font-size:9pt;"
            "}"
            "QToolButton:hover {"
            "border-width:2px;"
            "}"
        )
        if btn.property("group_right"):
            style += "QToolButton{border-right:3px solid #6d8d9b;}"
        btn.setStyleSheet(style)

    def on_auto_changed(self):
        if self.chk_auto.isChecked():
            self.timer.start(int(self.spin_interval.value()) * 1000)
        else:
            self.timer.stop()

    def on_interval_changed(self):
        if self.chk_auto.isChecked():
            self.timer.start(int(self.spin_interval.value()) * 1000)

    # ---------------- helpers ----------------
    def _show_error(self, title: str, err: Exception):
        # Show a concise error message without traceback for end users.
        msg = f"{title}\n\n{err}"
        QtWidgets.QMessageBox.critical(self, title, msg)


def main():
    setup_logging()
    # High DPI attributes must be set BEFORE QApplication is created
    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app = QtWidgets.QApplication(sys.argv)
    try:
        app.setStyle('Fusion')
    except Exception:
        pass

    try:
        with open('app_style.qss', 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())
    except Exception:
        pass

    w = CabinetStatusWindow()
    # Maximize to help fit all doors on one page
    try:
        w.showMaximized()
    except Exception:
        pass

    # Wider by default to make the 10x12 shoe grid clearer on one page.
    w.resize(1500, 820)
    try:
        w.setMinimumWidth(1200)
    except Exception:
        pass

    w.showMaximized()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

