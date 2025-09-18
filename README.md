# Gestão de Apostas - Versão Completa Python + SQL

Este projeto é uma migração completa da aplicação original baseada em Firebase para uma arquitetura com backend em Python (Flask) e um banco de dados SQL (SQLite para desenvolvimento).

## Funcionalidades Implementadas

-   Criação, Edição e Desativação de Contas.
-   Registro de Operações de Aposta com Múltiplas Pernas.
-   Visualização de Operações Ativas.
-   Resolução de Operações (marcar um resultado como vencedor e distribuir os ganhos).
-   Registro de Transações Externas (Depósitos, Saques, Despesas).
-   Cálculo de Resumo Financeiro.
-   Histórico de Transações Recentes.

## Pré-requisitos

-   Python 3.7 ou superior
-   `pip` (gerenciador de pacotes do Python)

## Como Configurar e Rodar o Projeto

Siga estes passos no seu terminal:

**1. Estrutura de Pastas:**
   Certifique-se de que seus arquivos estão organizados da seguinte forma:

   ```
   /seu_projeto/
   |-- app.py
   |-- schema.sql
   |-- requirements.txt
   |-- README.md
   |-- /static/
   |   |-- main.js
   |-- /templates/
   |   |-- index.html
   ```

**2. Crie e Ative o Ambiente Virtual:**
   ```bash
   # Crie o ambiente
   python -m venv venv
   # Ative o ambiente (Windows)
   .\venv\Scripts\activate
   # Ative o ambiente (macOS/Linux)
   source venv/bin/activate
   ```

**3. Instale as Dependências:**
   ```bash
   pip install -r requirements.txt
   ```

**4. Crie o Banco de Dados:**
   Este comando criará o arquivo `gestao_apostas.db` e executará o script `schema.sql` para criar todas as tabelas e inserir dados de exemplo.

   ```bash
   sqlite3 gestao_apostas.db < schema.sql
   ```

**5. Rode a Aplicação:**
   Inicie o servidor Flask.

   ```bash
   python app.py
   ```

**6. Acesse a Aplicação:**
   Abra seu navegador e acesse: [http://127.0.0.1:5000](http://127.0.0.1:5000)

   **IMPORTANTE:** A aplicação usa um usuário de exemplo (`id=1`) por padrão. Em um ambiente de produção real, a função `get_current_user_id()` em `app.py` **DEVE** ser substituída por um sistema de autenticação seguro (login, sessões, tokens JWT, etc.).