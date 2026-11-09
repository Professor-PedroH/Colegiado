"""Janela principal: navegação, menus, backup e tema."""
import datetime as dt
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QMainWindow, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme
from .db import backup_dir, br, parse
from .dialogs import (CursoDadosDialog, DemandaDialog, RelatorioDialog, ReuniaoDialog, abrir_arquivo, aviso, botoes,
                      importar_backup_ui)
from .info import APP_NOME, AUTOR, VERSAO
from .pages import DemandasPage, HomePage, PautaFuturaPage, PessoasPage, ReunioesPage


class MainWindow(QMainWindow):
    def __init__(self, db, curso_id, curso_nome):
        super().__init__()
        self.db, self.curso_id, self.curso_nome = db, curso_id, curso_nome
        self.trocar = False
        self.setWindowIcon(QIcon(theme.asset("icon.ico")))
        self.resize(1320, 820)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(QPixmap(theme.asset("logo.png")).scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        logo.setContentsMargins(18, 16, 0, 0)
        sv.addWidget(logo)
        self.marca = QLabel()
        self.marca.setWordWrap(True)
        self.marca.setContentsMargins(18, 8, 12, 2)
        sv.addWidget(self.marca)
        self.coord_lbl = QLabel()
        self.coord_lbl.setWordWrap(True)
        self.coord_lbl.setContentsMargins(18, 0, 12, 8)
        sv.addWidget(self.coord_lbl)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.addItems(["Início", "Demandas", "Reuniões", "Próximas pautas", "Pessoas"])
        sv.addWidget(self.nav, 1)
        rodape = QLabel(f"<span style='color:#83827D; font-size:8pt;'>Desenvolvido por</span><br>"
                        f"<span style='font-size:9pt;'>{AUTOR}</span>")
        rodape.setWordWrap(True)
        rodape.setContentsMargins(18, 8, 12, 14)
        sv.addWidget(rodape)
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
        self.atualiza_cabecalho()
        self.refresh_all()
        QTimer.singleShot(400, self.resumo)

    def atualiza_cabecalho(self):
        c = self.db.curso(self.curso_id)
        self.curso_nome = c["nome"]
        self.setWindowTitle(f"Colegiado – {self.curso_nome}")
        self.marca.setText(f"<span style='font-family:Georgia,serif; font-size:15pt;'>{self.curso_nome}</span>"
                           f"<br><span style='color:#83827D;'>Colegiado do Curso</span>")
        coord = (c.get("coordenador") or "").strip()
        self.coord_lbl.setText(f"<span style='color:#83827D; font-size:8pt;'>{c.get('tratamento') or 'Coordenador'}</span>"
                               f"<br><span style='font-size:9pt;'>{coord}</span>" if coord else "")
        self.coord_lbl.setVisible(bool(coord))

    def _nav(self, i):
        self.stack.setCurrentIndex(i)
        self.pages[i].refresh()

    def _menus(self):
        mb = self.menuBar()
        m = mb.addMenu("Arquivo")
        self._act(m, "Dados do curso (coordenador(a), nome)…", self.dados_curso)
        self._act(m, "Trocar de curso", self._trocar)
        m.addSeparator()
        self._act(m, "Sair", self.close)
        m = mb.addMenu("Relatórios")
        self._act(m, "Relatório do período em PDF…", self.relatorio)
        m = mb.addMenu("Backup")
        self._act(m, "Exportar backup completo (todos os cursos)…", lambda: self.exportar(False))
        self._act(m, "Exportar somente este curso…", lambda: self.exportar(True))
        self._act(m, "Importar backup…", self.importar)
        self._act(m, "Abrir pasta dos backups automáticos", lambda: abrir_arquivo(backup_dir()))
        m.addSeparator()
        self._act(m, "Histórico de alterações", self.historico)
        m = mb.addMenu("Exibir")
        self._act(m, "Alternar tema claro/escuro", self.alternar_tema)
        m = mb.addMenu("Ajuda")
        self._act(m, "Sobre", self.sobre)

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

    def editar_reuniao(self, rid, data=None):
        ReuniaoDialog(self.db, self.curso_id, self.curso_nome, rid, self, data).exec()
        self.refresh_all()

    def relatorio(self):
        RelatorioDialog(self.db, self.curso_id, self).exec()

    def dados_curso(self):
        CursoDadosDialog(self.db, self.curso_id, self).exec()
        self.atualiza_cabecalho()
        self.refresh_all()

    # ---- backup / tema
    def exportar(self, so_curso):
        if so_curso:
            slug = re.sub(r"\W+", "_", self.curso_nome).strip("_")
            nome = f"curso_{slug}_{dt.date.today():%Y%m%d}.zip"
        else:
            nome = f"backup_completo_{dt.datetime.now():%Y%m%d_%H%M}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar backup", nome, "Backup (*.zip)")
        if path:
            self.db.export_backup(path, self.curso_id if so_curso else None)
            self.db.log("Backup exportado" + (" (curso)" if so_curso else " (completo)"), path)
            aviso(self, "Backup salvo com sucesso (dados e documentos anexos).", "Pronto")

    def importar(self):
        if importar_backup_ui(self, self.db):
            self._trocar()

    def alternar_tema(self):
        novo = "claro" if theme.P["nome"] == "escuro" else "escuro"
        theme.set_theme(novo)
        self.db.set_cfg("tema", novo)
        QApplication.instance().setStyleSheet(theme.qss())
        self.refresh_all()

    def sobre(self):
        aviso(self, f"{APP_NOME}\nVersão {VERSAO}\n\nDesenvolvido por {AUTOR}.", "Sobre")

    def historico(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico de alterações")
        dlg.resize(800, 500)
        t = QTableWidget(0, 3)
        t.setHorizontalHeaderLabels(["Quando", "Ação", "Detalhe"])
        t.verticalHeader().hide()
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
        passadas = self.db.reunioes_sem_situacao(self.curso_id)
        mandatos = self.db.membros_mandato(self.curso_id, 30)
        blocos = []
        if atras:
            blocos.append([f"{len(atras)} demanda(s) ATRASADA(S):"] +
                          [f"  • {d['titulo']} (prazo {br(d['prazo'])})" for d in atras[:6]])
        if prox:
            blocos.append([f"{len(prox)} vencendo nos próximos 7 dias:"] +
                          [f"  • {d['titulo']} (prazo {br(d['prazo'])})" for d in prox[:6]])
        if passadas:
            blocos.append([f"{len(passadas)} reunião(ões) já passou(aram) e ainda está(ão) como \"Agendada\" "
                           "(atualize a situação para Realizada ou Cancelada):"] +
                          [f"  • {br(r['data'])} – {r['tipo']}" for r in passadas[:6]])
        if mandatos:
            blocos.append(["Mandatos vencidos ou vencendo em até 30 dias:"] +
                          [f"  • {p['nome']} – {'terminou' if p['mandato_fim'] < hoje.isoformat() else 'termina'} "
                           f"em {br(p['mandato_fim'])}" for p in mandatos[:6]])
        if blocos:
            aviso(self, "\n\n".join("\n".join(b) for b in blocos), "Resumo de hoje")

    def closeEvent(self, e):
        try:
            self.db.auto_backup()
        except OSError:
            pass
        e.accept()
