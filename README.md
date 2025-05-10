# SmartTask API 🚀

<!-- Badges -->
[![CI](https://img.shields.io/github/actions/workflow/status/Eng-Soft-Claudio/SmartTask/ci.yml?branch=main&style=for-the-badge)](https://github.com/Eng-Soft-Claudio/SmartTask/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/codecov/c/github/Eng-Soft-Claudio/SmartTask?branch=main&style=for-the-badge)](https://codecov.io/gh/Eng-Soft-Claudio/SmartTask)  
[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-blue.svg?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)  
[![Issues](https://img.shields.io/github/issues/Eng-Soft-Claudio/SmartTask?style=for-the-badge&logo=github)](https://github.com/Eng-Soft-Claudio/SmartTask/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/Eng-Soft-Claudio/SmartTask?style=for-the-badge&logo=github)](https://github.com/Eng-Soft-Claudio/SmartTask/pulls)


## Visão Geral ✨

**SmartTask API** é uma API RESTful robusta e assíncrona construída com FastAPI para gerenciamento inteligente de tarefas pessoais ou de equipe. O diferencial está no sistema de priorização automática de tarefas, baseado em importância e urgência (data de vencimento), auxiliando na organização e foco no que realmente importa.

---

### Funcionalidades Principais ✅

*   **Autenticação Segura:** Cadastro e Login com tokens **JWT**. Senhas armazenadas com hash seguro (bcrypt).
*   **Gerenciamento Completo de Tarefas (CRUD):** Operações de Criar, Ler (com filtros e ordenação), Atualizar e Deletar tarefas.
*   **Controle de Acesso:** Usuários só podem visualizar e gerenciar suas próprias tarefas.
*   **Priorização Inteligente:** Cálculo automático de `priority_score` baseado na fórmula: `(peso_prazo / dias_restantes) + (importancia * peso_importancia)`. Pesos configuráveis.
*   **Filtros e Ordenação Avançados:** Liste tarefas filtrando por status, prazo, projeto e tags (múltiplas tags com lógica AND). Ordene por score de prioridade, data de vencimento, data de criação ou importância.
*   **Notificações por E-mail (Tarefas Urgentes):** Sistema em background (ARQ + Redis) que periodicamente verifica tarefas urgentes (acima de um limiar de prioridade ou com prazo próximo/vencido) e notifica o usuário por e-mail.
*   **Webhooks Opcionais:** Envia eventos (`task.created`, `task.updated`) para uma URL externa configurável, permitindo integração com outras ferramentas. Envio realizado em background.
*   **Documentação Interativa:** Interface Swagger UI (`/docs`) e ReDoc (`/redoc`) geradas automaticamente para fácil exploração e teste da API.

---

## Tecnologias Utilizadas 🛠️

*   **Backend:** Python 3.12+
*   **Framework API:** FastAPI
*   **Validação de Dados:** Pydantic
*   **Banco de Dados:** MongoDB (interação assíncrona com Motor)
*   **Filas e Tarefas em Background (E-mail):** ARQ (Asynchronous Redis Queue)
*   **Cache/Broker para ARQ:** Redis
*   **Autenticação:** JWT (python-jose), Hashing de Senha (Passlib\[bcrypt])
*   **Envio de E-mail:** fastapi-mail
*   **Requisições HTTP (Webhooks):** httpx
*   **Servidor ASGI:** Uvicorn
*   **Testes:** Pytest, pytest-asyncio
*   **Contêiner (para Redis em dev):** Docker

---

## Pré-requisitos 📋

Para rodar este projeto localmente, você precisará ter instalado:

1.  **Python** (versão 3.10 ou superior recomendada) e **Pip**.
2.  **Git** (para clonar o repositório).
3.  **Docker** e **Docker Compose** (recomendado para gerenciar o contêiner Redis facilmente em desenvolvimento).
4.  Acesso a um servidor **MongoDB** (pode ser uma conta gratuita no MongoDB Atlas ou uma instância local).
5.  Acesso a um servidor **Redis** (pode ser rodando via Docker localmente - veja abaixo - ou um serviço externo).
6.  Credenciais de um **Servidor SMTP** (ex: Gmail com Senha de App, SendGrid, etc.) para a funcionalidade de envio de e-mails.

---

## Instalação e Configuração Rápida ⚙️

1.  **Clone o Repositório:**
    ```bash
    git clone https://github.com/Eng-Soft-Claudio/SmartTask.git
    cd SmartTask
    ```

2.  **Crie e Ative um Ambiente Virtual:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # No Windows use: venv\Scripts\activate
    ```

3.  **Instale as Dependências:**
    *(Certifique-se de criar ou ter um arquivo `requirements.txt` com as dependências)*
    ```bash
    pip install -r requirements.txt
    # Para gerar requirements.txt a partir do ambiente atual (após instalar tudo):
    # pip freeze > requirements.txt
    ```

4.  **Configure as Variáveis de Ambiente:**
    *   Copie o arquivo `.env.example` para `.env` na raiz do projeto.
    *   Edite o `.env` e preencha **obrigatoriamente**:
        *   `MONGODB_URL`: Sua string de conexão do MongoDB (ex: do Atlas).
        *   `JWT_SECRET_KEY`: Gere uma chave forte (ex: `openssl rand -hex 32`).
        *   `REDIS_URL`: A URL do seu servidor Redis (ex: `redis://localhost:6379/0` se usar Docker local).
    *   Preencha **opcionalmente** (necessário para envio de e-mail e webhooks):
        *   `MAIL_ENABLED=true`
        *   `MAIL_USERNAME=<seu_usuario_smtp>`
        *   `MAIL_PASSWORD=<sua_senha_smtp_ou_app>`
        *   `MAIL_FROM=<seu_email_remetente>`
        *   `MAIL_SERVER=<seu_host_smtp>`
        *   `MAIL_PORT=<porta_smtp>` (ex: 587)
        *   `WEBHOOK_URL=<sua_url_de_webhook>` (ex: de webhook.site)
        *   *Outras variáveis como `MAIL_FROM_NAME`, `*_WEIGHT_*`, `*_THRESHOLD`, etc.*
    *   **NUNCA comite seu arquivo `.env` no Git!**

---

## Executando a Aplicação 🚀

1.  **Inicie o Redis (usando Docker):**
    *   Verifique se o contêiner já existe (de execuções anteriores): `docker ps -a | grep smarttask-redis`
    *   Se existir e estiver parado, inicie-o: `docker start smarttask-redis`
    *   Se não existir, crie e inicie: `docker run --name smarttask-redis -p 6379:6379 -d redis:latest`
    *   Verifique se está rodando: `docker ps`

2.  **Inicie o Servidor da API (FastAPI):**
    *   (Em um terminal, com `venv` ativado)
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   A API estará acessível em `http://127.0.0.1:8000`.
    *   A documentação interativa estará em `http://127.0.0.1:8000/docs`.

3.  **Inicie o Worker de Background (ARQ):**
    *   (Em **outro** terminal, com `venv` ativado)
    ```bash
    arq app.worker.WorkerSettings
    ```
    *   Este processo ficará ativo, executando as tarefas agendadas (como verificação de e-mails urgentes). Observe os logs neste terminal.

---

## Executando os Testes ✅

*   Certifique-se que o **Redis (Docker) esteja rodando**.
*   Certifique-se que o **servidor Uvicorn NÃO esteja rodando** (os testes usam um cliente em memória).
*   (No terminal, com `venv` ativado, na raiz do projeto)
    ```bash
    pytest -v --cov=app --cov-report term-missing
    ```

---

## Estrutura do Projeto 📁

```bash
SmartTask/
├── app/                # Diretório principal da aplicação FastAPI
│ ├── core/             # Configurações, segurança, utils, email, webhook, etc.
│ ├── db/               # Lógica de acesso ao banco de dados (MongoDB utils, CRUDs)
│ ├── models/           # Modelos Pydantic (User, Task, Token)
│ ├── routers/          # Roteadores FastAPI (endpoints /auth, /tasks)
│ ├── email-templates/  # Templates HTML para e-mails
│ ├── init.py
│ ├── main.py           # Ponto de entrada da aplicação FastAPI (criação da app, lifespan, inclusão de routers)
│ └── worker.py         # Definição das tarefas e configurações do worker ARQ
├── tests/              # Testes automatizados (Pytest)
│ ├── init.py
│ └── conftest.py       # Fixtures e configuração do Pytest
│ └── test_*.py         # Arquivos de teste
├── venv/               # Ambiente virtual Python (ignorado pelo Git)
├── .env                # Variáveis de ambiente locais (NÃO COMMITAR!)
├── .env.example        # Exemplo de variáveis de ambiente necessárias
├── .gitignore          # Arquivos e pastas a serem ignorados pelo Git
├── Dockerfile          # Para containerizar a API
├── docker-compose.yml  # Para orquestrar API, worker e Redis (opcional)
├── LICENSE             # Arquivo de licença (MIT)
├── README.md           # Este arquivo
└── requirements.txt    # Dependências Python do projeto
```

---

## Roadmap Futuro 🗺️

*   ➡️ **Cobertura Completa de Testes:** Expandir os testes unitários e de integração com Pytest.
*   🔄 **Recálculo Periódico de Prioridade:** Adicionar tarefa ARQ para atualizar scores diariamente.
*   🔐 **Controle de Acesso Baseado em Papéis (RBAC):** Introduzir papéis (ex: Admin, Usuário) com diferentes permissões.
*   🤝 **Compartilhamento de Tarefas/Projetos:** Permitir colaboração entre usuários.
*   🔔 **Notificações em Tempo Real (WebSockets):** Para atualizações instantâneas na interface (quando houver uma).
*   🛡️ **Verificação de Assinatura Webhook:** Implementar verificação HMAC no lado do receptor.
*   🐳 **Dockerização Completa:** Facilitar deploy com `Dockerfile` e `docker-compose.yml`.
*   📊 **Melhorias na Lógica de Prioridade:** Refinar a fórmula ou permitir configuração por usuário.
*   🐛 **Tratamento de Erros Aprimorado:** Implementar error handlers mais robustos.

---

## Contribuição 🤝

Contribuições são bem-vindas! Siga estes passos:

1.  Faça um **Fork** do projeto.
2.  Crie uma nova **Branch** (`git checkout -b feature/MinhaNovaFeature`).
3.  Faça suas alterações e **Commit** (`git commit -m "feat: Adiciona MinhaNovaFeature"`).
4.  **Push** para a sua branch (`git push origin feature/MinhaNovaFeature`).
5.  Abra um **Pull Request**.

---

## Licença 📜

Este projeto está licenciado sob a Licença MIT.

Direitos Autorais: 2025, Cláudio de Lima Tosta.

É concedida permissão, gratuita, a qualquer pessoa que obtenha uma cópia deste software e dos arquivos de documentação associados (o "Software"), para lidar com o Software sem restrições, incluindo, entre outras, os direitos de usar, copiar, modificar, mesclar, publicar, distribuir, sublicenciar e/ou vender cópias do Software, e para permitir que as pessoas a quem o Software é fornecido o façam, sujeito às seguintes condições:

O aviso de direitos autorais acima e este aviso de permissão devem ser incluídos em todas as cópias ou partes substanciais do Software.

O SOFTWARE É FORNECIDO "NO ESTADO EM QUE SE ENCONTRA", SEM GARANTIA DE QUALQUER TIPO, EXPRESSA OU IMPLÍCITA, INCLUINDO, MAS NÃO SE LIMITANDO ÀS GARANTIAS DE COMERCIALIZAÇÃO, ADEQUAÇÃO A UM DETERMINADO FIM E NÃO VIOLAÇÃO. EM NENHUMA HIPÓTESE OS AUTORES OU TITULARES DOS DIREITOS AUTORAIS SERÃO RESPONSÁVEIS POR QUALQUER RECLAMAÇÃO, DANOS OU OUTRA RESPONSABILIDADE, SEJA EM UMA AÇÃO CONTRATUAL, ATO ILÍCITO OU DE OUTRA FORMA, DECORRENTE DE, DE OU EM CONEXÃO COM O SOFTWARE OU O USO OU OUTRAS NEGOCIAÇÕES NO SOFTWARE.
