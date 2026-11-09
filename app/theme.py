"""Paleta sóbria (inspirada no Claude) com modos claro e escuro."""
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

LIGHT = dict(bg="#F5F4ED", card="#FFFFFF", alt="#FAF9F5", text="#1F1E1D", muted="#83827D", border="#E3E0D3",
             accent="#C96442", accent_h="#B5573A", on_accent="#FFFFFF", sel="#EFE6DA",
             late="#B53333", late_bg="#F6DEDA", soon="#9A6A12", soon_bg="#F6E9C9",
             ok="#4F7A4A", meet="#4F5B7A", meet_bg="#E2E5EE")
DARK = dict(bg="#262624", card="#30302E", alt="#2B2B29", text="#FAF9F5", muted="#A6A59F", border="#444441",
            accent="#D97757", accent_h="#E58B6E", on_accent="#1F1E1D", sel="#3C3A37",
            late="#F08A7E", late_bg="#4A2B28", soon="#E5B567", soon_bg="#4A3D22",
            ok="#8FBF88", meet="#A9B8DE", meet_bg="#33384A")

P = dict(LIGHT, nome="claro")


def asset(nome):
    """Caminho de um arquivo da pasta assets (funciona também no .exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / "assets" / nome)


def set_theme(nome):
    P.clear()
    P.update(DARK if nome == "escuro" else LIGHT)
    P["nome"] = "escuro" if nome == "escuro" else "claro"


def _check_icon():
    path = Path(tempfile.gettempdir()) / f"colegiado_check_{P['nome']}.png"
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setBrush(QColor(P["accent"]))
    qp.setPen(Qt.PenStyle.NoPen)
    qp.drawRoundedRect(0, 0, 16, 16, 4, 4)
    pen = QPen(QColor(P["on_accent"]), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    qp.setPen(pen)
    qp.drawPolyline([QPointF(4, 8.5), QPointF(7, 11.5), QPointF(12, 5)])
    qp.end()
    pm.save(str(path))
    return path.as_posix()


def qss():
    p = P
    chk = _check_icon()
    return f"""
* {{ font-family: 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 10pt; }}
QWidget {{ background: {p['bg']}; color: {p['text']}; }}
QLabel {{ background: transparent; }}
QFrame[card="true"] {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 10px; }}
QFrame[card="true"] QLabel {{ background: transparent; border: none; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
  background: {p['card']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 5px 8px;
  selection-background-color: {p['accent']}; selection-color: {p['on_accent']}; }}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{ border: 1px solid {p['accent']}; }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['border']};
  selection-background-color: {p['sel']}; selection-color: {p['text']}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 22px; }}
QPushButton {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {p['sel']}; }}
QPushButton:disabled {{ color: {p['muted']}; }}
QPushButton[primary="true"] {{ background: {p['accent']}; color: {p['on_accent']}; border: 1px solid {p['accent']}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {p['accent_h']}; }}
QPushButton[danger="true"] {{ color: {p['late']}; }}
QPushButton:checked {{ background: {p['accent']}; color: {p['on_accent']}; border-color: {p['accent']}; }}
QTableWidget, QListWidget {{ background: {p['card']}; alternate-background-color: {p['alt']}; border: 1px solid {p['border']};
  border-radius: 8px; gridline-color: {p['border']}; selection-background-color: {p['sel']}; selection-color: {p['text']}; outline: 0; }}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView::section {{ background: {p['alt']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border']};
  padding: 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {p['alt']}; border: none; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {p['muted']}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['accent']}; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTableView::indicator, QListView::indicator {{ width: 16px; height: 16px; border: 1px solid {p['muted']};
  border-radius: 4px; background: {p['card']}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {{ image: url({chk}); border: none; }}
QListWidget#nav {{ background: {p['alt']}; border: none; border-right: 1px solid {p['border']}; border-radius: 0; padding-top: 8px; }}
QListWidget#nav::item {{ padding: 11px 14px; margin: 2px 8px; border-radius: 6px; }}
QListWidget#nav::item:selected {{ background: {p['sel']}; color: {p['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QMenuBar {{ background: {p['bg']}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {p['sel']}; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; }}
QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 4px; }}
QCalendarWidget QAbstractItemView {{ background: {p['card']}; color: {p['text']}; selection-background-color: {p['accent']};
  selection-color: {p['on_accent']}; }}
QCalendarWidget QToolButton {{ background: {p['card']}; color: {p['text']}; }}
QSplitter::handle {{ background: transparent; }}
"""
