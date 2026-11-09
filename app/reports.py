"""Ata em Word (.docx) e relatório de demandas em Excel (.xlsx)."""
from .db import br, parse

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _lista(nomes):
    if not nomes:
        return ""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def gerar_ata(db, curso_nome, rid, path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
    from docx.shared import Cm, Pt

    r = db.one("SELECT * FROM reuniao WHERE id=?", (rid,))
    d = parse(r["data"])
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.5)
        s.top_margin = s.bottom_margin = Cm(2.5)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Times New Roman", Pt(12)

    def par(txt="", bold=False, al=AL.JUSTIFY, depois=6):
        p = doc.add_paragraph()
        p.add_run(txt).bold = bold
        p.alignment = al
        p.paragraph_format.space_after = Pt(depois)
        return p

    par(f"ATA DE REUNIÃO {r['tipo'].upper()} DO COLEGIADO DO CURSO DE {curso_nome.upper()}", True, AL.CENTER, 14)

    pres = db.q("SELECT p.nome, p.categoria, p.funcao, x.presente FROM presenca x JOIN pessoa p ON p.id=x.pessoa_id "
                "WHERE x.reuniao_id=? ORDER BY p.nome COLLATE NOCASE", (rid,))
    coord = db.coordenador()
    presentes = [x for x in pres if x["presente"] and x["nome"] != coord]
    ausentes = [x["nome"] for x in pres if not x["presente"] and x["nome"] != coord]
    hora = r["hora"].replace(":", "h")
    abertura = (f"Aos {d.day} dias do mês de {MESES[d.month - 1]} de {d.year}, às {hora}, em {r['local']}, "
                f"reuniu-se o Colegiado do Curso de {curso_nome}, sob a presidência do Coordenador do Curso, {coord}")
    if presentes:
        abertura += ", com a presença dos membros: " + _lista([f"{x['nome']} ({x['categoria']})" for x in presentes])
    par(abertura + ".")
    if ausentes:
        par("Ausências: " + _lista(ausentes) + ".")

    pautas = db.pautas_reuniao(rid)
    par("ORDEM DO DIA E DELIBERAÇÕES", True, AL.LEFT)
    if not pautas:
        par("Não foram registrados pontos de pauta.")
    for i, p in enumerate(pautas, 1):
        par(f"{i}. {p['titulo']}", True, AL.LEFT, 2)
        if p["descricao"]:
            par(p["descricao"])
        par("Deliberação: " + (p["deliberacao"] or "sem deliberação registrada."))

    dems = db.q("SELECT * FROM demanda WHERE reuniao_id=? ORDER BY prazo", (rid,))
    if dems:
        par("ENCAMINHAMENTOS", True, AL.LEFT)
        t = doc.add_table(rows=1, cols=4)
        t.style = "Table Grid"
        for c, h in zip(t.rows[0].cells, ("Demanda", "Responsável(is)", "Prazo", "Pauta")):
            c.text = ""
            c.paragraphs[0].add_run(h).bold = True
        for x in dems:
            cells = t.add_row().cells
            for c, v in zip(cells, (x["titulo"], db.resp_texto(x), br(x["prazo"]), db.pautas_txt(x["id"]))):
                c.text = v
        doc.add_paragraph()
    if r["obs"]:
        par("OBSERVAÇÕES", True, AL.LEFT)
        par(r["obs"])
    par("Nada mais havendo a tratar, a reunião foi encerrada, e eu, ______________________, lavrei a presente ata, "
        "que, após lida e aprovada, será assinada pelos presentes.")
    par("")
    par("_____________________________________", al=AL.LEFT, depois=0)
    par(f"{coord} – Coordenador do Curso (Presidente)", al=AL.LEFT, depois=14)
    if presentes:
        for x in presentes:
            par("_____________________________________", al=AL.LEFT, depois=0)
            par(f"{x['nome']} – {x['funcao'] or x['categoria']}", al=AL.LEFT, depois=14)
    doc.save(path)


def exportar_demandas(db, curso, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    cab = ["Prazo", "Prioridade", "Status", "Demanda", "Descrição", "Responsáveis", "Pauta(s)",
           "Reunião de origem", "Concluída em", "Repetição"]
    larg = [12, 12, 20, 40, 45, 32, 32, 16, 14, 12]
    from .db import hoje
    for i, (nome, concl) in enumerate((("Em aberto", False), ("Concluídas", True))):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nome
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="C96442")
        for d in db.demandas(curso, concl):
            ws.append([parse(d["prazo"]), d["prioridade"], d["status"], d["titulo"], d["descricao"], d["resp"],
                       d["pautas"], parse(d["r_data"]), parse(d["concluida_em"]), d["recorrencia"]])
            row = ws.max_row
            for col in (1, 8, 9):
                ws.cell(row, col).number_format = "DD/MM/YYYY"
            if not concl and d["prazo"] and parse(d["prazo"]) < hoje():
                for c in ws[row]:
                    c.fill = PatternFill("solid", fgColor="F6DEDA")
        for n, w in enumerate(larg, 1):
            ws.column_dimensions[get_column_letter(n)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.save(path)
