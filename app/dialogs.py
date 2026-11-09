"""Janelas de cadastro."""
import datetime as dt
import os

from PySide6.QtCore import QDate, QTime, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextEdit, QTimeEdit, QVBoxLayout, QWidget)

from . import reports, theme
from .db import PRIORIDADES, RECORRENCIAS, STATUS, br, parse

UR = Qt.ItemDataRole.UserRole
CHK, UNC = Qt.CheckState.Checked, Qt.CheckState.Unchecked
CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


def confirm(parent, texto):
    m = QMessageBox(QMessageBox.Icon.Question, "Confirmar", texto, parent=parent)
    sim = m.addButton("Sim", QMessageBox.ButtonRole.YesRole)
    m.addButton("Não", QMessageBox.ButtonRole.NoRole)
    m.exec()
    return m.clickedButton() is sim


def aviso(parent, texto, titulo="Atenção"):
    m = QMessageBox(QMessageBox.Icon.Information, titulo, texto, parent=parent)
    m.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    m.exec()


def abrir_arquivo(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def to_qdate(s):
    d = parse(s) if isinstance(s, str) else s
    return QDate(d.year, d.month, d.day) if d else QDate.currentDate()


def date_edit(s=None):
    w = QDateEdit()
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd/MM/yyyy")
    w.setDate(to_qdate(s))
    return w


def dstr(w):
    return w.date().toString("yyyy-MM-dd")


class OptDate(QWidget):
    """Data opcional: caixa de seleção + data."""

    def __init__(self, s=None):
        super().__init__()
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        self.cb = QCheckBox("definir")
        self.de = date_edit(s)
        self.de.setEnabled(bool(s))
        self.cb.setChecked(bool(s))
        self.cb.toggled.connect(self.de.setEnabled)
        l.addWidget(self.cb)
        l.addWidget(self.de)
        l.addStretch()

    def value(self):
        return dstr(self.de) if self.cb.isChecked() else None


def botoes(dlg, ok="Salvar", extra=()):
    row = QHBoxLayout()
    for b in extra:
        row.addWidget(b)
    row.addStretch()
    c = QPushButton("Cancelar")
    c.clicked.connect(dlg.reject)
    s = QPushButton(ok)
    s.setProperty("primary", True)
    s.setDefault(True)
    s.clicked.connect(dlg.accept)
    row.addWidget(c)
    row.addWidget(s)
    return row


def checklist(itens, marcados=()):
    """itens: [(texto, id)]"""
    lw = QListWidget()
    for texto, i in itens:
        it = QListWidgetItem(texto)
        it.setFlags(CHECKABLE)
        it.setCheckState(CHK if i in marcados else UNC)
        it.setData(UR, i)
        lw.addItem(it)
    return lw


def marcados(lw):
    return [lw.item(i).data(UR) for i in range(lw.count()) if lw.item(i).checkState() == CHK]


# ---------------------------------------------------------------- curso
class CursoDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.nome = None
        self.setWindowTitle("Colegiado – Controle de Demandas")
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(10)
        topo = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(theme.asset("logo.png")).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        t = QLabel("Controle de Demandas do Colegiado")
        t.setStyleSheet("font-family:Georgia,serif; font-size:18pt;")
        topo.addWidget(logo)
        topo.addWidget(t, 1)
        v.addLayout(topo)
        resp = QLabel(f"Coordenação: {self.db.coordenador()}")
        resp.setStyleSheet(f"color:{theme.P['muted']};")
        v.addWidget(resp)
        v.addWidget(QLabel("Qual é o curso de graduação? Escolha um já cadastrado ou digite um novo nome."))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.lineEdit().setPlaceholderText("Ex.: Engenharia Civil")
        v.addWidget(self.combo)
        self.fill()
        imp = QPushButton("Importar backup…")
        imp.clicked.connect(self.importar)
        v.addLayout(botoes(self, "Entrar", [imp]))

    def fill(self):
        self.combo.clear()
        for c in self.db.cursos():
            self.combo.addItem(c["nome"])
        if not self.db.cursos():
            self.combo.setCurrentText("")

    def importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar backup", "", "Backup (*.json)")
        if not path:
            return
        if not confirm(self, "Importar substitui todos os dados atuais pelos do arquivo (uma cópia dos dados atuais é guardada antes). Continuar?"):
            return
        try:
            self.db.import_json(path)
            aviso(self, "Backup importado com sucesso.", "Pronto")
            self.fill()
        except Exception as e:
            aviso(self, f"Não foi possível importar: {e}", "Erro")

    def accept(self):
        nome = self.combo.currentText().strip()
        if not nome:
            return aviso(self, "Informe o nome do curso.")
        self.nome = nome
        self.curso_id = self.db.curso_id(nome)
        super().accept()


# ---------------------------------------------------------------- pessoa
class PessoaDialog(QDialog):
    def __init__(self, db, curso, pid=None, parent=None):
        super().__init__(parent)
        self.db, self.curso, self.pid = db, curso, pid
        p = db.one("SELECT * FROM pessoa WHERE id=?", (pid,)) if pid else {}
        self.setWindowTitle("Pessoa")
        self.setMinimumWidth(460)
        self.nome = QLineEdit(p.get("nome", ""))
        self.cat = QComboBox()
        self.cat.addItems(["Docente", "TAE", "Discente"])
        self.cat.setCurrentText(p.get("categoria", "Docente"))
        self.email = QLineEdit(p.get("email") or "")
        self.tel = QLineEdit(p.get("telefone") or "")
        self.membro = QCheckBox("É membro do Colegiado")
        self.membro.setChecked(bool(p.get("membro")))
        self.funcao = QComboBox()
        self.funcao.setEditable(True)
        self.funcao.addItems(["", "Presidente (Coordenador)", "Vice-coordenador", "Titular", "Suplente",
                              "Representante docente", "Representante TAE", "Representante discente"])
        self.funcao.setCurrentText(p.get("funcao") or "")
        self.ini, self.fim = OptDate(p.get("mandato_ini")), OptDate(p.get("mandato_fim"))
        self.ativo = QCheckBox("Ativo no curso")
        self.ativo.setChecked(bool(p.get("ativo", 1)))
        f = QFormLayout()
        for lbl, w in (("Nome*", self.nome), ("Categoria", self.cat), ("E-mail", self.email), ("Telefone", self.tel),
                       ("", self.membro), ("Função no colegiado", self.funcao), ("Mandato – início", self.ini),
                       ("Mandato – fim", self.fim), ("", self.ativo)):
            f.addRow(lbl, w)
        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addLayout(botoes(self))

    def accept(self):
        if not self.nome.text().strip():
            return aviso(self, "Informe o nome.")
        d = dict(nome=self.nome.text().strip(), categoria=self.cat.currentText(), email=self.email.text().strip(),
                 telefone=self.tel.text().strip(), membro=int(self.membro.isChecked()),
                 funcao=self.funcao.currentText().strip(), mandato_ini=self.ini.value(),
                 mandato_fim=self.fim.value(), ativo=int(self.ativo.isChecked()))
        self.db.salvar_pessoa(self.curso, d, self.pid)
        super().accept()


# ---------------------------------------------------------------- pauta futura
class PautaDialog(QDialog):
    def __init__(self, db, curso, pid=None, parent=None):
        super().__init__(parent)
        self.db, self.curso, self.pid = db, curso, pid
        p = db.one("SELECT * FROM pauta WHERE id=?", (pid,)) if pid else {}
        self.setWindowTitle("Ponto de pauta")
        self.setMinimumWidth(480)
        self.titulo = QLineEdit(p.get("titulo", ""))
        self.desc = QTextEdit()
        self.desc.setPlainText(p.get("descricao") or "")
        f = QFormLayout()
        f.addRow("Ponto de pauta*", self.titulo)
        f.addRow("Descrição", self.desc)
        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addLayout(botoes(self))

    def accept(self):
        if not self.titulo.text().strip():
            return aviso(self, "Informe o ponto de pauta.")
        self.db.salvar_pauta_futura(self.curso, self.titulo.text().strip(), self.desc.toPlainText().strip(), self.pid)
        super().accept()


class TrazerPautaDialog(QDialog):
    def __init__(self, db, curso, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trazer pontos da pauta futura")
        self.setMinimumSize(460, 360)
        self.rows = db.pautas_futuras(curso)
        self.lw = checklist([(r["titulo"], r["id"]) for r in self.rows])
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Marque os pontos que entrarão nesta reunião:" if self.rows else "Não há pontos na pauta futura."))
        v.addWidget(self.lw)
        v.addLayout(botoes(self, "Trazer"))

    def selecionados(self):
        ids = marcados(self.lw)
        return [r for r in self.rows if r["id"] in ids]


# ---------------------------------------------------------------- demanda
class DemandaDialog(QDialog):
    def __init__(self, db, curso, did=None, reuniao_id=None, prazo=None, parent=None):
        super().__init__(parent)
        self.db, self.curso, self.did = db, curso, did
        self.novos = []
        d = db.one("SELECT * FROM demanda WHERE id=?", (did,)) if did else {}
        self.setWindowTitle("Demanda")
        self.resize(800, 700)
        self.titulo = QLineEdit(d.get("titulo", ""))
        self.desc = QTextEdit()
        self.desc.setPlainText(d.get("descricao") or "")
        self.desc.setMaximumHeight(70)
        self.prazo = date_edit(d.get("prazo") or prazo or dt.date.today() + dt.timedelta(days=7))
        self.prio = QComboBox()
        self.prio.addItems(PRIORIDADES)
        self.prio.setCurrentText(d.get("prioridade", "Média"))
        self.status = QComboBox()
        self.status.addItems(STATUS)
        self.status.setCurrentText(d.get("status", "Aberta"))
        self.rec = QComboBox()
        self.rec.addItems(RECORRENCIAS)
        self.rec.setCurrentText(d.get("recorrencia") or "Nenhuma")
        self.reun = QComboBox()
        self.reun.addItem("Sem reunião (demanda avulsa)", None)
        rid = d.get("reuniao_id", reuniao_id)
        for r in db.reunioes(curso):
            self.reun.addItem(f"{br(r['data'])} – {r['tipo']}", r["id"])
        self.reun.setCurrentIndex(max(0, self.reun.findData(rid)))
        self.coord = QCheckBox("Coordenação do curso")
        self.coord.setChecked(bool(d.get("coord")))
        self.resp = checklist([(f"{p['nome']}  ({p['categoria']})", p["id"]) for p in db.pessoas(curso, ativos=True)],
                              db.resp_ids(did) if did else ())
        self.sel_pautas = set(db.pauta_ids(did)) if did else set()
        self.pautas = QListWidget()
        self.todas = QCheckBox("Mostrar pautas de todas as reuniões")
        self.todas.toggled.connect(self.fill_pautas)
        self.reun.currentIndexChanged.connect(self.fill_pautas)
        self.fill_pautas()
        self.hist = QListWidget()
        self.hist.setMaximumHeight(90)
        if did:
            for a in db.andamentos(did):
                self.hist.addItem(f"{br(a['data'])} – {a['texto']}")
        self.and_txt = QLineEdit()
        self.and_txt.setPlaceholderText("Ex.: cobrei em 10/11, aguardando resposta")
        b = QPushButton("Registrar andamento")
        b.clicked.connect(self.add_and)

        f = QFormLayout()
        f.addRow("Demanda*", self.titulo)
        f.addRow("Descrição", self.desc)
        row = QHBoxLayout()
        for lbl, w in (("Prazo", self.prazo), ("Prioridade", self.prio), ("Status", self.status), ("Repetir", self.rec)):
            row.addWidget(QLabel(lbl))
            row.addWidget(w)
        f.addRow(row)
        f.addRow("Reunião de origem", self.reun)
        cols = QHBoxLayout()
        a, c = QVBoxLayout(), QVBoxLayout()
        a.addWidget(QLabel("Responsáveis"))
        a.addWidget(self.coord)
        a.addWidget(self.resp)
        c.addWidget(QLabel("Pontos de pauta relacionados"))
        c.addWidget(self.todas)
        c.addWidget(self.pautas)
        cols.addLayout(a)
        cols.addLayout(c)
        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addLayout(cols, 1)
        v.addWidget(QLabel("Histórico de andamento"))
        v.addWidget(self.hist)
        h = QHBoxLayout()
        h.addWidget(self.and_txt, 1)
        h.addWidget(b)
        v.addLayout(h)
        extra = []
        if did:
            exc = QPushButton("Excluir demanda")
            exc.setProperty("danger", True)
            exc.clicked.connect(self._excluir)
            extra.append(exc)
        v.addLayout(botoes(self, extra=extra))

    def _excluir(self):
        if confirm(self, "Excluir esta demanda definitivamente? Esta ação não pode ser desfeita."):
            self.db.excluir_demanda(self.did)
            QDialog.accept(self)

    def _visiveis(self):
        return {self.pautas.item(i).data(UR) for i in range(self.pautas.count())}

    def fill_pautas(self):
        self.sel_pautas = (self.sel_pautas - self._visiveis()) | set(marcados(self.pautas))
        rid = self.reun.currentData()
        rows = self.db.q("SELECT p.*, r.data AS r_data FROM pauta p LEFT JOIN reuniao r ON r.id=p.reuniao_id "
                         "WHERE p.curso_id=? ORDER BY p.reuniao_id IS NULL, r.data DESC, p.ordem", (self.curso,))
        itens = []
        for p in sorted(rows, key=lambda p: p["reuniao_id"] != rid):
            if self.todas.isChecked() or p["reuniao_id"] in (rid, None) or p["id"] in self.sel_pautas:
                rot = f"[{br(p['r_data'])}] " if p["reuniao_id"] else "[Próxima pauta] "
                itens.append((rot + p["titulo"], p["id"]))
        novo = checklist(itens, self.sel_pautas)
        self.pautas.clear()
        for i in range(novo.count()):
            self.pautas.addItem(novo.takeItem(0))

    def add_and(self):
        t = self.and_txt.text().strip()
        if t:
            self.novos.append(t)
            self.hist.insertItem(0, f"{dt.date.today():%d/%m/%Y} – {t}")
            self.and_txt.clear()

    def accept(self):
        if not self.titulo.text().strip():
            return aviso(self, "Informe o título da demanda.")
        self.add_and()
        rec = self.rec.currentText()
        d = dict(titulo=self.titulo.text().strip(), descricao=self.desc.toPlainText().strip(), prazo=dstr(self.prazo),
                 prioridade=self.prio.currentText(), status=self.status.currentText(),
                 reuniao_id=self.reun.currentData(), coord=int(self.coord.isChecked()),
                 recorrencia="" if rec == "Nenhuma" else rec)
        pautas = (self.sel_pautas - self._visiveis()) | set(marcados(self.pautas))
        self.db.salvar_demanda(self.curso, d, marcados(self.resp), sorted(pautas), self.did, self.novos)
        super().accept()


# ---------------------------------------------------------------- reunião
class ReuniaoDialog(QDialog):
    def __init__(self, db, curso, curso_nome, rid=None, parent=None, data=None):
        super().__init__(parent)
        self.db, self.curso, self.curso_nome, self.rid = db, curso, curso_nome, rid
        r = db.one("SELECT * FROM reuniao WHERE id=?", (rid,)) if rid else {}
        self.setWindowTitle("Reunião do Colegiado")
        self.resize(840, 620)
        tabs = QTabWidget()
        # dados
        self.tipo = QComboBox()
        self.tipo.addItems(["Ordinária", "Extraordinária"])
        self.tipo.setCurrentText(r.get("tipo", "Ordinária"))
        self.data = date_edit(r.get("data") or data)
        self.hora = QTimeEdit(QTime.fromString(r.get("hora", "14:00"), "HH:mm"))
        self.hora.setDisplayFormat("HH:mm")
        self.local = QLineEdit(r.get("local") or "")
        self.status = QComboBox()
        self.status.addItems(["Agendada", "Realizada", "Cancelada"])
        self.status.setCurrentText(r.get("status", "Agendada"))
        self.obs = QTextEdit()
        self.obs.setPlainText(r.get("obs") or "")
        w = QWidget()
        f = QFormLayout(w)
        for lbl, x in (("Tipo", self.tipo), ("Data", self.data), ("Horário", self.hora), ("Local", self.local),
                       ("Situação", self.status), ("Observações (constam na ata)", self.obs)):
            f.addRow(lbl, x)
        tabs.addTab(w, "Dados")
        # pauta
        self.tp = QTableWidget(0, 2)
        self.tp.setHorizontalHeaderLabels(["Ponto de pauta", "Deliberação / encaminhamento"])
        self.tp.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tp.verticalHeader().hide()
        self.tp.setWordWrap(True)
        self.tp.itemChanged.connect(lambda *_: self.tp.resizeRowsToContents())
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(self.tp)
        h = QHBoxLayout()
        for txt, fn in (("+ Adicionar ponto", lambda: self.add_pauta(None, "Novo ponto", "")),
                        ("Trazer da pauta futura", self.trazer), ("Remover", self.rem_pauta),
                        ("↑", lambda: self.mover(-1)), ("↓", lambda: self.mover(1))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        tabs.addTab(w, "Pauta")
        # demandas
        self.ld = QListWidget()
        self.ld.itemDoubleClicked.connect(lambda *_: self.ed_dem())
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Demandas geradas nesta reunião (salve a reunião antes de criar demandas — isso é feito automaticamente)."))
        v.addWidget(self.ld)
        h = QHBoxLayout()
        for txt, fn in (("+ Nova demanda", self.nova_dem), ("Editar", self.ed_dem), ("Excluir", self.del_dem)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        tabs.addTab(w, "Demandas")
        # presença
        pres = db.presencas(rid) if rid else {}
        membros = db.pessoas(curso, so_membros=True, ativos=True)
        self.lp = checklist([(f"{p['nome']}  ({p['categoria']}{', ' + p['funcao'] if p['funcao'] else ''})", p["id"])
                             for p in membros], {k for k, vv in pres.items() if vv})
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Marque os membros presentes:" if membros else "Cadastre membros do Colegiado em Pessoas."))
        v.addWidget(self.lp)
        b = QPushButton("Marcar / desmarcar todos")
        b.clicked.connect(self.todos)
        v.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        tabs.addTab(w, "Presença")

        ata = QPushButton("Gerar ata (Word)")
        ata.clicked.connect(self.gerar_ata)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        exc = QPushButton("Excluir reunião")
        exc.setProperty("danger", True)
        exc.clicked.connect(self._excluir)
        lay.addLayout(botoes(self, extra=[ata, exc]))
        self.load_pautas()
        self.load_demandas()

    # pauta
    def add_pauta(self, pid, titulo, delib):
        r = self.tp.rowCount()
        self.tp.insertRow(r)
        a = QTableWidgetItem(titulo)
        a.setData(UR, pid)
        self.tp.setItem(r, 0, a)
        self.tp.setItem(r, 1, QTableWidgetItem(delib or ""))
        self.tp.resizeRowsToContents()

    def load_pautas(self):
        self.tp.blockSignals(True)
        self.tp.setRowCount(0)
        for p in (self.db.pautas_reuniao(self.rid) if self.rid else []):
            self.add_pauta(p["id"], p["titulo"], p["deliberacao"])
        self.tp.blockSignals(False)

    def _row(self, r):
        return (self.tp.item(r, 0).data(UR), self.tp.item(r, 0).text(), self.tp.item(r, 1).text())

    def _set(self, r, t):
        self.tp.item(r, 0).setData(UR, t[0])
        self.tp.item(r, 0).setText(t[1])
        self.tp.item(r, 1).setText(t[2])

    def mover(self, d):
        r = self.tp.currentRow()
        if r < 0 or not 0 <= r + d < self.tp.rowCount():
            return
        a, b = self._row(r), self._row(r + d)
        self._set(r, b)
        self._set(r + d, a)
        self.tp.setCurrentCell(r + d, 0)

    def rem_pauta(self):
        r = self.tp.currentRow()
        if r >= 0 and confirm(self, "Remover este ponto de pauta? Demandas ligadas a ele perdem o vínculo."):
            self.tp.removeRow(r)

    def trazer(self):
        dlg = TrazerPautaDialog(self.db, self.curso, self)
        if dlg.exec():
            for p in dlg.selecionados():
                self.add_pauta(p["id"], p["titulo"], p["deliberacao"] or "")

    # demandas
    def load_demandas(self):
        self.ld.clear()
        if not self.rid:
            return
        for d in self.db.q("SELECT * FROM demanda WHERE reuniao_id=? ORDER BY prazo", (self.rid,)):
            it = QListWidgetItem(f"{br(d['prazo'])} – {d['titulo']}  [{d['status']}]  {self.db.resp_texto(d)}")
            it.setData(UR, d["id"])
            self.ld.addItem(it)

    def nova_dem(self):
        if not self._save():
            return
        DemandaDialog(self.db, self.curso, reuniao_id=self.rid, parent=self).exec()
        self.load_demandas()

    def ed_dem(self):
        it = self.ld.currentItem()
        if it:
            DemandaDialog(self.db, self.curso, did=it.data(UR), parent=self).exec()
            self.load_demandas()

    def del_dem(self):
        it = self.ld.currentItem()
        if it and confirm(self, "Excluir esta demanda?"):
            self.db.excluir_demanda(it.data(UR))
            self.load_demandas()

    def todos(self):
        novo = UNC if all(self.lp.item(i).checkState() == CHK for i in range(self.lp.count())) else CHK
        for i in range(self.lp.count()):
            self.lp.item(i).setCheckState(novo)

    # salvar
    def _save(self):
        if not self.local.text().strip():
            aviso(self, "Informe o local da reunião (aba Dados).")
            return False
        d = dict(tipo=self.tipo.currentText(), data=dstr(self.data), hora=self.hora.time().toString("HH:mm"),
                 local=self.local.text().strip(), status=self.status.currentText(), obs=self.obs.toPlainText().strip())
        pautas = [self._row(r) for r in range(self.tp.rowCount()) if self._row(r)[1].strip()]
        pres = {self.lp.item(i).data(UR): self.lp.item(i).checkState() == CHK for i in range(self.lp.count())}
        self.rid = self.db.salvar_reuniao(self.curso, d, pautas, pres, self.rid)
        self.load_pautas()
        return True

    def gerar_ata(self):
        if not self._save():
            return
        nome = f"Ata_{self.data.date().toString('yyyy-MM-dd')}.docx"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar ata", nome, "Documento Word (*.docx)")
        if path:
            reports.gerar_ata(self.db, self.curso_nome, self.rid, path)
            abrir_arquivo(path)

    def _excluir(self):
        if not self.rid:
            return self.reject()
        if confirm(self, "Excluir esta reunião e seus pontos de pauta? As demandas ligadas a ela NÃO são apagadas "
                         "(passam a ser avulsas). Esta ação não pode ser desfeita."):
            self.db.excluir_reuniao(self.rid)
            QDialog.accept(self)

    def accept(self):
        if self._save():
            super().accept()
