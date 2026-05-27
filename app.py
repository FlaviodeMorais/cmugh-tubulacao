import base64
import io
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List

import pandas as pd
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
from PIL import Image

import streamlit as st

DB_FILE = Path("cm_saas.db")


@dataclass
class RegistroCM:
    id: int
    tenant: str
    data_registro: str
    obra: str
    frente_servico: str
    disciplina: str
    atividade: str
    equipe: str
    fiscal: str
    status: str
    impacto_rdo: str
    observacoes: str
    evidencias: str = ""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registros_cm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL,
                data_registro TEXT NOT NULL,
                obra TEXT NOT NULL,
                frente_servico TEXT NOT NULL,
                disciplina TEXT NOT NULL,
                atividade TEXT NOT NULL,
                equipe TEXT,
                fiscal TEXT NOT NULL,
                status TEXT NOT NULL,
                impacto_rdo TEXT NOT NULL,
                observacoes TEXT,
                evidencias TEXT DEFAULT ''
            )
            """
        )
        try:
            conn.execute("ALTER TABLE registros_cm ADD COLUMN evidencias TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


def carregar_lista(tenant: str) -> List[RegistroCM]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM registros_cm WHERE tenant = ? ORDER BY id DESC", (tenant,)
        ).fetchall()
    return [RegistroCM(**dict(r)) for r in rows]


THUMB_SIZE = 200


def img_thumb(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    m = min(w, h)
    img = img.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
    img = img.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def fmt_data(iso: str) -> str:
    try:
        a, m, d = iso.split("-")
        return f"{d}/{m}/{a}"
    except Exception:
        return iso


def para_exibicao(registros: List[RegistroCM]) -> list:
    rows = []
    for r in registros:
        d = asdict(r)
        d["data_registro"] = fmt_data(d["data_registro"])
        try:
            n = len(json.loads(d.get("evidencias") or "[]"))
        except Exception:
            n = 0
        d["evidencias"] = f"{n} foto(s)" if n else ""
        rows.append(d)
    return rows


def exibir_cards(registros: List[RegistroCM]) -> None:
    for r in registros:
        titulo = f"#{r.id} | {fmt_data(r.data_registro)} | {r.obra} | {r.fiscal}"
        with st.expander(titulo, expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Frente:** {r.frente_servico}")
                st.markdown(f"**Disciplina:** {r.disciplina}")
                st.markdown(f"**Atividade:** {r.atividade}")
            with col2:
                st.markdown(f"**Equipe:** {r.equipe or '—'}")
                st.markdown(f"**Status:** {r.status}")
                st.markdown(f"**Pertinência RDOe:** {r.impacto_rdo}")
            if r.observacoes:
                st.markdown(f"**Obs:** {r.observacoes}")
            exibir_grid_evidencias(r.evidencias)


def _img_centralizada(data: bytes, legenda: str = "") -> None:
    b64 = base64.b64encode(data).decode()
    cap = (
        f'<p style="text-align:center;font-size:0.78em;color:#aaa;margin:4px 0 8px">{legenda}</p>'
        if legenda else ""
    )
    st.markdown(
        f'<div style="display:flex;flex-direction:column;align-items:center">'
        f'<img src="data:image/jpeg;base64,{b64}" width="{THUMB_SIZE}">'
        f'{cap}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _parse_evidencias(evidencias_json: str) -> list:
    """Retorna lista de dicts {foto: bytes, legenda: str}, compatível com formato antigo."""
    try:
        items = json.loads(evidencias_json)
    except Exception:
        return []
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({"foto": base64.b64decode(item["foto"]), "legenda": item.get("legenda", "")})
        else:
            result.append({"foto": base64.b64decode(item), "legenda": ""})
    return result


def exibir_grid_evidencias(evidencias_json: str) -> None:
    if not evidencias_json:
        return
    items = _parse_evidencias(evidencias_json)
    if not items:
        return
    thumbs = [{"t": img_thumb(i["foto"]), "l": i["legenda"]} for i in items]
    if len(thumbs) == 1:
        _img_centralizada(thumbs[0]["t"], thumbs[0]["l"])
    else:
        for linha in range(0, len(thumbs), 2):
            cols = st.columns(2)
            for col_idx, img_idx in enumerate(range(linha, min(linha + 2, len(thumbs)))):
                with cols[col_idx]:
                    _img_centralizada(thumbs[img_idx]["t"], thumbs[img_idx]["l"])


def salvar_registro(registro: RegistroCM) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO registros_cm (
                tenant, data_registro, obra, frente_servico, disciplina, atividade,
                equipe, fiscal, status, impacto_rdo, observacoes, evidencias
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registro.tenant,
                registro.data_registro,
                registro.obra,
                registro.frente_servico,
                registro.disciplina,
                registro.atividade,
                registro.equipe,
                registro.fiscal,
                registro.status,
                registro.impacto_rdo,
                registro.observacoes,
                registro.evidencias,
            ),
        )


init_db()
st.set_page_config(page_title="RDOe - Registro Diario de Ocorrências", page_icon="📱", layout="centered")
st.markdown(
    '<h1 style="font-size:1.5rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
    '📱 RDOe - Registro Diario de Ocorrências</h1>',
    unsafe_allow_html=True,
)
st.caption("SRGE/SI-III/HDTON/CMUGH")

st.subheader("Contrato nº.:")
tenant = st.text_input("", placeholder="Nº do contrato / Nome da empresa")
if not tenant.strip():
    st.warning("Informe o número do contrato ou nome da empresa para acessar os dados.")
    st.stop()

tenant = tenant.strip().lower()
lista_registros = carregar_lista(tenant)

st.subheader("1) Fiscalização de Campo")
col_nome, col_mat = st.columns([3, 2])
with col_nome:
    fiscal_nome = st.text_input("Nome do Fiscal de Campo", key="fiscal_nome")
with col_mat:
    fiscal_matricula = st.text_input("Matrícula", key="fiscal_matricula")
col_chave, col_disc_fiscal = st.columns([2, 3])
with col_chave:
    fiscal_chave = st.text_input("Chave", key="fiscal_chave")
with col_disc_fiscal:
    fiscal_disciplina = st.selectbox(
        "Disciplina",
        ["Tubulação", "Dinâmicos", "Estáticos", "Civil", "Estruturas Metálicas", "Elétrica", "Instrumentação", "Telecom", "Automação", "HVAC", "Comissionamento", "Qualidade", "SMS", "Contratual"],
        key="fiscal_disciplina",
    )

st.subheader("2) Registros RDOe")

if "fk" not in st.session_state:
    st.session_state.fk = 0
fk = st.session_state.fk

col_unidade, col_data = st.columns([4, 1])
with col_unidade:
    obra = st.text_input("Unidade", key=f"obra_{fk}")
with col_data:
    data_registro = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", key=f"data_{fk}")

col_frente, col_disciplina = st.columns([3, 2])
with col_frente:
    frente_servico = st.text_input("Frente de serviço", key=f"frente_{fk}")
with col_disciplina:
    disciplina = st.selectbox("Disciplina", ["Tubulação", "Dinâmicos", "Estáticos", "Civil", "Estruturas Metálicas", "Elétrica", "Instrumentação", "Telecom", "Automação", "HVAC", "Comissionamento", "Qualidade", "SMS", "Contratual"], key=f"disc_{fk}")

atividade = st.text_area("Atividade Executada", key=f"ativ_{fk}")

fotos = st.file_uploader(
    "Evidências (máx. 4 fotos)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key=f"fotos_{fk}",
)
if len(fotos) > 4:
    st.warning("Apenas as 4 primeiras fotos serão consideradas.")
    fotos = fotos[:4]
_legendas: list[str] = []
if fotos:
    _thumbs = [img_thumb(f.getvalue()) for f in fotos]
    if len(_thumbs) == 1:
        _img_centralizada(_thumbs[0])
        _legendas.append(st.text_input("Legenda", key=f"cap_0_{fk}", placeholder="Descrição da evidência", label_visibility="collapsed"))
    else:
        for _i in range(0, len(_thumbs), 2):
            _cols = st.columns(2)
            for _j in range(2):
                _idx = _i + _j
                if _idx < len(_thumbs):
                    with _cols[_j]:
                        _img_centralizada(_thumbs[_idx])
                        _legendas.append(st.text_input("Legenda", key=f"cap_{_idx}_{fk}", placeholder="Descrição da evidência", label_visibility="collapsed"))

equipe = st.text_input("Equipe / empreiteira", key=f"equipe_{fk}")
fiscal = fiscal_nome
status = st.selectbox("Status", ["Executado", "Em andamento", "Bloqueado", "Não iniciado"], key=f"status_{fk}")
impacto_rdo = st.selectbox("Pertinência para RDOe", ["Alta", "Média", "Baixa"], key=f"impacto_{fk}")
observacoes = st.text_area("Observações adicionais", key=f"obs_{fk}")

if st.button("Salvar no list", type="primary"):
    obrigatorios = [obra.strip(), frente_servico.strip(), atividade.strip(), fiscal.strip()]
    if not all(obrigatorios):
        st.error("Preencha os campos obrigatórios: obra, frente, atividade e fiscal.")
    else:
        salvar_registro(
            RegistroCM(
                id=0,
                tenant=tenant,
                data_registro=data_registro.isoformat(),
                obra=obra.strip(),
                frente_servico=frente_servico.strip(),
                disciplina=disciplina,
                atividade=atividade.strip(),
                equipe=equipe.strip(),
                fiscal=fiscal.strip(),
                status=status,
                impacto_rdo=impacto_rdo,
                observacoes=observacoes.strip(),
                evidencias=json.dumps([
                    {"foto": base64.b64encode(f.getvalue()).decode(), "legenda": leg}
                    for f, leg in zip(fotos[:4], _legendas)
                ]),
            )
        )
        st.success("Registro inserido no list com sucesso.")
        st.session_state.fk += 1
        st.rerun()

st.subheader("3) Consolidação do fiscal para RDOe")
filtro_obra = st.text_input("Filtrar por obra")
filtro_impacto = st.multiselect("Filtrar pertinência", ["Alta", "Média", "Baixa"], default=["Alta", "Média"])
filtro_status = st.multiselect("Filtrar status", ["Executado", "Em andamento", "Bloqueado", "Não iniciado"], default=["Executado", "Em andamento", "Bloqueado"])

lista_filtrada = lista_registros
if filtro_obra.strip():
    lista_filtrada = [item for item in lista_filtrada if filtro_obra.lower() in item.obra.lower()]
if filtro_impacto:
    lista_filtrada = [item for item in lista_filtrada if item.impacto_rdo in filtro_impacto]
if filtro_status:
    lista_filtrada = [item for item in lista_filtrada if item.status in filtro_status]

st.metric("Registros pertinentes para RDOe", len(lista_filtrada))
if lista_filtrada:
    exibir_cards(lista_filtrada)
else:
    st.warning("Nenhum registro encontrado com os filtros atuais.")

def _to_excel(registros) -> bytes:
    df = pd.DataFrame(para_exibicao(registros))
    df = df.drop(columns=["id", "tenant", "evidencias"], errors="ignore")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="RDOe")
    return buf.getvalue()


def _cabecalho_word(doc: Document, contrato: str) -> None:
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = t.add_run("RDOe - Registro Diario de Ocorrências")
    run.bold = True
    run.font.size = Pt(14)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"SRGE/SI-III/HDTON/CMUGH  |  Contrato: {contrato}").font.size = Pt(10)
    doc.add_paragraph()


def _to_word(registros, contrato: str) -> bytes:
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(2)
        sec.right_margin = Cm(2)
    _cabecalho_word(doc, contrato)
    for r in registros:
        doc.add_heading(f"#{r.id} | {fmt_data(r.data_registro)} | {r.obra} | {r.fiscal}", level=2)
        tabela = doc.add_table(rows=3, cols=2)
        tabela.style = "Table Grid"
        dados = [
            ("Frente de Serviço", r.frente_servico, "Equipe", r.equipe or "—"),
            ("Disciplina", r.disciplina, "Status", r.status),
            ("Atividade Executada", r.atividade, "Pertinência RDOe", r.impacto_rdo),
        ]
        for i, (l1, v1, l2, v2) in enumerate(dados):
            tabela.cell(i, 0).text = f"{l1}: {v1}"
            tabela.cell(i, 1).text = f"{l2}: {v2}"
        if r.observacoes:
            doc.add_paragraph(f"Observações: {r.observacoes}")
        # evidências
        items = _parse_evidencias(r.evidencias)
        if items:
            doc.add_paragraph("Evidências:").runs[0].bold = True
            thumbs = [(img_thumb(i["foto"]), i["legenda"]) for i in items]
            for par in range(0, len(thumbs), 2):
                tbl = doc.add_table(rows=2, cols=min(2, len(thumbs) - par))
                for col_idx in range(tbl.columns.__len__()):
                    thumb_data, legenda = thumbs[par + col_idx]
                    cell = tbl.cell(0, col_idx)
                    cell_p = cell.paragraphs[0]
                    cell_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = cell_p.add_run()
                    run.add_picture(io.BytesIO(thumb_data), width=Cm(6))
                    leg_p = tbl.cell(1, col_idx).paragraphs[0]
                    leg_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    leg_run = leg_p.add_run(legenda)
                    leg_run.font.size = Pt(8)
                    leg_run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
        doc.add_paragraph()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class _PDF(FPDF):
    def __init__(self, contrato: str):
        super().__init__()
        self._contrato = contrato

    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, "RDOe - Registro Diario de Ocorrencias", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, f"SRGE/SI-III/HDTON/CMUGH  |  Contrato: {self._contrato}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Pag. {self.page_no()}", align="C")


def _to_pdf(registros, contrato: str) -> bytes:
    pdf = _PDF(contrato)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for r in registros:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"#{r.id} | {fmt_data(r.data_registro)} | {r.obra} | {r.fiscal}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        campos = [
            ("Frente", r.frente_servico), ("Disciplina", r.disciplina),
            ("Atividade", r.atividade), ("Equipe", r.equipe or "-"),
            ("Status", r.status), ("Pertinencia RDOe", r.impacto_rdo),
        ]
        for label, valor in campos:
            pdf.set_font("Helvetica", "B", 9)
            pdf.write(6, f"{label}: ")
            pdf.set_font("Helvetica", "", 9)
            pdf.write(6, valor)
            pdf.ln(6)
        if r.observacoes:
            pdf.set_font("Helvetica", "B", 9)
            pdf.write(6, "Obs: ")
            pdf.set_font("Helvetica", "", 9)
            pdf.write(6, r.observacoes)
            pdf.ln(6)
        items = _parse_evidencias(r.evidencias)
        if items:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 6, "Evidencias:", new_x="LMARGIN", new_y="NEXT")
            thumbs = [(img_thumb(i["foto"]), i["legenda"]) for i in items]
            col_w = 45
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            for idx, (thumb_data, legenda) in enumerate(thumbs):
                col = idx % 2
                row = idx // 2
                x = x0 + col * (col_w + 5)
                y = y0 + row * (col_w + 10)
                tmp = io.BytesIO(thumb_data)
                pdf.image(tmp, x=x, y=y, w=col_w)
                pdf.set_xy(x, y + col_w + 1)
                pdf.set_font("Helvetica", "I", 7)
                pdf.cell(col_w, 4, legenda[:30], align="C")
            rows_used = (len(thumbs) + 1) // 2
            pdf.set_xy(x0, y0 + rows_used * (col_w + 10))
        pdf.ln(4)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 170, pdf.get_y())
        pdf.ln(4)
    return bytes(pdf.output())


col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
with col_exp1:
    st.download_button(
        "⬇ Word (.docx)",
        data=_to_word(lista_filtrada, tenant),
        file_name=f"rdoe_{tenant}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
with col_exp2:
    st.download_button(
        "⬇ PDF",
        data=_to_pdf(lista_filtrada, tenant),
        file_name=f"rdoe_{tenant}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
with col_exp3:
    st.download_button(
        "⬇ Excel (.xlsx)",
        data=_to_excel(lista_filtrada),
        file_name=f"rdoe_consolidado_{tenant}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col_exp4:
    st.download_button(
        "⬇ JSON",
        data=json.dumps(para_exibicao(lista_filtrada), ensure_ascii=False, indent=2),
        file_name=f"rdoe_consolidado_{tenant}.json",
        mime="application/json",
        use_container_width=True,
    )
