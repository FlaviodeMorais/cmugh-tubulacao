import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List

import streamlit as st

DATA_FILE = Path("tarefas_cm.json")


@dataclass
class RegistroCM:
    id: int
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


def carregar_lista() -> List[RegistroCM]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return [RegistroCM(**item) for item in json.load(f)]


def salvar_lista(lista_registros: List[RegistroCM]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump([asdict(item) for item in lista_registros], f, ensure_ascii=False, indent=2)


def novo_id(lista_registros: List[RegistroCM]) -> int:
    return max((item.id for item in lista_registros), default=0) + 1


st.set_page_config(page_title="C&M Mobile - EPC Petrobras", page_icon="📱", layout="centered")
st.title("📱 C&M Mobile | Registro de Campo")
st.caption("Preenchimento rápido em campo com consolidação para o RDOe")

if "lista_registros" not in st.session_state:
    st.session_state.lista_registros = carregar_lista()

st.subheader("1) Lista base de informações")
st.info("Toda informação preenchida no formulário abaixo entra automaticamente nesta lista.")

with st.expander("Ver lista completa", expanded=False):
    if st.session_state.lista_registros:
        st.dataframe([asdict(item) for item in st.session_state.lista_registros], use_container_width=True)
    else:
        st.write("Lista vazia. Preencha o formulário para incluir registros.")

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
            novo_registro = RegistroCM(
                id=novo_id(st.session_state.lista_registros),
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
            st.session_state.lista_registros.append(novo_registro)
            salvar_lista(st.session_state.lista_registros)
            st.success(f"Registro #{novo_registro.id} inserido no list com sucesso.")

st.subheader("3) Consolidação do fiscal para RDOe")
st.caption("Use os filtros para separar o que é pertinente antes de consolidar no RDOe.")

filtro_obra = st.text_input("Filtrar por obra")
filtro_impacto = st.multiselect("Filtrar pertinência", ["Alta", "Média", "Baixa"], default=["Alta", "Média"])
filtro_status = st.multiselect(
    "Filtrar status", ["Executado", "Em andamento", "Bloqueado", "Não iniciado"], default=["Executado", "Em andamento", "Bloqueado"]
)

lista_filtrada = st.session_state.lista_registros
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
    file_name="rdoe_consolidado_cm.json",
    mime="application/json",
)
