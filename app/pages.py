"""Páginas da janela principal."""
import datetime as dt
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import reports, theme
from .calendar_widget import CalendarWidget
from .db import br, iso, parse
from .dialogs import (PautaDialog, PessoaDialog, UR, abrir_arquivo, aviso, confirm, CHK, UNC, CHECKABLE)


def titulo(txt):
    l = QLabel(txt)
    l.setStyleSheet("font-family:Georgia,serif; font-size:18pt;")
    return l


def botao(txt, fn, primary=False, danger=False):
    b = QPushButton(txt)
    b.clicked.connect(fn)
    if primary:
        b.setProperty("primary", True)
    if danger:
        b.setProperty("danger", True)
    return b


def tabela(cols, stretch=None):
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().hide()
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    h = t.horizontalHeader()
    h.setHighlightSections(False)
    for i in range(len(cols)):
        h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i == stretch else QHeaderView.ResizeMode.ResizeToContents)
    return t


def item(txt, uid=None, cor=None, bold=False):
    it = QTableWidgetItem(txt)
    if uid is not None:
        it.setData(UR, uid)
    if cor:
        it.setForeground(QBrush(QColor(cor)))
    if bold:
        f = QFont()
        f.setBold(True)
        it.setFont(f)
    return it


def selecionado(t):
    r = t.currentRow()
    return t.item(r, 0).data(UR) if r >= 0 and t.item(r, 0) else None


