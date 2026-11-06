"""Camada de dados (SQLite) – cursos, pessoas, reuniões, pautas, demandas, log e backup."""
import calendar
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

APP = "ColegiadoDemandas"
STATUS = ["Aberta", "Em andamento", "Aguardando terceiros", "Concluída"]
PRIORIDADES = ["Alta", "Média", "Baixa"]
RECORRENCIAS = ["Nenhuma", "Mensal", "Semestral", "Anual"]
TABLES = ["curso", "pessoa", "reuniao", "presenca", "pauta", "demanda",
          "demanda_pauta", "demanda_resp", "andamento", "log", "config"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS curso(id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS pessoa(id INTEGER PRIMARY KEY, curso_id INT, nome TEXT, categoria TEXT,
  email TEXT, telefone TEXT, membro INT DEFAULT 0, funcao TEXT, mandato_ini TEXT, mandato_fim TEXT, ativo INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS reuniao(id INTEGER PRIMARY KEY, curso_id INT, tipo TEXT, data TEXT, hora TEXT,
  local TEXT, status TEXT, obs TEXT);
CREATE TABLE IF NOT EXISTS presenca(reuniao_id INT, pessoa_id INT, presente INT, PRIMARY KEY(reuniao_id, pessoa_id));
CREATE TABLE IF NOT EXISTS pauta(id INTEGER PRIMARY KEY, curso_id INT, reuniao_id INT, titulo TEXT,
  descricao TEXT, deliberacao TEXT, ordem INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS demanda(id INTEGER PRIMARY KEY, curso_id INT, titulo TEXT, descricao TEXT, prazo TEXT,
  prioridade TEXT, status TEXT, reuniao_id INT, coord INT DEFAULT 0, recorrencia TEXT DEFAULT '', concluida_em TEXT);
CREATE TABLE IF NOT EXISTS demanda_pauta(demanda_id INT, pauta_id INT, PRIMARY KEY(demanda_id, pauta_id));
CREATE TABLE IF NOT EXISTS demanda_resp(demanda_id INT, pessoa_id INT, PRIMARY KEY(demanda_id, pessoa_id));
CREATE TABLE IF NOT EXISTS andamento(id INTEGER PRIMARY KEY, demanda_id INT, data TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts TEXT, acao TEXT, detalhe TEXT);
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
"""


# ---------- utilidades de data ----------
def hoje():
    return dt.date.today()


def iso(d):
    return d.isoformat() if d else None


def parse(s):
    return dt.date.fromisoformat(s) if s else None


def br(s):
    d = parse(s)
    return d.strftime("%d/%m/%Y") if d else ""


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def data_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    p = Path(base) / APP
    p.mkdir(parents=True, exist_ok=True)
    return p


def backup_dir():
    p = Path.home() / "Documents" / APP / "Backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


class DB:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "colegiado.db"
        self.dir = self.path.parent
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    # ---------- básicos ----------
    def q(self, sql, a=()):
        return [dict(r) for r in self.con.execute(sql, a).fetchall()]

    def one(self, sql, a=()):
        r = self.q(sql, a)
        return r[0] if r else None

    def x(self, sql, a=()):
        c = self.con.execute(sql, a)
        self.con.commit()
        return c.lastrowid

    def save(self, table, d, id=None):
        if id:
            sets = ",".join(f"{k}=?" for k in d)
            self.x(f"UPDATE {table} SET {sets} WHERE id=?", (*d.values(), id))
            return id
        cols = ",".join(d)
        return self.x(f"INSERT INTO {table}({cols}) VALUES({','.join('?' * len(d))})", tuple(d.values()))

    def log(self, acao, detalhe=""):
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.x("INSERT INTO log(ts,acao,detalhe) VALUES(?,?,?)", (ts, acao, detalhe))
        try:
            with open(self.dir / "historico.log", "a", encoding="utf-8") as f:
                f.write(f"{ts} | {acao} | {detalhe}\n")
        except OSError:
            pass

    def cfg(self, chave, padrao=None):
        r = self.one("SELECT valor FROM config WHERE chave=?", (chave,))
        return r["valor"] if r else padrao

    def set_cfg(self, chave, valor):
        self.x("INSERT OR REPLACE INTO config(chave,valor) VALUES(?,?)", (chave, valor))

    # ---------- cursos ----------
    def cursos(self):
        return self.q("SELECT * FROM curso ORDER BY nome")

    def curso_id(self, nome):
        r = self.one("SELECT id FROM curso WHERE nome=?", (nome,))
        if r:
            return r["id"]
        cid = self.x("INSERT INTO curso(nome) VALUES(?)", (nome,))
        self.log("Curso cadastrado", nome)
        return cid

    # ---------- pessoas ----------
    def pessoas(self, curso, so_membros=False, ativos=False):
        sql = "SELECT * FROM pessoa WHERE curso_id=?"
        if so_membros:
            sql += " AND membro=1"
        if ativos:
            sql += " AND ativo=1"
        return self.q(sql + " ORDER BY nome COLLATE NOCASE", (curso,))

    def salvar_pessoa(self, curso, d, id=None):
        pid = self.save("pessoa", {**d, "curso_id": curso}, id)
        self.log("Pessoa " + ("atualizada" if id else "cadastrada"), d["nome"])
        return pid

    def excluir_pessoa(self, pid):
        p = self.one("SELECT nome FROM pessoa WHERE id=?", (pid,))
        for t in ("demanda_resp", "presenca"):
            self.x(f"DELETE FROM {t} WHERE pessoa_id=?", (pid,))
        self.x("DELETE FROM pessoa WHERE id=?", (pid,))
        self.log("Pessoa excluída", p["nome"] if p else str(pid))

    # ---------- reuniões e pautas ----------
    def reunioes(self, curso):
        return self.q("SELECT * FROM reuniao WHERE curso_id=? ORDER BY data DESC, hora DESC", (curso,))

    def pautas_reuniao(self, rid):
        return self.q("SELECT * FROM pauta WHERE reuniao_id=? ORDER BY ordem, id", (rid,))

    def pautas_futuras(self, curso):
        return self.q("SELECT * FROM pauta WHERE curso_id=? AND reuniao_id IS NULL ORDER BY id", (curso,))

    def presencas(self, rid):
        return {r["pessoa_id"]: bool(r["presente"])
                for r in self.q("SELECT * FROM presenca WHERE reuniao_id=?", (rid,))}

    def salvar_reuniao(self, curso, d, pautas, presentes, id=None):
        rid = self.save("reuniao", {**d, "curso_id": curso}, id)
        manter = []
        for ordem, (pid, titulo, delib) in enumerate(pautas):
            manter.append(self.save("pauta", {"curso_id": curso, "reuniao_id": rid, "titulo": titulo,
                                              "deliberacao": delib, "ordem": ordem}, pid))
        for p in self.pautas_reuniao(rid):
            if p["id"] not in manter:
                self.excluir_pauta(p["id"], log=False)
        self.x("DELETE FROM presenca WHERE reuniao_id=?", (rid,))
        for pessoa, pres in presentes.items():
            self.x("INSERT INTO presenca VALUES(?,?,?)", (rid, pessoa, int(pres)))
        self.log("Reunião " + ("atualizada" if id else "criada"), f"{br(d['data'])} {d['hora']} – {d['tipo']}")
        return rid

    def excluir_reuniao(self, rid):
        r = self.one("SELECT data FROM reuniao WHERE id=?", (rid,))
        for p in self.pautas_reuniao(rid):
            self.excluir_pauta(p["id"], log=False)
        self.x("DELETE FROM presenca WHERE reuniao_id=?", (rid,))
        self.x("UPDATE demanda SET reuniao_id=NULL WHERE reuniao_id=?", (rid,))
        self.x("DELETE FROM reuniao WHERE id=?", (rid,))
        self.log("Reunião excluída", br(r["data"]) if r else str(rid))

    def salvar_pauta_futura(self, curso, titulo, descricao, id=None):
        d = {"titulo": titulo, "descricao": descricao}
        if not id:
            d.update(curso_id=curso, reuniao_id=None)
        pid = self.save("pauta", d, id)
        self.log("Próxima pauta " + ("atualizada" if id else "criada"), titulo)
        return pid

    def excluir_pauta(self, pid, log=True):
        self.x("DELETE FROM demanda_pauta WHERE pauta_id=?", (pid,))
        self.x("DELETE FROM pauta WHERE id=?", (pid,))
        if log:
            self.log("Pauta excluída", str(pid))

    # ---------- demandas ----------
    def resp_ids(self, did):
        return [r["pessoa_id"] for r in self.q("SELECT pessoa_id FROM demanda_resp WHERE demanda_id=?", (did,))]

    def pauta_ids(self, did):
        return [r["pauta_id"] for r in self.q("SELECT pauta_id FROM demanda_pauta WHERE demanda_id=?", (did,))]

    def resp_texto(self, d):
        nomes = ["Coordenação"] if d["coord"] else []
        nomes += [r["nome"] for r in self.q(
            "SELECT p.nome FROM demanda_resp x JOIN pessoa p ON p.id=x.pessoa_id "
            "WHERE x.demanda_id=? ORDER BY p.nome COLLATE NOCASE", (d["id"],))]
        return ", ".join(nomes)

    def demandas(self, curso, concluidas=False):
        op = "=" if concluidas else "!="
        ordem = "d.concluida_em DESC" if concluidas else "d.prazo, CASE d.prioridade WHEN 'Alta' THEN 0 WHEN 'Média' THEN 1 ELSE 2 END"
        rows = self.q(f"SELECT d.*, r.data AS r_data FROM demanda d LEFT JOIN reuniao r ON r.id=d.reuniao_id "
                      f"WHERE d.curso_id=? AND d.status{op}'Concluída' ORDER BY {ordem}", (curso,))
        for r in rows:
            r["resp"] = self.resp_texto(r)
            r["resp_ids"] = self.resp_ids(r["id"])
            r["pautas"] = self.pautas_txt(r["id"])
        return rows

    def pautas_txt(self, did):
        return "; ".join(r["titulo"] for r in self.q(
            "SELECT p.titulo FROM demanda_pauta x JOIN pauta p ON p.id=x.pauta_id WHERE x.demanda_id=? ORDER BY p.id", (did,)))

    def andamentos(self, did):
        return self.q("SELECT * FROM andamento WHERE demanda_id=? ORDER BY data DESC, id DESC", (did,))

    def salvar_demanda(self, curso, d, resp_ids, pauta_ids, id=None, andamentos=()):
        antes = self.one("SELECT status FROM demanda WHERE id=?", (id,)) if id else None
        concluindo = d["status"] == "Concluída" and (not antes or antes["status"] != "Concluída")
        d = {**d, "curso_id": curso}
        if concluindo:
            d["concluida_em"] = iso(hoje())
        elif d["status"] != "Concluída":
            d["concluida_em"] = None
        did = self.save("demanda", d, id)
        self.x("DELETE FROM demanda_resp WHERE demanda_id=?", (did,))
        self.x("DELETE FROM demanda_pauta WHERE demanda_id=?", (did,))
        for p in resp_ids:
            self.x("INSERT INTO demanda_resp VALUES(?,?)", (did, p))
        for p in pauta_ids:
            self.x("INSERT INTO demanda_pauta VALUES(?,?)", (did, p))
        for texto in andamentos:
            self.x("INSERT INTO andamento(demanda_id,data,texto) VALUES(?,?,?)", (did, iso(hoje()), texto))
        self.log("Demanda " + ("atualizada" if id else "criada"), d["titulo"])
        if concluindo:
            self._recorrer(did)
        return did

    def marcar(self, did, concluida):
        d = self.one("SELECT titulo FROM demanda WHERE id=?", (did,))
        if concluida:
            self.x("UPDATE demanda SET status='Concluída', concluida_em=? WHERE id=?", (iso(hoje()), did))
            self.log("Demanda concluída", d["titulo"])
            self._recorrer(did)
        else:
            self.x("UPDATE demanda SET status='Aberta', concluida_em=NULL WHERE id=?", (did,))
            self.log("Demanda reaberta", d["titulo"])

    def _recorrer(self, did):
        d = self.one("SELECT * FROM demanda WHERE id=?", (did,))
        n = {"Mensal": 1, "Semestral": 6, "Anual": 12}.get(d["recorrencia"])
        if not n or not d["prazo"]:
            return
        prazo = iso(add_months(parse(d["prazo"]), n))
        if self.one("SELECT id FROM demanda WHERE curso_id=? AND titulo=? AND prazo=? AND status!='Concluída'",
                    (d["curso_id"], d["titulo"], prazo)):
            return
        novo = {k: d[k] for k in ("curso_id", "titulo", "descricao", "prioridade", "reuniao_id", "coord", "recorrencia")}
        novo.update(status="Aberta", prazo=prazo)
        nid = self.save("demanda", novo)
        for p in self.resp_ids(did):
            self.x("INSERT INTO demanda_resp VALUES(?,?)", (nid, p))
        self.log("Demanda recorrente gerada", f"{d['titulo']} – {br(prazo)}")

    def excluir_demanda(self, did):
        d = self.one("SELECT titulo FROM demanda WHERE id=?", (did,))
        for t in ("demanda_resp", "demanda_pauta", "andamento"):
            self.x(f"DELETE FROM {t} WHERE demanda_id=?", (did,))
        self.x("DELETE FROM demanda WHERE id=?", (did,))
        self.log("Demanda excluída", d["titulo"] if d else str(did))

    # ---------- backup ----------
    def export_json(self, path):
        data = {"app": APP, "versao": 1, "exportado_em": dt.datetime.now().isoformat(timespec="seconds"),
                "tabelas": {t: self.q(f"SELECT * FROM {t}") for t in TABLES}}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def auto_backup(self, tag="auto"):
        pasta = backup_dir()
        self.export_json(pasta / f"backup_{tag}_{dt.datetime.now():%Y%m%d_%H%M%S}.json")
        for f in sorted(pasta.glob(f"backup_{tag}_*.json"))[:-20]:
            f.unlink()

    def import_json(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("app") != APP or "tabelas" not in data:
            raise ValueError("Este arquivo não é um backup válido do programa.")
        self.auto_backup("antes_de_importar")
        try:
            for t in TABLES:
                self.con.execute(f"DELETE FROM {t}")
            for t in TABLES:
                for row in data["tabelas"].get(t, []):
                    cols = list(row)
                    self.con.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                     [row[c] for c in cols])
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise
        self.log("Backup importado", Path(path).name)

    def historico(self, limite=500):
        return self.q("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limite,))
