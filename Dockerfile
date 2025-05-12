# Dockerfile

# --- Estágio 1: Base com Python ---
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /project_root
ENV PYTHONPATH=/project_root

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home appuser

COPY requirements.txt . 
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

COPY ./app /project_root/app     
COPY ./tests /project_root/tests 

# Mude a propriedade de /project_root (que contém app e tests)
RUN chown -R appuser:appuser /project_root

USER appuser

EXPOSE 8000

# Comando padrão (API) - agora deve encontrar app.main
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Estágio 3: Testes ---
FROM base AS test
WORKDIR /project_root

USER root
RUN pip install --no-cache-dir pytest pytest-cov
USER appuser