# ------------------------------------------------------------ tabela de demandas
class DemandaTable(QTableWidget):
    marcou = Signal(int, bool)
    abrir = Signal(int)
    COLS = ["", "Prazo", "Prior.", "Status", "Demanda", "Responsáveis", "Pauta / reunião"]

    def __init__(self, concluidas=False, compacta=False):
        super().__init__(0, len(self.COLS))
        self.concluidas = concluidas
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().hide()
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setWordWrap(True)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        for i in range(len(self.COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i in (4,) else QHeaderView.ResizeMode.ResizeToContents)
        if compacta:
            for c in (3, 6):
                self.setColumnHidden(c, True)
            h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(5, 110)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemChanged.connect(self._chg)
        self.cellDoubleClicked.connect(lambda r, c: self.abrir.emit(self.item(r, 0).data(UR)))

    def _chg(self, it):
        if it.column() == 0:
            self.marcou.emit(it.data(UR), it.checkState() == CHK)

    def carregar(self, rows):
        p, hoje = theme.P, dt.date.today()
        self.blockSignals(True)
        self.setRowCount(0)
        for d in rows:
            i = self.rowCount()
            self.insertRow(i)
            chk = QTableWidgetItem()
            chk.setFlags(CHECKABLE)
            chk.setCheckState(CHK if self.concluidas else UNC)
            chk.setData(UR, d["id"])
            prazo = parse(d["prazo"])
            cor = None
            if not self.concluidas and prazo:
                cor = p["late"] if prazo < hoje else p["soon"] if prazo <= hoje + dt.timedelta(days=7) else None
            origem = d["pautas"] or (f"Reunião {br(d['r_data'])}" if d["r_data"] else "Avulsa")
            texto = br(d["concluida_em"]) if self.concluidas else br(d["prazo"])
            self.setItem(i, 0, chk)
            self.setItem(i, 1, item(texto, cor=cor, bold=bool(cor)))
            self.setItem(i, 2, item(d["prioridade"], cor=p["late"] if d["prioridade"] == "Alta" else p["muted"]))
            self.setItem(i, 3, item(d["status"]))
            self.setItem(i, 4, item(d["titulo"]))
            self.setItem(i, 5, item(d["resp"] or "—"))
            self.setItem(i, 6, item(origem))
        self.resizeRowsToContents()
        self.blockSignals(False)
        self.horizontalHeaderItem(1).setText("Concluída em" if self.concluidas else "Prazo")


# ------------------------------------------------------------ início
class HomePage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        row = QHBoxLayout()
        self.cards = {}
        for k, t in (("atrasadas", "Atrasadas"), ("semana", "Vencem em 7 dias"), ("abertas", "Em aberto"),
                     ("reuniao", "Próxima reunião")):
            f = QFrame()
            f.setProperty("card", True)
            v = QVBoxLayout(f)
            n, c = QLabel("0"), QLabel(t)
            v.addWidget(n)
            v.addWidget(c)
            self.cards[k] = (n, c)
            row.addWidget(f)
        lay.addLayout(row)
        sp = QSplitter()
        self.cal = CalendarWidget()
        self.cal.abrir_demanda.connect(mw.editar_demanda)
        self.cal.abrir_reuniao.connect(mw.editar_reuniao)
        self.cal.nova_reuniao.connect(lambda d: mw.editar_reuniao(None, d))
        sp.addWidget(self.cal)
        painel = QFrame()
        painel.setProperty("card", True)
        v = QVBoxLayout(painel)
        h = QHBoxLayout()
        h.addWidget(QLabel("<b>Em aberto – por vencimento</b>"))
        h.addStretch()
        h.addWidget(botao("+ Nova demanda", lambda: mw.nova_demanda(), True))
        v.addLayout(h)
        self.lista = DemandaTable(compacta=True)
        self.lista.marcou.connect(mw.marcar)
        self.lista.abrir.connect(mw.editar_demanda)
        v.addWidget(self.lista)
        sp.addWidget(painel)
        painel.setMinimumWidth(470)
        self.cal.setMinimumWidth(520)
        sp.setStretchFactor(0, 1)
        sp.setStretchFactor(1, 1)
        lay.addWidget(sp, 1)

    def refresh(self):
        mw, p, hoje = self.mw, theme.P, dt.date.today()
        rows = mw.db.demandas(mw.curso_id)
        reunioes = [r for r in mw.db.reunioes(mw.curso_id) if r["status"] != "Cancelada"]
        eventos = {}
        atras = sem = 0
        for d in rows:
            if not d["prazo"]:
                continue
            pz = parse(d["prazo"])
            kind = "late" if pz < hoje else "soon" if pz <= hoje + dt.timedelta(days=7) else "open"
            atras += kind == "late"
            sem += kind == "soon"
            eventos.setdefault(d["prazo"], []).append(
                dict(kind=kind, id=d["id"], texto=d["titulo"], tip=f"{d['titulo']}\nResponsáveis: {d['resp'] or '—'}"))
        futuras = [r for r in reunioes if r["data"] >= iso(hoje)]
        for r in reunioes:
            eventos.setdefault(r["data"], []).insert(
                0, dict(kind="meet", id=r["id"], texto=f"{r['hora']} Reunião", tip=f"Reunião {r['tipo']} – {r['local']}"))
        prox = min(futuras, key=lambda r: (r["data"], r["hora"]), default=None)
        vals = {"atrasadas": (str(atras), p["late"] if atras else p["text"]), "semana": (str(sem), p["soon"] if sem else p["text"]),
                "abertas": (str(len(rows)), p["text"]),
                "reuniao": (f"{br(prox['data'])[:5]} {prox['hora']}" if prox else "—", p["text"])}
        for k, (txt, cor) in vals.items():
            n, c = self.cards[k]
            n.setText(txt)
            n.setStyleSheet(f"font-family:Georgia,serif; font-size:22pt; color:{cor};")
            c.setStyleSheet(f"color:{p['muted']};")
        self.cal.set_eventos(eventos)
        self.lista.carregar(rows)


# ------------------------------------------------------------ demandas
class DemandasPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.addWidget(titulo("Demandas"))
        top.addStretch()
        top.addWidget(botao("Exportar Excel", self.exportar))
        top.addWidget(botao("+ Nova demanda", lambda: mw.nova_demanda(), True))
        lay.addLayout(top)
        fl = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por título, responsável, pauta…")
        self.f_resp, self.f_status, self.f_prio = QComboBox(), QComboBox(), QComboBox()
        self.f_status.addItems(["Todos os status", "Aberta", "Em andamento", "Aguardando terceiros"])
        self.f_prio.addItems(["Todas as prioridades", "Alta", "Média", "Baixa"])
        fl.addWidget(self.busca, 2)
        for w in (self.f_resp, self.f_status, self.f_prio):
            fl.addWidget(w, 1)
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.textChanged).connect(self.refresh)
        self.busca.textChanged.connect(self.refresh)
        lay.addLayout(fl)
        self.tabs = QTabWidget()
        self.t_ab, self.t_co = DemandaTable(), DemandaTable(concluidas=True)
        for t in (self.t_ab, self.t_co):
            t.marcou.connect(mw.marcar)
            t.abrir.connect(mw.editar_demanda)
        self.tabs.addTab(self.t_ab, "Em aberto")
        self.tabs.addTab(self.t_co, "Concluídas")
        lay.addWidget(self.tabs, 1)
        bot = QHBoxLayout()
        bot.addWidget(botao("Editar", self.editar))
        bot.addWidget(botao("Excluir", self.excluir, danger=True))
        bot.addStretch()
        lay.addLayout(bot)

    def _tabela(self):
        return self.tabs.currentWidget()

    def filtrar(self, rows, concl):
        txt, resp = self.busca.text().lower(), self.f_resp.currentData()
        st, pr = self.f_status.currentIndex(), self.f_prio.currentText()
        out = []
        for d in rows:
            if txt and txt not in " ".join((d["titulo"], d["descricao"] or "", d["resp"], d["pautas"], d["sei"] or "")).lower():
                continue
            if resp == "coord" and not d["coord"]:
                continue
            if isinstance(resp, int) and resp not in d["resp_ids"]:
                continue
            if st and not concl and d["status"] != self.f_status.currentText():
                continue
            if self.f_prio.currentIndex() and d["prioridade"] != pr:
                continue
            out.append(d)
        return out

    def refresh(self):
        mw = self.mw
        atual = self.f_resp.currentData()
        self.f_resp.blockSignals(True)
        self.f_resp.clear()
        self.f_resp.addItem("Todos os responsáveis", "*")
        self.f_resp.addItem("Coordenação", "coord")
        for p in mw.db.pessoas(mw.curso_id):
            self.f_resp.addItem(p["nome"], p["id"])
        self.f_resp.setCurrentIndex(max(0, self.f_resp.findData(atual)))
        self.f_resp.blockSignals(False)
        for i, (t, c) in enumerate(((self.t_ab, False), (self.t_co, True))):
            rows = self.filtrar(mw.db.demandas(mw.curso_id, c), c)
            t.carregar(rows)
            self.tabs.setTabText(i, f"{'Concluídas' if c else 'Em aberto'} ({len(rows)})")

    def editar(self):
        i = selecionado(self._tabela())
        if i:
            self.mw.editar_demanda(i)

    def excluir(self):
        i = selecionado(self._tabela())
        if i and confirm(self, "Excluir esta demanda definitivamente?"):
            self.mw.db.excluir_demanda(i)
            self.mw.refresh_all()

    def exportar(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar demandas", f"Demandas_{dt.date.today():%Y-%m-%d}.xlsx",
                                              "Excel (*.xlsx)")
        if path:
            reports.exportar_demandas(self.mw.db, self.mw.curso_id, path)
            abrir_arquivo(path)


