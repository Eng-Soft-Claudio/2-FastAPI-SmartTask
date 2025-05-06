# app/main.py

# ========================
# --- Importações ---
# ========================
import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware 
from contextlib import asynccontextmanager 

# --- Módulos da Aplicação ---
from app.routers import tasks
from app.routers import auth
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection
from app.db.user_crud import create_user_indexes
from app.db.task_crud import create_task_indexes
from app.core.config import settings
# Importar a função de setup e o InterceptHandler
from app.core.logging_config import setup_logging, InterceptHandler

# ===============================
# --- Configuração de Logging ---
# ===============================

# Chamar a configuração de logging ANTES de qualquer log da aplicação
setup_logging(log_level=settings.LOG_LEVEL)

# Obter um logger para este módulo (main.py)
logger = logging.getLogger(__name__) 


# ==================================
# --- Ciclo de Vida (Lifespan) ---
# ==================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação: conecta ao DB e cria índices no startup,
    e fecha a conexão no shutdown.
    """
    logger.info("Iniciando ciclo de vida da aplicação...")
    db_connection = await connect_to_mongo()

    if db_connection is None:
         logger.critical("Falha fatal ao conectar ao MongoDB na inicialização. App pode não funcionar corretamente.")
         yield 
         logger.info("Encerrando ciclo de vida (conexão DB falhou no início).")
         return 

    # Conexão bem-sucedida, define o estado
    app.state.db = db_connection
    logger.info("Conectado ao MongoDB.")

    # Tenta criar índices
    try:
        db_instance = app.state.db 
        logger.info("Tentando criar/verificar índices...")
        await create_user_indexes(db_instance)
        await create_task_indexes(db_instance)
        logger.info("Criação/verificação de índices concluída.")
    except Exception as e:
        logger.error(f"Erro durante a criação de índices: {e}", exc_info=True)

    # Aplicação pronta para receber requisições
    logger.info("Aplicação iniciada e pronta.")
    yield 

    # Código de Shutdown
    logger.info("Iniciando processo de encerramento...")
    await close_mongo_connection()
    logger.info("Conexão com MongoDB fechada.")
    logger.info("Aplicação encerrada.")


# =========================
# --- Instância FastAPI ---
# =========================
app = FastAPI(
    title=settings.PROJECT_NAME, 
    description="API RESTful para gerenciamento de tarefas com prioridade inteligente.",
    version="0.1.0",
    contact={
        "name": "Eng. Soft. Cláudio",
        "url": "https://www.linkedin.com/in/claudiodelimatosta/",
        "email": "claudiodelimatosta@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan # Define o ciclo de vida
)

# =========================
# --- Middlewares ---
# =========================

# Configurar CORS
if settings.CORS_ALLOWED_ORIGINS: 
    logger.info(f"Configurando CORS para origens: {settings.CORS_ALLOWED_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS, 
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
     logger.warning("Nenhuma origem CORS configurada (settings.CORS_ALLOWED_ORIGINS está vazia).")

# ======================
# --- Rotas (Routers) ---
# ======================
app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["Authentication"]) # Prefixo padrão
app.include_router(tasks.router, prefix=settings.API_V1_STR, tags=["Tasks"]) # Prefixo padrão

# =====================
# --- Endpoint Raiz ---
# =====================
@app.get("/", tags=["Root"])
async def read_root():
    """Endpoint raiz para verificar se a API está online."""
    return {"message": f"Bem-vindo à {settings.PROJECT_NAME}!"}


# =============================
# --- Execução (Uvicorn) ---
# =============================
if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor Uvicorn para desenvolvimento...")
    # 'reload=True' para hot-reload durante desenvolvimento, desativar em produção
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower() 
    )