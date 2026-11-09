"""Tela de inicialização."""
from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QThread
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from . import theme


def criar_splash(coordenador):
    p, w, h = theme.P, 560, 340
    pm = QPixmap(w, h)
    pm.fill(QColor(p["bg"]))
    q = QPainter(pm)
    q.setRenderHint(QPainter.RenderHint.Antialiasing)
    q.setPen(QColor(p["border"]))
    q.drawRect(0, 0, w - 1, h - 1)
    logo = QPixmap(theme.asset("logo.png")).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
    q.drawPixmap((w - 96) // 2, 38, logo)
    centro = Qt.AlignmentFlag.AlignCenter
    q.setPen(QColor(p["text"]))
    q.setFont(QFont("Georgia", 20))
    q.drawText(QRectF(0, 150, w, 40), centro, "Controle de Demandas do Colegiado")
    q.setPen(QColor(p["muted"]))
    q.setFont(QFont("Segoe UI", 10))
    q.drawText(QRectF(0, 192, w, 24), centro, "Curso de Graduação")
    q.setPen(QColor(p["accent"]))
    q.drawLine(w // 2 - 30, 232, w // 2 + 30, 232)
    q.setPen(QColor(p["text"]))
    q.setFont(QFont("Segoe UI", 10))
    q.drawText(QRectF(0, 248, w, 24), centro, f"Coordenador: {coordenador}")
    q.setPen(QColor(p["muted"]))
    q.setFont(QFont("Segoe UI", 9))
    q.drawText(QRectF(0, 296, w, 22), centro, "Carregando…")
    q.end()
    s = QSplashScreen(pm)
    s.show()
    QApplication.processEvents()
    return s


def aguardar(ms=1500):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QApplication.processEvents()
        QThread.msleep(20)
