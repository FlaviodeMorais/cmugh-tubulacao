import base64
import hashlib
import io
import json
import re
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

# Credenciais do admin master (senha armazenada como SHA-256)
_ADMIN_USER = "Admin"
_ADMIN_HASH = hashlib.sha256("979101Fm$".encode()).hexdigest()


def _verificar_admin(usuario: str, senha: str) -> bool:
    return (usuario == _ADMIN_USER and
            hashlib.sha256(senha.encode()).hexdigest() == _ADMIN_HASH)

DISCIPLINAS = [
    "Tubulação", "Dinâmicos", "Estáticos", "Civil", "Estruturas Metálicas",
    "Elétrica", "Instrumentação", "Telecom", "Automação", "HVAC",
    "Comissionamento", "Qualidade", "SMS", "Contratual",
]

# ─────────────────────────── DATACLASS ────────────────────────────

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
    responsavel: str
    fiscal: str
    status: str
    impacto_rdo: str
    observacoes: str
    evidencias: str = ""
    chave: str = ""

# ─────────────────────────── BANCO DE DADOS ───────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registros_cm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL,
                data_registro TEXT NOT NULL,
                obra TEXT NOT NULL,
                frente_servico TEXT NOT NULL,
                disciplina TEXT NOT NULL,
                atividade TEXT NOT NULL,
                equipe TEXT,
                responsavel TEXT DEFAULT '',
                fiscal TEXT NOT NULL,
                status TEXT NOT NULL,
                impacto_rdo TEXT NOT NULL,
                observacoes TEXT,
                evidencias TEXT DEFAULT '',
                chave TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contratos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero TEXT UNIQUE NOT NULL,
                senha_admin TEXT NOT NULL,
                email_destino TEXT DEFAULT '',
                smtp_servidor TEXT DEFAULT '',
                smtp_porta INTEGER DEFAULT 587,
                smtp_usuario TEXT DEFAULT '',
                smtp_senha TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fiscais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contrato TEXT NOT NULL,
                nome TEXT NOT NULL,
                matricula TEXT DEFAULT '',
                chave TEXT DEFAULT '',
                disciplina TEXT DEFAULT '',
                email TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contrato TEXT NOT NULL,
                nome TEXT NOT NULL
            )
        """)
        for col, definition in [
            ("evidencias",   "TEXT DEFAULT ''"),
            ("chave",        "TEXT DEFAULT ''"),
            ("responsavel",  "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE registros_cm ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE fiscais ADD COLUMN email TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        for col, defn in [
            ("email_destino", "TEXT DEFAULT ''"),
            ("smtp_servidor", "TEXT DEFAULT ''"),
            ("smtp_porta",    "INTEGER DEFAULT 587"),
            ("smtp_usuario",  "TEXT DEFAULT ''"),
            ("smtp_senha",    "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE contratos ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass


# ── contratos ──

def listar_contratos() -> List[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT numero FROM contratos ORDER BY numero").fetchall()
    return [r["numero"] for r in rows]


def criar_contrato(numero: str, senha: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO contratos (numero, senha_admin) VALUES (?, ?)", (numero, senha))
        return True
    except sqlite3.IntegrityError:
        return False


def verificar_senha(numero: str, senha: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM contratos WHERE numero=? AND senha_admin=?", (numero, senha)
        ).fetchone()
    return row is not None


def excluir_contrato(numero: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM contratos WHERE numero=?", (numero,))


# ── fiscais ──

def listar_fiscais(contrato: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fiscais WHERE contrato=? ORDER BY nome", (contrato,)
        ).fetchall()
    return [dict(r) for r in rows]


def adicionar_fiscal(contrato, nome, chave, disciplina, email="") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fiscais (contrato, nome, chave, disciplina, email) VALUES (?,?,?,?,?)",
            (contrato, nome, chave, disciplina, email),
        )


def excluir_fiscal(fid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM fiscais WHERE id=?", (fid,))


# ── unidades ──

def listar_unidades(contrato: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM unidades WHERE contrato=? ORDER BY nome", (contrato,)
        ).fetchall()
    return [dict(r) for r in rows]


def adicionar_unidade(contrato: str, nome: str) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO unidades (contrato, nome) VALUES (?,?)", (contrato, nome))


def excluir_unidade(uid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM unidades WHERE id=?", (uid,))


# ── registros ──

def carregar_lista(tenant: str) -> List[RegistroCM]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM registros_cm WHERE tenant=? ORDER BY id DESC", (tenant,)
        ).fetchall()
    return [RegistroCM(**dict(r)) for r in rows]


def salvar_registro(registro: RegistroCM) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO registros_cm (
                tenant, data_registro, obra, frente_servico, disciplina, atividade,
                equipe, responsavel, fiscal, status, impacto_rdo, observacoes, evidencias, chave
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            registro.tenant, registro.data_registro, registro.obra,
            registro.frente_servico, registro.disciplina, registro.atividade,
            registro.equipe, registro.responsavel, registro.fiscal, registro.status,
            registro.impacto_rdo, registro.observacoes,
            registro.evidencias, registro.chave,
        ))

# ─────────────────────────── HELPERS VISUAIS ──────────────────────

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


def id_registro(r) -> str:
    data = fmt_data(r.data_registro).replace("/", "")
    return f"RO-{r.obra}-{r.chave}-{data}-{r.id:04d}"


def _parse_evidencias(evidencias_json: str) -> list:
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


def _img_centralizada(data: bytes, legenda: str = "") -> None:
    b64 = base64.b64encode(data).decode()
    cap = (
        f'<p style="text-align:center;font-size:0.78em;color:#aaa;margin:4px 0 8px">{legenda}</p>'
        if legenda else ""
    )
    st.markdown(
        f'<div style="display:flex;flex-direction:column;align-items:center">'
        f'<img src="data:image/jpeg;base64,{b64}" width="{THUMB_SIZE}">'
        f'{cap}</div>',
        unsafe_allow_html=True,
    )


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
        with st.expander(id_registro(r), expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Frente:** {r.frente_servico}")
                st.markdown(f"**Disciplina:** {r.disciplina}")
                st.markdown(f"**Atividade:** {r.atividade}")
            with col2:
                st.markdown(f"**Equipe:** {r.equipe or '—'}")
                st.markdown(f"**Responsável:** {r.responsavel or '—'}")
                st.markdown(f"**Status:** {r.status}")
                st.markdown(f"**Classificação:** {r.impacto_rdo}")
            if r.observacoes:
                st.markdown(f"**Obs:** {r.observacoes}")
            exibir_grid_evidencias(r.evidencias)

# ─────────────────────────── EXPORTAÇÕES ──────────────────────────

def _to_excel(registros) -> bytes:
    df = pd.DataFrame(para_exibicao(registros))
    df = df.drop(columns=["id", "tenant", "evidencias"], errors="ignore")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="RDOe")
    return buf.getvalue()


def _cabecalho_word(doc: Document, contrato: str) -> None:
    t = doc.add_paragraph()
    run = t.add_run("RO - Registro de Ocorrências")
    run.bold = True
    run.font.size = Pt(14)
    sub = doc.add_paragraph()
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
        doc.add_heading(id_registro(r), level=2)
        tabela = doc.add_table(rows=4, cols=2)
        tabela.style = "Table Grid"
        dados = [
            ("Frente de Serviço", r.frente_servico, "Equipe", r.equipe or "—"),
            ("Responsável Contratada", r.responsavel or "—", "", ""),
            ("Disciplina", r.disciplina, "Status", r.status),
            ("Atividade Executada", r.atividade, "Classificação", r.impacto_rdo),
        ]
        for i, (l1, v1, l2, v2) in enumerate(dados):
            tabela.cell(i, 0).text = f"{l1}: {v1}"
            tabela.cell(i, 1).text = f"{l2}: {v2}"
        if r.observacoes:
            doc.add_paragraph(f"Observações: {r.observacoes}")
        items = _parse_evidencias(r.evidencias)
        if items:
            doc.add_paragraph("Evidências:").runs[0].bold = True
            thumbs = [(img_thumb(i["foto"]), i["legenda"]) for i in items]
            for par in range(0, len(thumbs), 2):
                tbl = doc.add_table(rows=2, cols=min(2, len(thumbs) - par))
                for col_idx in range(len(tbl.columns)):
                    thumb_data, legenda = thumbs[par + col_idx]
                    cell_p = tbl.cell(0, col_idx).paragraphs[0]
                    cell_p.add_run().add_picture(io.BytesIO(thumb_data), width=Cm(6))
                    leg_p = tbl.cell(1, col_idx).paragraphs[0]
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
        self.cell(0, 8, "RO - Registro de Ocorrencias", align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, f"SRGE/SI-III/HDTON/CMUGH  |  Contrato: {self._contrato}", align="L", new_x="LMARGIN", new_y="NEXT")
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
        pdf.cell(0, 7, id_registro(r), new_x="LMARGIN", new_y="NEXT")
        for label, valor in [
            ("Frente", r.frente_servico), ("Disciplina", r.disciplina),
            ("Atividade", r.atividade), ("Equipe", r.equipe or "-"),
            ("Responsável", r.responsavel or "-"),
            ("Status", r.status), ("Classificação", r.impacto_rdo),
        ]:
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
            x0, y0 = pdf.get_x(), pdf.get_y()
            for idx, (thumb_data, legenda) in enumerate(thumbs):
                col, row = idx % 2, idx // 2
                x = x0 + col * (col_w + 5)
                y = y0 + row * (col_w + 10)
                pdf.image(io.BytesIO(thumb_data), x=x, y=y, w=col_w)
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

# ─────────────────────────── COMPARTILHAMENTO ─────────────────────

def _share_btn(label: str, data: bytes, filename: str, mime: str, key: str) -> None:
    """Botão que usa Web Share API no mobile; fallback download no desktop."""
    b64 = base64.b64encode(data).decode()
    fid = re.sub(r"\W", "_", key)
    html = f"""
