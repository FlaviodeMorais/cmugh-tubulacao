# C&M Mobile SaaS para Obras EPC Petrobras

Sim — o app pode ser utilizado em modelo **SaaS**.

## O que foi adaptado para SaaS

- Armazenamento em SQLite (`cm_saas.db`) em vez de lista apenas em sessão/JSON.
- Campo de acesso por **tenant** (empresa/contrato), separando os dados por cliente.
- O formulário insere automaticamente no **list do tenant**.
- O fiscal acessa o list do tenant, filtra e consolida os itens para o **RDOe**.

## Fluxo

1. Informar tenant na tela de acesso.
2. Equipe preenche formulário mobile.
3. Registro entra automaticamente no list do tenant.
4. Fiscal filtra pertinência/status/obra e exporta consolidado do RDOe.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Publicação SaaS (sugestão)

- Hospedar em Streamlit Community Cloud, AWS, Azure ou GCP.
- Para produção multiusuário robusta, trocar SQLite por Postgres gerenciado.