# ------------------------------------------------------------ reuniões
class ReunioesPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.addWidget(titulo("Reuniões"))
        top.addStretch()
        top.addWidget(botao("Relatório em PDF…", mw.relatorio))
        top.addWidget(botao("+ Nova reunião", lambda: mw.editar_reuniao(None), True))
        lay.addLayout(top)
        self.t = tabela(["Data", "Horário", "Ata nº", "Tipo", "Local", "Situação", "Pautas", "Demandas", "Anexos"], stretch=4)
        self.t.cellDoubleClicked.connect(lambda *_: self.abrir())
        lay.addWidget(self.t, 1)
        bot = QHBoxLayout()
        bot.addWidget(botao("Abrir / editar", self.abrir))
        bot.addWidget(botao("Gerar ata (Word)", self.ata))
        bot.addWidget(botao("Excluir", self.excluir, danger=True))
        bot.addStretch()
        lay.addLayout(bot)

    def refresh(self):
        db, p = self.mw.db, theme.P
        self.t.setRowCount(0)
        for r in db.reunioes(self.mw.curso_id):
            i = self.t.rowCount()
            self.t.insertRow(i)
            np_ = db.one("SELECT COUNT(*) n FROM pauta WHERE reuniao_id=?", (r["id"],))["n"]
            nd = db.one("SELECT COUNT(*) n FROM demanda WHERE reuniao_id=?", (r["id"],))["n"]
            na = db.one("SELECT COUNT(*) n FROM anexo WHERE reuniao_id=?", (r["id"],))["n"]
            passou = r["status"] == "Agendada" and r["data"] < iso(dt.date.today())
            cor = p["muted"] if r["status"] == "Cancelada" else (p["soon"] if passou else None)
            situacao = "Agendada (já passou)" if passou else r["status"]
            ata = f"{r['numero']}/{r['data'][:4]}" if r["numero"] else "—"
            vals = (br(r["data"]), r["hora"], ata, r["tipo"], r["local"], situacao, str(np_), str(nd), str(na))
            for c, v in enumerate(vals):
                self.t.setItem(i, c, item(v, r["id"] if c == 0 else None, cor))

    def abrir(self):
        i = selecionado(self.t)
        if i:
            self.mw.editar_reuniao(i)

    def ata(self):
        i = selecionado(self.t)
        if not i:
            return aviso(self, "Selecione uma reunião.")
        r = self.mw.db.one("SELECT data FROM reuniao WHERE id=?", (i,))
        path, _ = QFileDialog.getSaveFileName(self, "Salvar ata", f"Ata_{r['data']}.docx", "Documento Word (*.docx)")
        if path:
            reports.gerar_ata(self.mw.db, self.mw.curso_nome, i, path)
            abrir_arquivo(path)

    def excluir(self):
        i = selecionado(self.t)
        if i and confirm(self, "Excluir a reunião e seus pontos de pauta? As demandas continuam, como avulsas."):
            self.mw.db.excluir_reuniao(i)
            self.mw.refresh_all()


