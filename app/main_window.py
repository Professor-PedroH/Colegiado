"""Janela principal: navegação, menus, backup e tema."""
import datetime as dt

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView)

from . import theme
from .db import backup_dir, br, parse
from .dialogs import DemandaDialog, ReuniaoDialog, abrir_arquivo, aviso, confirm, botoes
from .pages import DemandasPage, HomePage, PautaFuturaPage, PessoasPage, ReunioesPage


class MainWindow(QMainWindow):
    def __init__(self, db, curso_id, curso_nome):
        super().__init__()
        self.db, self.curso_id, self.curso_nome = db, curso_id, curso_nome
        self.trocar = False
        self.setWindowTitle(f"Colegiado – {curso_nome}")
        self.resize(1320, 820)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        marca = QLabel(f"<span style='font-family:Georgia,serif; font-size:15pt;'>{curso_nome}</span>"
                       f"<br><span style='color:#83827D;'>Colegiado do Curso</span>")
        marca.setWordWrap(True)
        marca.setContentsMargins(18, 18, 12, 6)
        sv.addWidget(marca)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.addItems(["Início", "Demandas", "Reuniões", "Próximas pautas", "Pessoas"])
        sv.addWidget(self.nav, 1)
        h.addWidget(side)
        self.stack = QStackedWidget()
        self.pages = [HomePage(self), DemandasPage(self), ReunioesPage(self), PautaFuturaPage(self), PessoasPage(self)]
        for p in self.pages:
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.nav.currentRowChanged.connect(self._nav)
        self.nav.setCurrentRow(0)
        self._menus()
        self.refresh_all()
        QTimer.singleShot(400, self.resumo)

    def _nav(self, i):
        self.stack.setCurrentIndex(i)
        self.pages[i].refresh()

    def _menus(self):
        mb = self.menuBar()
        m = mb.addMenu("Arquivo")
        self._act(m, "Trocar de curso", self._trocar)
        m.addSeparator()
        self._act(m, "Sair", self.close)
        m = mb.addMenu("Backup")
        self._act(m, "Exportar backup…", self.exportar)
        self._act(m, "Importar backup…", self.importar)
        self._act(m, "Abrir pasta dos backups automáticos", lambda: abrir_arquivo(backup_dir()))
        m.addSeparator()
        self._act(m, "Histórico de alterações", self.historico)
        m = mb.addMenu("Exibir")
        self._act(m, "Alternar tema claro/escuro", self.alternar_tema)

    def _act(self, menu, texto, fn):
        a = QAction(texto, self)
        a.triggered.connect(lambda *_: fn())
        menu.addAction(a)

    # ---- atualização
    def refresh_all(self):
        for p in self.pages:
            p.refresh()

    def marcar(self, did, concluida):
        self.db.marcar(did, concluida)
        QTimer.singleShot(0, self.refresh_all)

    # ---- ações compartilhadas pelas páginas
    def editar_demanda(self, did):
        DemandaDialog(self.db, self.curso_id, did=did, parent=self).exec()
        self.refresh_all()

    def nova_demanda(self, prazo=None):
        DemandaDialog(self.db, self.curso_id, prazo=prazo, parent=self).exec()
        self.refresh_all()

    def editar_reuniao(self, rid):
        ReuniaoDialog(self.db, self.curso_id, self.curso_nome, rid, self).exec()
        self.refresh_all()

    # ---- backup / tema
    def exportar(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar backup", f"backup_colegiado_{dt.datetime.now():%Y%m%d_%H%M}.json",
                                              "Backup (*.json)")
        if path:
            self.db.export_json(path)
            self.db.log("Backup exportado", path)
            aviso(self, "Backup salvo com sucesso.", "Pronto")

    def importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar backup", "", "Backup (*.json)")
        if not path or not confirm(self, "Importar substitui TODOS os dados atuais pelos do arquivo "
                                         "(uma cópia dos dados atuais é guardada antes). Continuar?"):
            return
        try:
            self.db.import_json(path)
        except Exception as e:
            return aviso(self, f"Não foi possível importar: {e}", "Erro")
        aviso(self, "Backup importado. Escolha o curso novamente.", "Pronto")
        self._trocar()

    def alternar_tema(self):
        novo = "claro" if theme.P["nome"] == "escuro" else "escuro"
        theme.set_theme(novo)
        self.db.set_cfg("tema", novo)
        QApplication.instance().setStyleSheet(theme.qss())
        self.refresh_all()

    def historico(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico de alterações")
        dlg.resize(800, 500)
        t = QTableWidget(0, 3)
        t.setHorizontalHeaderLabels(["Quando", "Ação", "Detalhe"])
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for r in self.db.historico():
            i = t.rowCount()
            t.insertRow(i)
            quando = dt.datetime.fromisoformat(r["ts"]).strftime("%d/%m/%Y %H:%M")
            for c, v in enumerate((quando, r["acao"], r["detalhe"])):
                t.setItem(i, c, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        v = QVBoxLayout(dlg)
        v.addWidget(t)
        v.addLayout(botoes(dlg, "Fechar"))
        dlg.exec()

    def _trocar(self):
        self.trocar = True
        self.close()

    # ---- resumo ao abrir
    def resumo(self):
        hoje = dt.date.today()
        rows = [d for d in self.db.demandas(self.curso_id) if d["prazo"]]
        atras = [d for d in rows if parse(d["prazo"]) < hoje]
        prox = [d for d in rows if hoje <= parse(d["prazo"]) <= hoje + dt.timedelta(days=7)]
        if not atras and not prox:
            return
        linhas = []
        if atras:
            linhas.append(f"{len(atras)} demanda(s) ATRASADA(S):")
            linhas += [f"  • {d['titulo']} (prazo {br(d['prazo'])})" for d in atras[:6]]
        if prox:
            linhas.append(f"\n{len(prox)} vencendo nos próximos 7 dias:")
            linhas += [f"  • {d['titulo']} (prazo {br(d['prazo'])})" for d in prox[:6]]
        aviso(self, "\n".join(linhas), "Resumo de hoje")

    def closeEvent(self, e):
        try:
            self.db.auto_backup()
        except OSError:
            pass
        e.accept()
