# C&M Mobile para Obras EPC Petrobras

Aplicativo em Streamlit com foco **mobile** para registrar informações de campo e apoiar a consolidação do **RDOe** pelo fiscal.

## Fluxo solicitado

1. Existe um **list** (`lista_registros`) que armazena todas as informações.
2. O time preenche um **formulário mobile**.
3. Ao enviar, os dados entram automaticamente no **list**.
4. O fiscal acessa o **list**, aplica filtros de pertinência e consolida o que deve entrar no RDOe.

## Funcionalidades

- Interface em layout centralizado para uso mobile.
- Formulário de registro com obra, frente, disciplina, atividade, equipe, fiscal, status e pertinência para RDOe.
- Lista base visível no app.
- Painel de consolidação com filtros por obra, status e pertinência.
- Exportação da lista consolidada em JSON.
- Persistência local em `tarefas_cm.json`.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
