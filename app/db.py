"""Camada de dados (SQLite) – cursos, pessoas, reuniões, pautas, demandas, anexos, log e backup."""
import calendar
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import uuid
import zipfile
from pathlib import Path

APP = "ColegiadoDemandas"
STATUS = ["Aberta", "Em andamento", "Aguardando terceiros", "Concluída"]
PRIORIDADES = ["Alta", "Média", "Baixa"]
RECORRENCIAS = ["Nenhuma", "Mensal", "Semestral", "Anual"]
TABLES = ["curso", "pessoa", "reuniao", "presenca", "pauta", "demanda",
          "demanda_pauta", "demanda_resp", "andamento", "anexo", "log", "config"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS curso(id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL,
  coordenador TEXT DEFAULT '', tratamento TEXT DEFAULT 'Coordenador');
CREATE TABLE IF NOT EXISTS pessoa(id INTEGER PRIMARY KEY, curso_id INT, nome TEXT, categoria TEXT,
  email TEXT, telefone TEXT, membro INT DEFAULT 0, funcao TEXT, mandato_ini TEXT, mandato_fim TEXT, ativo INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS reuniao(id INTEGER PRIMARY KEY, curso_id INT, tipo TEXT, data TEXT, hora TEXT,
  local TEXT, status TEXT, obs TEXT, numero INT, sei_convocacao TEXT);
CREATE TABLE IF NOT EXISTS presenca(reuniao_id INT, pessoa_id INT, presente INT, PRIMARY KEY(reuniao_id, pessoa_id));
CREATE TABLE IF NOT EXISTS pauta(id INTEGER PRIMARY KEY, curso_id INT, reuniao_id INT, titulo TEXT,
  descricao TEXT, deliberacao TEXT, ordem INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS demanda(id INTEGER PRIMARY KEY, curso_id INT, titulo TEXT, descricao TEXT, prazo TEXT,
  prioridade TEXT, status TEXT, reuniao_id INT, coord INT DEFAULT 0, recorrencia TEXT DEFAULT '', concluida_em TEXT,
  criada_em TEXT, sei TEXT);
CREATE TABLE IF NOT EXISTS demanda_pauta(demanda_id INT, pauta_id INT, PRIMARY KEY(demanda_id, pauta_id));
CREATE TABLE IF NOT EXISTS demanda_resp(demanda_id INT, pessoa_id INT, PRIMARY KEY(demanda_id, pessoa_id));
CREATE TABLE IF NOT EXISTS andamento(id INTEGER PRIMARY KEY, demanda_id INT, data TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS anexo(id INTEGER PRIMARY KEY, reuniao_id INT, nome TEXT, arquivo TEXT, tamanho INT, adicionado_em TEXT);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts TEXT, acao TEXT, detalhe TEXT);
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
"""
# colunas acrescentadas depois da versão 1.0 (migração de bancos antigos)
NOVAS = {"curso": [("coordenador", "TEXT DEFAULT ''"), ("tratamento", "TEXT DEFAULT 'Coordenador'")],
         "reuniao": [("numero", "INT"), ("sei_convocacao", "TEXT")],
         "demanda": [("criada_em", "TEXT"), ("sei", "TEXT")]}


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
        self.anexos_dir = self.dir / "anexos"
        self.anexos_dir.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrar()

    def _migrar(self):
        for t, cols in NOVAS.items():
            ex = self._cols(t)
            for nome, tipo in cols:
                if nome not in ex:
                    self.con.execute(f"ALTER TABLE {t} ADD COLUMN {nome} {tipo}")
        self.con.commit()

    def _cols(self, t):
        return {r["name"] for r in self.con.execute(f"PRAGMA table_info({t})").fetchall()}

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
        return self.q("SELECT * FROM curso ORDER BY nome COLLATE NOCASE")

    def curso(self, cid):
        return self.one("SELECT * FROM curso WHERE id=?", (cid,))

    def criar_curso(self, nome):
        cid = self.x("INSERT INTO curso(nome) VALUES(?)", (nome,))
        self.log("Curso cadastrado", nome)
        return cid

    def curso_id(self, nome):
        r = self.one("SELECT id FROM curso WHERE nome=?", (nome,))
        return r["id"] if r else self.criar_curso(nome)

    def salvar_curso_dados(self, cid, nome, coordenador, tratamento):
        self.x("UPDATE curso SET nome=?, coordenador=?, tratamento=? WHERE id=?", (nome, coordenador, tratamento, cid))
        self.log("Dados do curso atualizados", nome)

    def excluir_curso(self, cid):
        c = self.curso(cid)
        if not c:
            return
        self.auto_backup("antes_de_excluir_curso")
        arquivos = [a["arquivo"] for a in self.q(
            "SELECT arquivo FROM anexo WHERE reuniao_id IN (SELECT id FROM reuniao WHERE curso_id=?)", (cid,))]
        R, D = "SELECT id FROM reuniao WHERE curso_id=?", "SELECT id FROM demanda WHERE curso_id=?"
        for t in ("demanda_resp", "demanda_pauta", "andamento"):
            self.con.execute(f"DELETE FROM {t} WHERE demanda_id IN ({D})", (cid,))
        for t in ("presenca", "anexo"):
            self.con.execute(f"DELETE FROM {t} WHERE reuniao_id IN ({R})", (cid,))
        for t in ("pauta", "demanda", "reuniao", "pessoa"):
            self.con.execute(f"DELETE FROM {t} WHERE curso_id=?", (cid,))
        self.con.execute("DELETE FROM curso WHERE id=?", (cid,))
        self.con.commit()
        for a in arquivos:
            self._apagar_se_orfao(a)
        self.log("Curso excluído", c["nome"])

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

    def membros_mandato(self, curso, dias=30):
        lim = iso(hoje() + dt.timedelta(days=dias))
        return self.q("SELECT * FROM pessoa WHERE curso_id=? AND membro=1 AND ativo=1 AND mandato_fim IS NOT NULL "
                      "AND mandato_fim<=? ORDER BY mandato_fim", (curso, lim))

    # ---------- reuniões, pautas e anexos ----------
    def reunioes(self, curso):
        return self.q("SELECT * FROM reuniao WHERE curso_id=? ORDER BY data DESC, hora DESC", (curso,))

    def reunioes_sem_situacao(self, curso):
        return self.q("SELECT * FROM reuniao WHERE curso_id=? AND status='Agendada' AND data<? ORDER BY data",
                      (curso, iso(hoje())))

    def proximo_numero(self, curso, ano):
        r = self.one("SELECT MAX(numero) m FROM reuniao WHERE curso_id=? AND substr(data,1,4)=?", (curso, str(ano)))
        return (r["m"] or 0) + 1

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
        for a in self.anexos(rid):
            self.remover_anexo(a["id"], log=False)
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

    # anexos (documentos da reunião)
    def anexos(self, rid):
        return self.q("SELECT * FROM anexo WHERE reuniao_id=? ORDER BY id", (rid,))

    def caminho_anexo(self, a):
        return self.anexos_dir / a["arquivo"]

    def anexar(self, rid, origem):
        origem = Path(origem)
        seguro = re.sub(r"[^\w.\- ()]", "_", origem.name)[:100] or "documento"
        rel = f"{uuid.uuid4().hex}/{seguro}"
        destino = self.anexos_dir / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
        aid = self.save("anexo", {"reuniao_id": rid, "nome": origem.name, "arquivo": rel,
                                  "tamanho": destino.stat().st_size, "adicionado_em": iso(hoje())})
        self.log("Documento anexado à reunião", origem.name)
        return aid

    def remover_anexo(self, aid, log=True):
        a = self.one("SELECT * FROM anexo WHERE id=?", (aid,))
        if not a:
            return
        self.x("DELETE FROM anexo WHERE id=?", (aid,))
        self._apagar_se_orfao(a["arquivo"])
        if log:
            self.log("Documento removido da reunião", a["nome"])

    def _apagar_se_orfao(self, arquivo):
        if self.one("SELECT id FROM anexo WHERE arquivo=?", (arquivo,)):
            return
        f = self.anexos_dir / arquivo
        try:
            f.unlink(missing_ok=True)
            if f.parent != self.anexos_dir and not any(f.parent.iterdir()):
                f.parent.rmdir()
        except OSError:
            pass

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
        if not id:
            d["criada_em"] = iso(hoje())
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
        novo.update(status="Aberta", prazo=prazo, criada_em=iso(hoje()))
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

    # ---------- backup (arquivo .zip com dados.json + anexos/) ----------
    def export_backup(self, path, curso_id=None):
        if curso_id is None:
            tabelas, escopo = {t: self.q(f"SELECT * FROM {t}") for t in TABLES}, "tudo"
        else:
            c = (curso_id,)
            R, D = "SELECT id FROM reuniao WHERE curso_id=?", "SELECT id FROM demanda WHERE curso_id=?"
            tabelas, escopo = {"curso": self.q("SELECT * FROM curso WHERE id=?", c)}, "curso"
            for t in ("pessoa", "reuniao", "pauta", "demanda"):
                tabelas[t] = self.q(f"SELECT * FROM {t} WHERE curso_id=?", c)
            for t in ("presenca", "anexo"):
                tabelas[t] = self.q(f"SELECT * FROM {t} WHERE reuniao_id IN ({R})", c)
            for t in ("demanda_pauta", "demanda_resp", "andamento"):
                tabelas[t] = self.q(f"SELECT * FROM {t} WHERE demanda_id IN ({D})", c)
        dados = {"app": APP, "versao": 2, "escopo": escopo, "exportado_em": dt.datetime.now().isoformat(timespec="seconds"),
                 "tabelas": tabelas}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("dados.json", json.dumps(dados, ensure_ascii=False, indent=1))
            for a in tabelas["anexo"]:
                f = self.anexos_dir / a["arquivo"]
                if f.exists():
                    z.write(f, "anexos/" + a["arquivo"])

    def auto_backup(self, tag="auto", manter=10):
        pasta = backup_dir()
        self.export_backup(pasta / f"backup_{tag}_{dt.datetime.now():%Y%m%d_%H%M%S}.zip")
        for f in sorted(pasta.glob(f"backup_{tag}_*.zip"))[:-manter]:
            f.unlink()

    def ler_backup(self, path):
        path = Path(path)
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as z:
                    data = json.loads(z.read("dados.json").decode("utf-8"))
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, KeyError, ValueError):
            raise ValueError("Este arquivo não é um backup válido do programa.")
        if not isinstance(data, dict) or data.get("app") != APP or "tabelas" not in data:
            raise ValueError("Este arquivo não é um backup válido do programa.")
        data.setdefault("escopo", "tudo")
        return data

    def _extrair_anexos(self, path):
        if not zipfile.is_zipfile(path):
            return
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                partes = Path(n).parts
                if len(partes) >= 2 and partes[0] == "anexos" and not n.endswith("/") and ".." not in partes:
                    dest = self.anexos_dir.joinpath(*partes[1:])
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(n))

    def _limpar_orfaos(self):
        usados = {a["arquivo"] for a in self.q("SELECT arquivo FROM anexo")}
        for f in list(self.anexos_dir.rglob("*")):
            if f.is_file() and f.relative_to(self.anexos_dir).as_posix() not in usados:
                f.unlink()
        for d in sorted(self.anexos_dir.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    def import_tudo(self, path):
        data = self.ler_backup(path)
        if data["escopo"] != "tudo":
            raise ValueError("Este arquivo contém um único curso; use a importação de curso.")
        self.auto_backup("antes_de_importar")
        try:
            for t in TABLES:
                self.con.execute(f"DELETE FROM {t}")
            for t in TABLES:
                cols = self._cols(t)
                for row in data["tabelas"].get(t, []):
                    d = {k: v for k, v in row.items() if k in cols}
                    self.con.execute(f"INSERT INTO {t}({','.join(d)}) VALUES({','.join('?' * len(d))})", list(d.values()))
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise
        self._extrair_anexos(path)
        self._limpar_orfaos()
        self.log("Backup completo importado", Path(path).name)

    def _ins(self, tabela, row, **sobre):
        cols = self._cols(tabela)
        d = {k: v for k, v in row.items() if k in cols and k != "id"}
        d.update(sobre)
        c = self.con.execute(f"INSERT INTO {tabela}({','.join(d)}) VALUES({','.join('?' * len(d))})", list(d.values()))
        return c.lastrowid

    def import_curso(self, path, substituir=False):
        data = self.ler_backup(path)
        if data["escopo"] != "curso":
            raise ValueError("Este arquivo é um backup completo, não de um único curso.")
        t = data["tabelas"]
        c = t["curso"][0]
        ex = self.one("SELECT id FROM curso WHERE nome=?", (c["nome"],))
        if ex:
            if not substituir:
                raise ValueError("Já existe um curso com este nome.")
            self.excluir_curso(ex["id"])
        else:
            self.auto_backup("antes_de_importar_curso")
        try:
            cid = self._ins("curso", c)
            pm = {r["id"]: self._ins("pessoa", r, curso_id=cid) for r in t.get("pessoa", [])}
            rm = {r["id"]: self._ins("reuniao", r, curso_id=cid) for r in t.get("reuniao", [])}
            gm = {r["id"]: self._ins("pauta", r, curso_id=cid, reuniao_id=rm.get(r["reuniao_id"])) for r in t.get("pauta", [])}
            dm = {r["id"]: self._ins("demanda", r, curso_id=cid, reuniao_id=rm.get(r["reuniao_id"])) for r in t.get("demanda", [])}
            for r in t.get("presenca", []):
                if r["reuniao_id"] in rm and r["pessoa_id"] in pm:
                    self.con.execute("INSERT INTO presenca VALUES(?,?,?)", (rm[r["reuniao_id"]], pm[r["pessoa_id"]], r["presente"]))
            for r in t.get("demanda_pauta", []):
                if r["demanda_id"] in dm and r["pauta_id"] in gm:
                    self.con.execute("INSERT INTO demanda_pauta VALUES(?,?)", (dm[r["demanda_id"]], gm[r["pauta_id"]]))
            for r in t.get("demanda_resp", []):
                if r["demanda_id"] in dm and r["pessoa_id"] in pm:
                    self.con.execute("INSERT INTO demanda_resp VALUES(?,?)", (dm[r["demanda_id"]], pm[r["pessoa_id"]]))
            for r in t.get("andamento", []):
                if r["demanda_id"] in dm:
                    self._ins("andamento", r, demanda_id=dm[r["demanda_id"]])
            for r in t.get("anexo", []):
                if r["reuniao_id"] in rm:
                    self._ins("anexo", r, reuniao_id=rm[r["reuniao_id"]])
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise
        self._extrair_anexos(path)
        self.log("Curso importado", c["nome"])
        return cid

    def historico(self, limite=500):
        return self.q("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limite,))
