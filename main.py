"""Colegiado – Controle de Demandas. Execute: python main.py"""
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from PySide6.QtGui import QIcon

from app import theme
from app.db import DB, data_dir
from app.dialogs import CursoDialog
from app.main_window import MainWindow
from app.splash import aguardar, criar_splash


def _hook(tipo, valor, tb):
    txt = "".join(traceback.format_exception(tipo, valor, tb))
    try:
        (data_dir() / "erro.log").open("a", encoding="utf-8").write(txt + "\n")
    except OSError:
        pass
    QMessageBox.critical(None, "Erro inesperado", f"{valor}\n\nDetalhes gravados em erro.log (pasta %APPDATA%\\ColegiadoDemandas).")


def main():
    sys.excepthook = _hook
    app = QApplication(sys.argv)
    app.setApplicationName("Colegiado")
    db = DB()
    theme.set_theme(db.cfg("tema", "claro"))
    app.setStyleSheet(theme.qss())
    app.setWindowIcon(QIcon(theme.asset("icon.ico")))
    splash = criar_splash()
    aguardar(1500)
    first = True
    while True:
        dlg = CursoDialog(db)
        if first:
            splash.finish(dlg)
            first = False
        if not dlg.exec():
            break
        win = MainWindow(db, dlg.curso_id, dlg.nome)
        win.show()
        app.exec()
        if not win.trocar:
            break


if __name__ == "__main__":
    main()
