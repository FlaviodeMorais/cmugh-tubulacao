import base64
import io
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List

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

st.download_button(
    "Exportar lista consolidada (JSON)",
    data=json.dumps(para_exibicao(lista_filtrada), ensure_ascii=False, indent=2),
    file_name=f"rdoe_consolidado_{tenant}.json",
    mime="application/json",
)
