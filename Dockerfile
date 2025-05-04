# Dockerfile

# --- Estágio 1: Base com Python ---
# Usar uma imagem oficial Python como base.
# Escolher uma versão específica (ex: 3.10) e preferencialmente uma versão 'slim' para tamanho menor.
# Docs: https://hub.docker.com/_/python
FROM python:3.10-slim AS base

# Definir variáveis de ambiente para Python (boas práticas)
# PYTHONDONTWRITEBYTECODE: Impede Python de escrever arquivos .pyc
# PYTHONUNBUFFERED: Garante que prints/logs apareçam imediatamente no Docker
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Definir o diretório de trabalho dentro do contêiner
WORKDIR /app

# Instalar dependências do sistema (se necessário - por agora, talvez não)
# Ex: Se usássemos bibliotecas que dependem de C, poderíamos precisar de build-essentials
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*


# --- Estágio 2: Instalar Dependências Python ---
# Copiar *apenas* o arquivo de dependências primeiro
# Isso aproveita o cache do Docker: se requirements.txt não mudar, não reinstala tudo
COPY requirements.txt .

# Instalar dependências usando pip
# --no-cache-dir economiza espaço na imagem
# --upgrade pip garante que estamos com a versão mais recente
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt


# --- Estágio 3: Copiar o Código da Aplicação ---
# Copiar todo o diretório da aplicação 'app' para o diretório de trabalho '/app/app' no contêiner
# ASSUMINDO que seu código da aplicação está dentro de uma pasta 'app' na raiz do projeto.
COPY ./app /app/app
# Se algum outro arquivo for necessário (ex: .env.example, outros scripts), copie-os também


# --- Estágio 4: Expor a Porta e Definir Comando de Execução ---
# Expor a porta que o Uvicorn usará dentro do contêiner (ex: 8000)
EXPOSE 8000

# Comando padrão para executar a aplicação quando o contêiner iniciar
# Usamos uvicorn diretamente, especificando o host 0.0.0.0 para aceitar conexões externas
# e apontando para a instância 'app' dentro de 'app.main'
# NÃO usamos --reload em produção!
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]