# ------------------------------------------------------------ próximas pautas
class PautaFuturaPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.addWidget(titulo("Próximos pontos de pauta"))
        top.addStretch()
        top.addWidget(botao("+ Novo ponto", self.novo, True))
        lay.addLayout(top)
        lay.addWidget(QLabel("Guarde aqui os assuntos que surgirem e traga-os para a pauta quando criar a reunião."))
        self.t = tabela(["Ponto de pauta", "Descrição"], stretch=1)
        self.t.cellDoubleClicked.connect(lambda *_: self.editar())
        lay.addWidget(self.t, 1)
        bot = QHBoxLayout()
        bot.addWidget(botao("Editar", self.editar))
        bot.addWidget(botao("Excluir", self.excluir, danger=True))
        bot.addStretch()
        lay.addLayout(bot)

    def refresh(self):
        self.t.setRowCount(0)
        for r in self.mw.db.pautas_futuras(self.mw.curso_id):
            i = self.t.rowCount()
            self.t.insertRow(i)
            self.t.setItem(i, 0, item(r["titulo"], r["id"]))
            self.t.setItem(i, 1, item(r["descricao"] or ""))

    def novo(self):
        PautaDialog(self.mw.db, self.mw.curso_id, parent=self).exec()
        self.mw.refresh_all()

    def editar(self):
        i = selecionado(self.t)
        if i:
            PautaDialog(self.mw.db, self.mw.curso_id, i, self).exec()
            self.mw.refresh_all()

    def excluir(self):
        i = selecionado(self.t)
        if i and confirm(self, "Excluir este ponto de pauta?"):
            self.mw.db.excluir_pauta(i)
            self.mw.refresh_all()


# ------------------------------------------------------------ pessoas
class PessoasPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.addWidget(titulo("Pessoas"))
        top.addStretch()
        top.addWidget(botao("+ Nova pessoa", self.nova, True))
        lay.addLayout(top)
        fl = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por nome…")
        self.cat = QComboBox()
        self.cat.addItems(["Todas as categorias", "Docente", "TAE", "Discente"])
        self.so_membros = QCheckBox("Somente membros do Colegiado")
        fl.addWidget(self.busca, 2)
        fl.addWidget(self.cat, 1)
        fl.addWidget(self.so_membros)
        self.busca.textChanged.connect(self.refresh)
        self.cat.currentIndexChanged.connect(self.refresh)
        self.so_membros.toggled.connect(self.refresh)
        lay.addLayout(fl)
        self.t = tabela(["Nome", "Categoria", "Colegiado", "Função", "E-mail", "Telefone", "Mandato"], stretch=0)
        self.t.cellDoubleClicked.connect(lambda *_: self.editar())
        lay.addWidget(self.t, 1)
        bot = QHBoxLayout()
        bot.addWidget(botao("Editar", self.editar))
        bot.addWidget(botao("Excluir", self.excluir, danger=True))
        bot.addStretch()
        lay.addLayout(bot)

    def refresh(self):
        p, txt = theme.P, self.busca.text().lower()
        self.t.setRowCount(0)
        for x in self.mw.db.pessoas(self.mw.curso_id, so_membros=self.so_membros.isChecked()):
            if txt and txt not in x["nome"].lower():
                continue
            if self.cat.currentIndex() and x["categoria"] != self.cat.currentText():
                continue
            mand = " a ".join(br(v) for v in (x["mandato_ini"], x["mandato_fim"]) if v)
            cor = None if x["ativo"] else p["muted"]
            vals = (x["nome"] + ("" if x["ativo"] else " (inativo)"), x["categoria"], "Sim" if x["membro"] else "—",
                    x["funcao"] or "", x["email"] or "", x["telefone"] or "", mand)
            i = self.t.rowCount()
            self.t.insertRow(i)
            for c, v in enumerate(vals):
                self.t.setItem(i, c, item(v, x["id"] if c == 0 else None, cor))

    def nova(self):
        PessoaDialog(self.mw.db, self.mw.curso_id, parent=self).exec()
        self.mw.refresh_all()

    def editar(self):
        i = selecionado(self.t)
        if i:
            PessoaDialog(self.mw.db, self.mw.curso_id, i, self).exec()
            self.mw.refresh_all()

    def excluir(self):
        i = selecionado(self.t)
        if i and confirm(self, "Excluir esta pessoa? Ela será removida das responsabilidades e presenças. "
                               "(Para apenas ocultá-la, desmarque \"Ativo no curso\".)"):
            self.mw.db.excluir_pessoa(i)
            self.mw.refresh_all()