<style>
#sbtn_{fid}{{background:#ff4b4b;color:#fff;border:none;padding:8px 16px;
border-radius:6px;cursor:pointer;font-size:14px;width:100%;
font-weight:600;font-family:sans-serif;}}
#sbtn_{fid}:hover{{background:#e03e3e;}}
</style>
<button id="sbtn_{fid}" onclick="sf_{fid}()">{label}</button>
<script>
async function sf_{fid}(){{
  const raw=atob('{b64}');
  const buf=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) buf[i]=raw.charCodeAt(i);
  const blob=new Blob([buf],{{type:'{mime}'}});
  const file=new File([blob],'{filename}',{{type:'{mime}'}});
  if(navigator.canShare&&navigator.canShare({{files:[file]}})){{
    try{{await navigator.share({{files:[file],title:'{filename}'}});return;}}
    catch(e){{if(e.name==='AbortError')return;}}
  }}
  const url=URL.createObjectURL(blob);
  const w=window.open(url,'_blank');
  if(!w){{
    const a=document.createElement('a');
    a.href=url;a.download='{filename}';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
  }}
  setTimeout(()=>URL.revokeObjectURL(url),90000);
}}
</script>"""
    st.components.v1.html(html, height=45)


# ─────────────────────────── INICIALIZAÇÃO ────────────────────────

init_db()
st.set_page_config(page_title="RO - Registro de Ocorrências", layout="centered")
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
header[data-testid="stHeader"] {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {display: none;}
[data-testid="manage-app-button"] {display: none !important;}
[class*="viewerBadge"] {display: none !important;}
[data-testid="stBottom"] > div:last-child {display: none !important;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── ESTADO ADMIN ────────────────────────

if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False
if "show_admin" not in st.session_state:
    st.session_state.show_admin = False

# ─────────────────────────── CABEÇALHO ───────────────────────────

col_titulo, col_gear = st.columns([11, 1])
with col_titulo:
    st.markdown(
        '<h1 style="font-size:1.5rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
        'RO - Registro de Ocorrências</h1>',
        unsafe_allow_html=True,
    )
with col_gear:
    st.markdown("<div style='padding-top:12px'>", unsafe_allow_html=True)
    if st.button("⚙️", help="Configurações / Admin", key="btn_gear"):
        st.session_state.show_admin = not st.session_state.show_admin
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.caption("SRGE/SI-III/HDTON/CMUGH")

# ─────────────────────────── PAINEL ADMIN ────────────────────────

if st.session_state.show_admin:
    with st.container(border=True):
        st.markdown("#### ⚙️ Área Admin")

        if st.session_state.admin_logado:
            st.markdown("""
