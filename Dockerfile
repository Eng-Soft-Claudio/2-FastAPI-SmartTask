# Dockerfile

# --- Estágio 1: Base com Python ---
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Especificar quais pacotes instalar (build-essential e gcc) 
# e limpar cache após a instalação
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc \
  && rm -rf /var/lib/apt/lists/* \
  # Criar usuário não-root para rodar a aplicação
  && useradd --create-home appuser

# --- Estágio 2: Instalar Dependências Python ---
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

# --- Estágio 3: Copiar o Código da Aplicação ---
COPY ./app /app/app
# Ajustar permissões para o usuário não-root
RUN chown -R appuser:appuser /app

# Mudar para usuário não-root
USER appuser

# --- Estágio 4: Expor a Porta e Definir Comando de Execução ---
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]