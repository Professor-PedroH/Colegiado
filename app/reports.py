"""Ata em Word (.docx), relatório do período em PDF e relatório de demandas em Excel (.xlsx)."""
from xml.sax.saxutils import escape as esc

from .db import br, hoje, parse

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _lista(nomes):
    if not nomes:
        return ""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _coord(c):
    nome = ((c or {}).get("coordenador") or "").strip()
    trat = (c or {}).get("tratamento") or "Coordenador"
    return nome, trat


# ============================================================ ATA (Word)
def gerar_ata(db, curso_nome, rid, path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
    from docx.shared import Cm, Pt

    r = db.one("SELECT * FROM reuniao WHERE id=?", (rid,))
    d = parse(r["data"])
    coord, trat = _coord(db.curso(r["curso_id"]))
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

    num = f" Nº {r['numero']}/{d.year}" if r["numero"] else ""
    par(f"ATA{num} – REUNIÃO {r['tipo'].upper()} DO COLEGIADO DO CURSO DE {curso_nome.upper()}", True, AL.CENTER, 14)

    pres = db.q("SELECT p.nome, p.categoria, p.funcao, x.presente FROM presenca x JOIN pessoa p ON p.id=x.pessoa_id "
                "WHERE x.reuniao_id=? ORDER BY p.nome COLLATE NOCASE", (rid,))
    presentes = [x for x in pres if x["presente"] and x["nome"] != coord]
    ausentes = [x["nome"] for x in pres if not x["presente"] and x["nome"] != coord]
    presidencia = (f"sob a presidência {'da' if trat == 'Coordenadora' else 'do'} {trat} do Curso, {coord}"
                   if coord else "sob a presidência da Coordenação do Curso")
    abertura = (f"Aos {d.day} dias do mês de {MESES[d.month - 1]} de {d.year}, às {r['hora'].replace(':', 'h')}, "
                f"em {r['local']}, reuniu-se o Colegiado do Curso de {curso_nome}, {presidencia}")
    if presentes:
        abertura += ", com a presença dos membros: " + _lista([f"{x['nome']} ({x['categoria']})" for x in presentes])
    par(abertura + ".")
    if r.get("sei_convocacao"):
        par(f"A convocação foi realizada por meio do processo SEI nº {r['sei_convocacao']}.")
    if ausentes:
        par("Ausências: " + _lista(ausentes) + ".")
    if pres:
        n_pres = sum(1 for x in pres if x["presente"])
        ok = n_pres >= len(pres) // 2 + 1
        par(f"Verificou-se a presença de {n_pres} dos {len(pres)} membros do Colegiado, "
            f"{'havendo' if ok else 'não havendo'} quórum de maioria para deliberação.")

    pautas = db.pautas_reuniao(rid)
    par("ORDEM DO DIA E DELIBERAÇÕES", True, AL.LEFT)
    if not pautas:
        par("Não foram registrados pontos de pauta.")
    for i, p in enumerate(pautas, 1):
        par(f"{i}. {p['titulo']}", True, AL.LEFT, 2)
        if p["descricao"]:
            par(p["descricao"])
        par("Deliberação: " + (p["deliberacao"] or "sem deliberação registrada."))

    anex = db.anexos(rid)
    if anex:
        par("DOCUMENTOS ANEXOS", True, AL.LEFT)
        for a in anex:
            par("• " + a["nome"], al=AL.LEFT, depois=2)
        par("", depois=2)

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
    par(f"{coord} – {trat} do Curso (Presidente)" if coord else "Coordenação do Curso (Presidente)", al=AL.LEFT, depois=14)
    for x in presentes:
        par("_____________________________________", al=AL.LEFT, depois=0)
        par(f"{x['nome']} – {x['funcao'] or x['categoria']}", al=AL.LEFT, depois=14)
    doc.save(path)


# ============================================================ RELATÓRIO (PDF)
def gerar_relatorio_pdf(db, curso_id, ini, fim, path, opts=None):
    """ini/fim: datas ISO (AAAA-MM-DD)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    o = {"detalhar": True, "concluidas": True, "abertas": True, "pendencias": True, "presenca": True, **(opts or {})}
    c = db.curso(curso_id)
    nome = c["nome"]
    coord, trat = _coord(c)

    # ---- dados
    reunioes = db.q("SELECT * FROM reuniao WHERE curso_id=? AND data BETWEEN ? AND ? ORDER BY data, hora",
                    (curso_id, ini, fim))
    realizadas = [r for r in reunioes if r["status"] == "Realizada"]
    todas = db.demandas(curso_id, False) + db.demandas(curso_id, True)
    concl = sorted((d for d in todas if d["status"] == "Concluída" and d["concluida_em"] and ini <= d["concluida_em"] <= fim),
                   key=lambda d: d["concluida_em"])
    abertas = sorted((d for d in todas if (not d["criada_em"] or d["criada_em"] <= fim)
                      and (d["status"] != "Concluída" or (d["concluida_em"] and d["concluida_em"] > fim))),
                     key=lambda d: (d["prazo"] is None, d["prazo"] or ""))
    criadas = [d for d in todas if d["criada_em"] and ini <= d["criada_em"] <= fim]
    ref = min(parse(fim), hoje())
    atras = [d for d in abertas if d["prazo"] and parse(d["prazo"]) < ref]
    n_pautas = sum(len(db.pautas_reuniao(r["id"])) for r in realizadas)

    # ---- estilos
    TERRA, ESCURO, CINZA = colors.HexColor("#C96442"), colors.HexColor("#1F1E1D"), colors.HexColor("#83827D")
    VERM, VERDE = colors.HexColor("#B53333"), colors.HexColor("#4F7A4A")
    base = getSampleStyleSheet()["Normal"]
    cel = ParagraphStyle("cel", parent=base, fontName="Helvetica", fontSize=8.5, leading=10.5)
    est = {
        "": cel,
        "cab": ParagraphStyle("cab", parent=cel, fontName="Helvetica-Bold", textColor=colors.white),
        "late": ParagraphStyle("late", parent=cel, fontName="Helvetica-Bold", textColor=VERM),
        "ok": ParagraphStyle("ok", parent=cel, fontName="Helvetica-Bold", textColor=VERDE, alignment=1),
        "clate": ParagraphStyle("clate", parent=cel, fontName="Helvetica-Bold", textColor=VERM, alignment=1),
        "mut": ParagraphStyle("mut", parent=cel, textColor=CINZA, alignment=1),
        "c": ParagraphStyle("c", parent=cel, alignment=1),
    }
    txt = ParagraphStyle("txt", parent=cel, fontSize=9.5, leading=12.5, spaceAfter=3)
    h1 = ParagraphStyle("h1", fontName="Times-Bold", fontSize=20, leading=24, textColor=TERRA)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=ESCURO, spaceBefore=14, spaceAfter=6, keepWithNext=1)
    h3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=ESCURO, spaceBefore=8, spaceAfter=2, keepWithNext=1)
    meta = ParagraphStyle("meta", parent=txt, textColor=CINZA)

    pagesize = landscape(A4) if o["presenca"] and len(realizadas) > 7 else A4
    doc = SimpleDocTemplate(path, pagesize=pagesize, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title=f"Relatório – {nome}", author="Colegiado – Controle de Demandas")

    def P(t, s=""):
        return Paragraph(esc(str(t)).replace("\n", "<br/>"), est[s] if isinstance(s, str) else s)

    def tab(cab, linhas, larg, centro=()):
        data = [[P(h, "cab") for h in cab]]
        for l in linhas:
            data.append([P(*v) if isinstance(v, tuple) else P(v, "c" if i in centro else "") for i, v in enumerate(l)])
        t = Table(data, colWidths=[w * doc.width for w in larg], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TERRA), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D4C8")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF9F5")]),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    def titulo_ata(r):
        return f" · Ata nº {r['numero']}/{r['data'][:4]}" if r["numero"] else ""

    el = [Paragraph("Relatório do Colegiado", h1), Paragraph(esc(f"Curso de {nome}"), ParagraphStyle("sub", parent=txt, fontSize=13, leading=16)),
          Paragraph(esc(f"Período: {br(ini)} a {br(fim)}"), meta)]
    if coord:
        el.append(Paragraph(esc(f"{trat}: {coord}"), meta))
    el.append(Paragraph(esc(f"Emitido em {hoje():%d/%m/%Y}"), meta))

    # ---- 1. resumo
    el.append(Paragraph("1. Resumo do período", h2))
    resumo = [("Reuniões realizadas", len(realizadas)), ("Pontos de pauta tratados", n_pautas),
              ("Demandas criadas no período", len(criadas)), ("Demandas concluídas no período", len(concl)),
              (f"Demandas em aberto em {br(fim)}", len(abertas)), ("  das quais atrasadas", len(atras))]
    pend_status = len(reunioes) - len(realizadas)
    if pend_status:
        resumo.insert(1, ("Reuniões agendadas/canceladas no período", pend_status))
    rows = [[(l, ""), (str(v), "late" if l.strip().startswith("das quais") and v else "")] for l, v in resumo]
    t = Table([[P(*a), P(*b)] for a, b in rows], colWidths=[0.45 * doc.width, 0.12 * doc.width], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D4C8")), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    el.append(t)
    if any(not d["criada_em"] for d in todas):
        el.append(Paragraph("Obs.: demandas cadastradas antes do registro da data de criação são consideradas em aberto "
                            "se ainda não concluídas.", meta))

    # ---- 2. reuniões
    el.append(Paragraph("2. Reuniões do período", h2))
    if not reunioes:
        el.append(Paragraph("Nenhuma reunião no período.", txt))
    else:
        el.append(tab(["Data", "Hora", "Ata nº", "Tipo", "Local", "Situação", "SEI (convocação)"],
                      [[br(r["data"]), r["hora"], f"{r['numero']}/{r['data'][:4]}" if r["numero"] else "—", r["tipo"],
                        r["local"], r["status"], r["sei_convocacao"] or "—"] for r in reunioes],
                      [0.13, 0.07, 0.08, 0.15, 0.24, 0.13, 0.20]))
        if o["detalhar"]:
            for r in reunioes:
                el.append(Paragraph(esc(f"{br(r['data'])} – {r['hora']} · Reunião {r['tipo'].lower()}{titulo_ata(r)} · {r['status']}"), h3))
                for i, p in enumerate(db.pautas_reuniao(r["id"]), 1):
                    delib = p["deliberacao"] or "sem deliberação registrada"
                    el.append(Paragraph(f"<b>{i}. {esc(p['titulo'])}</b> — {esc(delib)}", txt))
                dems = db.q("SELECT * FROM demanda WHERE reuniao_id=? ORDER BY prazo", (r["id"],))
                if dems:
                    el.append(Paragraph("<b>Demandas geradas:</b> " + esc("; ".join(
                        f"{d['titulo']} (prazo {br(d['prazo'])}, {d['status'].lower()})" for d in dems)), txt))
                anex = db.anexos(r["id"])
                if anex:
                    el.append(Paragraph("<b>Documentos anexos:</b> " + esc("; ".join(a["nome"] for a in anex)), txt))

    # ---- 3. concluídas
    if o["concluidas"]:
        el.append(Paragraph("3. Demandas concluídas no período", h2))
        if not concl:
            el.append(Paragraph("Nenhuma demanda concluída no período.", txt))
        else:
            el.append(tab(["Concluída em", "Demanda", "Responsáveis", "Prazo", "SEI / ofício"],
                          [[br(d["concluida_em"]), d["titulo"], d["resp"] or "—", br(d["prazo"]), d["sei"] or "—"] for d in concl],
                          [0.12, 0.38, 0.25, 0.13, 0.12]))

    # ---- 4. em aberto
    if o["abertas"]:
        el.append(Paragraph(f"4. Demandas em aberto em {br(fim)}", h2))
        if not abertas:
            el.append(Paragraph("Nenhuma demanda em aberto.", txt))
        else:
            ids_atr = {d["id"] for d in atras}
            el.append(tab(["Prazo", "Prior.", "Status", "Demanda", "Responsáveis", "SEI / ofício"],
                          [[(br(d["prazo"]) or "—", "late" if d["id"] in ids_atr else ""), d["prioridade"], d["status"],
                            d["titulo"], d["resp"] or "—", d["sei"] or "—"] for d in abertas],
                          [0.12, 0.08, 0.15, 0.31, 0.22, 0.12]))
            if atras:
                el.append(Paragraph("Prazos em vermelho: demandas atrasadas.", meta))

    # ---- 5. pendências por responsável
    if o["pendencias"] and abertas:
        el.append(Paragraph("5. Pendências por responsável", h2))
        nomes = {p["id"]: p["nome"] for p in db.pessoas(curso_id)}
        grupos = {}
        for d in abertas:
            for chave in (["Coordenação"] if d["coord"] else []) + [nomes[i] for i in d["resp_ids"] if i in nomes]:
                grupos.setdefault(chave, []).append(d)
        ids_atr = {d["id"] for d in atras}
        for chave in sorted(grupos, key=lambda k: (k != "Coordenação", k.lower())):
            el.append(Paragraph(esc(f"{chave} ({len(grupos[chave])})"), h3))
            for d in grupos[chave]:
                s = "late" if d["id"] in ids_atr else ""
                el.append(P(f"• {d['titulo']} — prazo {br(d['prazo']) or 'sem prazo'}", s))
        if any(not d["resp_ids"] and not d["coord"] for d in abertas):
            el.append(Paragraph("Há demandas em aberto sem responsável definido.", meta))

    # ---- 6. presença
    if o["presenca"]:
        el.append(Paragraph("6. Controle de presença nas reuniões realizadas", h2))
        if not realizadas:
            el.append(Paragraph("Nenhuma reunião realizada no período.", txt))
        else:
            ids = [r["id"] for r in realizadas]
            pres = {(x["reuniao_id"], x["pessoa_id"]): x["presente"] for x in db.q(
                f"SELECT * FROM presenca WHERE reuniao_id IN ({','.join(map(str, ids))})")}
            pessoas = [p for p in db.pessoas(curso_id) if (p["membro"] and p["ativo"]) or any((i, p["id"]) in pres for i in ids)]
            linhas = []
            for p in pessoas:
                cel_ = []
                reg = []
                for i in ids:
                    if (i, p["id"]) in pres:
                        v = bool(pres[(i, p["id"])])
                        reg.append(v)
                        cel_.append(("P", "ok") if v else ("F", "clate"))
                    else:
                        cel_.append(("–", "mut"))
                freq = f"{sum(reg)}/{len(reg)} ({round(100 * sum(reg) / len(reg))}%)" if reg else "—"
                linhas.append([f"{p['nome']} ({p['categoria']})"] + cel_ + [(freq, "c")])
            tot, quo = [], []
            for i in ids:
                reg = [bool(v) for (rid, _), v in pres.items() if rid == i]
                tot.append((f"{sum(reg)}/{len(reg)}", "c") if reg else ("–", "mut"))
                quo.append(("Sim", "ok") if reg and sum(reg) >= len(reg) // 2 + 1 else (("Não", "clate") if reg else ("–", "mut")))
            linhas.append([("Presentes", "")] + tot + [""])
            linhas.append([("Quórum de maioria", "")] + quo + [""])
            n = len(ids)
            resto = 1 - 0.30 - 0.14
            larg = [0.30] + [resto / n] * n + [0.14]
            el.append(tab(["Membro"] + [f"{br(r['data'])[:5]}" for r in realizadas] + ["Frequência"], linhas, larg))
            el.append(Paragraph("P = presente · F = ausente · – = sem registro. Frequência calculada sobre as reuniões com registro.", meta))

    def rodape(cv, d):
        cv.saveState()
        cv.setFont("Helvetica", 8)
        cv.setFillColor(CINZA)
        cv.drawString(d.leftMargin, 1.0 * cm, f"Colegiado do Curso de {nome} – Relatório do período {br(ini)} a {br(fim)}")
        cv.drawRightString(d.pagesize[0] - d.rightMargin, 1.0 * cm, f"Página {d.page}")
        cv.restoreState()

    el.append(Spacer(1, 6))
    doc.build(el, onFirstPage=rodape, onLaterPages=rodape)


# ============================================================ EXCEL
def exportar_demandas(db, curso, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    cab = ["Prazo", "Prioridade", "Status", "Demanda", "Descrição", "Responsáveis", "Pauta(s)", "Reunião de origem",
           "Nº SEI / ofício", "Criada em", "Concluída em", "Repetição"]
    larg = [12, 12, 20, 40, 45, 32, 32, 16, 22, 12, 14, 12]
    for i, (nome, concl) in enumerate((("Em aberto", False), ("Concluídas", True))):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nome
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="C96442")
        for d in db.demandas(curso, concl):
            ws.append([parse(d["prazo"]), d["prioridade"], d["status"], d["titulo"], d["descricao"], d["resp"],
                       d["pautas"], parse(d["r_data"]), d["sei"], parse(d["criada_em"]), parse(d["concluida_em"]),
                       d["recorrencia"]])
            row = ws.max_row
            for col in (1, 8, 10, 11):
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