<style>
[data-testid="manage-app-button"] {display: flex !important;}
[class*="viewerBadge"] {display: block !important;}
[data-testid="stBottom"] > div:last-child {display: block !important;}
</style>
""", unsafe_allow_html=True)
            col_ok, col_sair = st.columns([4, 1])
            col_ok.success("Admin conectado")
            if col_sair.button("Sair", key="admin_sair"):
                st.session_state.admin_logado = False
                st.session_state.show_admin = False
                st.rerun()

            contratos_admin = listar_contratos()
            if not contratos_admin:
                st.info("Nenhum contrato cadastrado ainda.")
                with st.form("form_novo_contrato"):
                    nc_num   = st.text_input("Nº do Contrato")
                    nc_senha = st.text_input("Senha do Contrato", type="password")
                    if st.form_submit_button("Criar Contrato"):
                        if nc_num.strip() and nc_senha.strip():
                            if criar_contrato(nc_num.strip(), nc_senha.strip()):
                                st.success("Contrato criado.")
                                st.rerun()
                            else:
                                st.error("Contrato já existe.")
                        else:
                            st.error("Preencha todos os campos.")
            else:
                contrato_admin = st.selectbox("Contrato", contratos_admin,
                                              key="sel_contrato_admin")
                tab_c, tab_f, tab_u = st.tabs(["Contratos", "Fiscais", "Unidades"])

                # ── Contratos ──
                with tab_c:
                    st.markdown("**Novo Contrato**")
                    with st.form("form_novo_contrato"):
                        nc_num   = st.text_input("Nº do Contrato")
                        nc_senha = st.text_input("Senha do Contrato", type="password")
                        if st.form_submit_button("Criar"):
                            if nc_num.strip() and nc_senha.strip():
                                if criar_contrato(nc_num.strip(), nc_senha.strip()):
                                    st.success("Contrato criado.")
                                    st.rerun()
                                else:
                                    st.error("Contrato já existe.")
                            else:
                                st.error("Preencha todos os campos.")
                    st.markdown("**Contratos cadastrados**")
                    for _c in contratos_admin:
                        c1, c2 = st.columns([4, 1])
                        c1.write(_c)
                        if c2.button("🗑", key=f"del_c_{_c}"):
                            excluir_contrato(_c)
                            st.rerun()

                # ── Fiscais ──
                with tab_f:
                    st.markdown("**Cadastrar Fiscal**")
                    with st.form("form_fiscal"):
                        f_nome  = st.text_input("Nome do Fiscal de Campo")
                        f_chave = st.text_input("Chave")
                        f_disc  = st.selectbox("Disciplina", DISCIPLINAS, key="disc_fiscal")
                        f_email = st.text_input("E-mail do Fiscal")
                        if st.form_submit_button("Adicionar"):
                            if f_nome.strip():
                                adicionar_fiscal(contrato_admin, f_nome.strip(),
                                                 f_chave.strip(), f_disc, f_email.strip())
                                st.success("Fiscal adicionado.")
                                st.rerun()
                            else:
                                st.error("Informe o nome do fiscal.")
                    st.markdown("**Fiscais cadastrados**")
                    for fiscal in listar_fiscais(contrato_admin):
                        c1, c2 = st.columns([4, 1])
                        c1.write(f"{fiscal['nome']} | {fiscal.get('email') or fiscal['chave']}")
                        if c2.button("🗑", key=f"del_f_{fiscal['id']}"):
                            excluir_fiscal(fiscal["id"])
                            st.rerun()

                # ── Unidades ──
                with tab_u:
                    st.markdown("**Cadastrar Unidade**")
                    with st.form("form_unidade"):
                        u_nome = st.text_input("Nome da Unidade")
                        if st.form_submit_button("Adicionar"):
                            if u_nome.strip():
                                adicionar_unidade(contrato_admin, u_nome.strip())
                                st.success("Unidade adicionada.")
                                st.rerun()
                            else:
                                st.error("Informe o nome da unidade.")
                    st.markdown("**Unidades cadastradas**")
                    for unidade in listar_unidades(contrato_admin):
                        c1, c2 = st.columns([4, 1])
                        c1.write(unidade["nome"])
                        if c2.button("🗑", key=f"del_u_{unidade['id']}"):
                            excluir_unidade(unidade["id"])
                            st.rerun()

        else:
            with st.form("admin_login"):
                _user  = st.text_input("Usuário")
                _senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    if _verificar_admin(_user.strip(), _senha):
                        st.session_state.admin_logado = True
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos.")

# ─────────────────────────── SELEÇÃO DE CONTRATO ─────────────────

st.subheader("Contrato nº.:")
contratos_disponiveis = listar_contratos()

if contratos_disponiveis:
    tenant = st.selectbox("", contratos_disponiveis, label_visibility="collapsed")
else:
    tenant = st.text_input("", placeholder="Nº do contrato (solicite ao admin o cadastro)")
    if not tenant.strip():
        st.warning("Nenhum contrato cadastrado. Acesse a Área Admin no menu lateral para cadastrar.")
        st.stop()
    tenant = tenant.strip()

lista_registros = carregar_lista(tenant)

# ─────────────────────────── 1) FISCALIZAÇÃO DE CAMPO ───────────

st.subheader("1) Fiscalização de Campo")

fiscais_disponiveis = listar_fiscais(tenant)
fiscal_selecionado  = {}

if fiscais_disponiveis:
    nomes = [""] + [f["nome"] for f in fiscais_disponiveis]
    nome_escolhido = st.selectbox("Nome do Fiscal de Campo", nomes, key="sel_fiscal",
                                  format_func=lambda x: "— selecione —" if x == "" else x)
    fiscal_selecionado = next((f for f in fiscais_disponiveis if f["nome"] == nome_escolhido), {})
    if nome_escolhido:
        col_chave, col_disc_f = st.columns(2)
        col_chave.text_input("Chave",      value=fiscal_selecionado.get("chave", ""),      disabled=True, key="chave_ro")
        col_disc_f.text_input("Disciplina", value=fiscal_selecionado.get("disciplina", ""), disabled=True, key="disc_ro")
else:
    st.info("Nenhum fiscal cadastrado para este contrato. Solicite ao admin.")
    col_nome, col_email_f = st.columns([3, 2])
    with col_nome:
        fiscal_selecionado["nome"] = st.text_input("Nome do Fiscal de Campo", key="fiscal_nome_livre")
    with col_email_f:
        fiscal_selecionado["email"] = st.text_input("E-mail", key="fiscal_email_livre")
    col_chave, col_disc_f = st.columns([2, 3])
    with col_chave:
        fiscal_selecionado["chave"] = st.text_input("Chave", key="fiscal_chave_livre")
    with col_disc_f:
        fiscal_selecionado["disciplina"] = st.selectbox("Disciplina", DISCIPLINAS, key="fiscal_disc_livre")

fiscal_nome  = fiscal_selecionado.get("nome", "")
fiscal_chave = fiscal_selecionado.get("chave", "")

# ─────────────────────────── 2) REGISTROS RDOe ───────────────────

st.subheader("2) Registros de Ocorrências")

if "fk" not in st.session_state:
    st.session_state.fk = 0
fk = st.session_state.fk

# Unidade
unidades_disponiveis = [u["nome"] for u in listar_unidades(tenant)]
col_unidade, col_data = st.columns([4, 1])
with col_unidade:
    if unidades_disponiveis:
        obra = st.selectbox("Unidade", unidades_disponiveis, key=f"obra_{fk}")
    else:
        obra = st.text_input("Unidade", key=f"obra_{fk}")
with col_data:
    data_registro = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", key=f"data_{fk}")

col_frente, col_disciplina = st.columns([3, 2])
with col_frente:
    frente_servico = st.text_input("Frente de serviço", key=f"frente_{fk}")
with col_disciplina:
    disciplina = st.selectbox("Disciplina", DISCIPLINAS, key=f"disc_{fk}")

atividade = st.text_area("Atividade Executada", key=f"ativ_{fk}")

fotos = st.file_uploader(
    "Evidências (máx. 4 fotos, 2 MB cada)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key=f"fotos_{fk}",
)
fotos_validas = []
for f in fotos:
    if len(f.getvalue()) > 2 * 1024 * 1024:
        st.warning(f"'{f.name}' excede 2 MB e foi ignorada.")
    else:
        fotos_validas.append(f)
fotos = fotos_validas[:4]
if len(fotos_validas) > 4:
    st.warning("Apenas as 4 primeiras fotos serão consideradas.")

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

col_equipe, col_resp = st.columns(2)
with col_equipe:
    equipe      = st.text_input("Equipe da Contratada", key=f"equipe_{fk}")
with col_resp:
    responsavel = st.text_input("Responsável Contratada", key=f"resp_{fk}")
status    = st.selectbox("Status", ["Executado", "Em andamento", "Bloqueado", "Não iniciado"], key=f"status_{fk}")
impacto_rdo = st.selectbox("Classificação do Registro", ["Alta", "Média", "Baixa"], key=f"impacto_{fk}")
observacoes = st.text_area("Observações adicionais", key=f"obs_{fk}")

if st.button("Salvar", type="primary"):
    obrigatorios = [str(obra).strip(), frente_servico.strip(), atividade.strip(), fiscal_nome.strip()]
    if not all(obrigatorios):
        st.error("Preencha os campos obrigatórios: unidade, frente, atividade e fiscal.")
    else:
        salvar_registro(RegistroCM(
            id=0,
            tenant=tenant,
            data_registro=data_registro.isoformat(),
            obra=str(obra).strip(),
            frente_servico=frente_servico.strip(),
            disciplina=disciplina,
            atividade=atividade.strip(),
            equipe=equipe.strip(),
            responsavel=responsavel.strip(),
            fiscal=fiscal_nome.strip(),
            status=status,
            impacto_rdo=impacto_rdo,
            observacoes=observacoes.strip(),
            evidencias=json.dumps([
                {"foto": base64.b64encode(f.getvalue()).decode(), "legenda": leg}
                for f, leg in zip(fotos[:4], _legendas)
            ]),
            chave=fiscal_chave.strip(),
        ))
        st.success("Registro inserido com sucesso.")
        st.session_state.fk += 1
        st.rerun()

# ─────────────────────────── 3) LIST DO FISCAL ───────────────────

st.subheader("3) Registros")

if lista_registros:
    exibir_cards(lista_registros)
else:
    st.info("Nenhum registro encontrado para este contrato.")

_n = f"{lista_registros[0].id:04d}" if len(lista_registros) == 1 else f"{len(lista_registros):04d}-registros"
if lista_registros:
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        _share_btn("Compartilhar PDF", _to_pdf(lista_registros, tenant),
                   f"RO-{_n}.pdf", "application/pdf", f"pdf_{_n}")
    with col_exp2:
        _share_btn("Compartilhar Excel", _to_excel(lista_registros),
                   f"RO-{_n}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"xlsx_{_n}")
