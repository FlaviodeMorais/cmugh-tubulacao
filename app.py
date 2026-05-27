import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List

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
                observacoes TEXT
            )
            """
        )


def carregar_lista(tenant: str) -> List[RegistroCM]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM registros_cm WHERE tenant = ? ORDER BY id DESC", (tenant,)
        ).fetchall()
    return [RegistroCM(**dict(r)) for r in rows]


def salvar_registro(registro: RegistroCM) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO registros_cm (
                tenant, data_registro, obra, frente_servico, disciplina, atividade,
                equipe, fiscal, status, impacto_rdo, observacoes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )


init_db()
st.set_page_config(page_title="C&M Mobile SaaS - EPC Petrobras", page_icon="📱", layout="centered")
st.title("📱 C&M Mobile SaaS | Registro de Campo")
st.caption("App mobile com segregação por empresa/contrato para consolidação do RDOe")

st.subheader("Acesso SaaS")
tenant = st.text_input("Empresa / Contrato (tenant)", value="petrobras-epc-a")
if not tenant.strip():
    st.warning("Informe o tenant para acessar os dados.")
    st.stop()

tenant = tenant.strip().lower()
lista_registros = carregar_lista(tenant)

st.subheader("1) Lista base de informações")
st.info("Cada envio do formulário é gravado automaticamente no list do tenant informado.")
with st.expander("Ver list completo do tenant", expanded=False):
    if lista_registros:
        st.dataframe([asdict(item) for item in lista_registros], use_container_width=True)
    else:
        st.write("List vazio para este tenant.")

st.subheader("2) Formulário mobile")
with st.form("form_registro_mobile", clear_on_submit=True):
    data_registro = st.date_input("Data", value=date.today())
    obra = st.text_input("Obra / Contrato")
    frente_servico = st.text_input("Frente de serviço")
    disciplina = st.selectbox("Disciplina", ["Civil", "Mecânica", "Elétrica", "Automação", "Tubulação"])
    atividade = st.text_area("Atividade executada / ocorrência")
    equipe = st.text_input("Equipe / empreiteira")
    fiscal = st.text_input("Fiscal")
    status = st.selectbox("Status", ["Executado", "Em andamento", "Bloqueado", "Não iniciado"])
    impacto_rdo = st.selectbox("Pertinência para RDOe", ["Alta", "Média", "Baixa"])
    observacoes = st.text_area("Observações adicionais")
    enviar = st.form_submit_button("Salvar no list")

    if enviar:
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
                )
            )
            st.success("Registro inserido no list com sucesso.")

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
    st.dataframe([asdict(item) for item in lista_filtrada], use_container_width=True)
else:
    st.warning("Nenhum registro encontrado com os filtros atuais.")

st.download_button(
    "Exportar lista consolidada (JSON)",
    data=json.dumps([asdict(item) for item in lista_filtrada], ensure_ascii=False, indent=2),
    file_name=f"rdoe_consolidado_{tenant}.json",
    mime="application/json",
)
