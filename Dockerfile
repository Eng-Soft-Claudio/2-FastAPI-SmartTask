# Dockerfile

# --- Estágio 1: Base com Python ---
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

COPY ./app /app
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Comando padrão (API)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Estágio 3: Testes ---
FROM base AS test
# É uma boa prática instalar pacotes como root ou ajustar permissões
USER root
RUN pip install --no-cache-dir pytest pytest-cov
USER appuser
# Se __init__.py existe em app/, --cov=app deve funcionar quando executado de /app.
# Caso contrário, --cov=. seria uma alternativa se você não tem __init__.py
CMD ["pytest", "--maxfail=5", "--disable-warnings", "--cov=app", "--cov-report=term-missing"]