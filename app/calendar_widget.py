"""Calendário próprio com visões Mês e Semana. Mostra prazos de demandas e reuniões."""
import datetime as dt
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .db import add_months, iso

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]


class Chip(QLabel):
    clicked = Signal()

    def __init__(self, texto, fg, bg, tip=""):
        super().__init__(texto)
        self.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:4px; padding:1px 5px; font-size:8pt;")
        self.setToolTip(tip or texto)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        self.clicked.emit()


class DayCell(QFrame):
    dbl = Signal(object)

    def __init__(self, day, fora, hoje):
        super().__init__()
        self.day = day
        p = theme.P
        self.setObjectName("cell")
        self.setStyleSheet(f"QFrame#cell {{ background:{p['alt'] if fora else p['card']}; "
                           f"border:{2 if hoje else 1}px solid {p['accent'] if hoje else p['border']}; border-radius:6px; }}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 3, 4, 3)
        self.lay.setSpacing(2)
        n = QLabel(str(day.day))
        cor = p["accent"] if hoje else (p["muted"] if fora else p["text"])
        n.setStyleSheet(f"color:{cor}; font-weight:{'700' if hoje else '400'}; background:transparent; border:none;")
        self.lay.addWidget(n)

    def mouseDoubleClickEvent(self, e):
        self.dbl.emit(self.day)


class CalendarWidget(QWidget):
    abrir_demanda = Signal(int)
    abrir_reuniao = Signal(int)
    nova_reuniao = Signal(object)

    def __init__(self):
        super().__init__()
        self.ref = dt.date.today()
        self.modo = "mes"
        self.eventos = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-family:Georgia,serif; font-size:16pt;")
        b_prev, b_hoje, b_next = QPushButton("‹"), QPushButton("Hoje"), QPushButton("›")
        b_prev.clicked.connect(lambda: self.mover(-1))
        b_next.clicked.connect(lambda: self.mover(1))
        b_hoje.clicked.connect(self.ir_hoje)
        self.b_mes, self.b_sem = QPushButton("Mês"), QPushButton("Semana")
        for b, m in ((self.b_mes, "mes"), (self.b_sem, "semana")):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.clicked.connect(partial(self.set_modo, m))
        self.b_mes.setChecked(True)
        for w in (b_prev, b_hoje, b_next):
            top.addWidget(w)
        top.addWidget(self.titulo)
        top.addStretch()
        top.addWidget(self.b_mes)
        top.addWidget(self.b_sem)
        lay.addLayout(top)
        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(0, 6, 0, 0)
        self.grid.setSpacing(4)
        lay.addWidget(self.host, 1)

    def set_eventos(self, eventos):
        self.eventos = eventos
        self.rebuild()

    def set_modo(self, modo):
        self.modo = modo
        self.rebuild()

    def ir_hoje(self):
        self.ref = dt.date.today()
        self.rebuild()

    def mover(self, delta):
        self.ref = add_months(self.ref, delta) if self.modo == "mes" else self.ref + dt.timedelta(weeks=delta)
        self.rebuild()

    def _abrir(self, ev):
        (self.abrir_reuniao if ev["kind"] == "meet" else self.abrir_demanda).emit(ev["id"])

    def _zoom(self, dia):
        self.ref, self.modo = dia, "semana"
        self.b_sem.setChecked(True)
        self.rebuild()

    def rebuild(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        p, hoje = theme.P, dt.date.today()
        if self.modo == "mes":
            primeiro = self.ref.replace(day=1)
            ini = primeiro - dt.timedelta(days=(primeiro.weekday() + 1) % 7)
            n, limite = 42, 3
            self.titulo.setText(f"{MESES[self.ref.month - 1].capitalize()} de {self.ref.year}")
        else:
            ini = self.ref - dt.timedelta(days=(self.ref.weekday() + 1) % 7)
            n, limite = 7, 14
            self.titulo.setText(f"{ini:%d/%m} – {ini + dt.timedelta(days=6):%d/%m/%Y}")
        for i, nome in enumerate(DIAS):
            l = QLabel(nome)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(f"color:{p['muted']}; font-weight:600;")
            self.grid.addWidget(l, 0, i)
        cores = {"late": (p["late"], p["late_bg"]), "soon": (p["soon"], p["soon_bg"]),
                 "open": (p["accent"], p["sel"]), "meet": (p["meet"], p["meet_bg"])}
        for k in range(n):
            d = ini + dt.timedelta(days=k)
            fora = self.modo == "mes" and d.month != self.ref.month
            cell = DayCell(d, fora, d == hoje)
            cell.setMinimumHeight(78 if self.modo == "mes" else 260)
            cell.dbl.connect(self.nova_reuniao.emit)
            cell.setToolTip("Duplo clique: criar reunião neste dia")
            evs = self.eventos.get(iso(d), [])
            for ev in evs[:limite]:
                fg, bg = cores[ev["kind"]]
                chip = Chip(ev["texto"], fg, bg, ev.get("tip", ""))
                chip.clicked.connect(partial(self._abrir, ev))
                cell.lay.addWidget(chip)
            if len(evs) > limite:
                mais = Chip(f"+{len(evs) - limite} mais", p["muted"], p["alt"])
                mais.clicked.connect(partial(self._zoom, d))
                cell.lay.addWidget(mais)
            cell.lay.addStretch()
            self.grid.addWidget(cell, k // 7 + 1, k % 7)
        for r in range(1, n // 7 + 1):
            self.grid.setRowStretch(r, 1)
        for c in range(7):
            self.grid.setColumnStretch(c, 1)
