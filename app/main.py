# app/main.py
"""
Ponto de entrada principal e configuração da aplicação FastAPI SmartTask.
Define a instância da aplicação, middlewares, rotas, ciclo de vida (lifespan)
e o endpoint raiz. Também inclui o setup de logging inicial.
"""

# ========================
# --- Importações ---
# ========================
import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# --- Módulos da Aplicação ---
from app.routers import tasks, auth, health
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection
from app.db.user_crud import create_user_indexes
from app.db.task_crud import create_task_indexes
from app.core.config import Settings, settings 
from app.core.logging_config import setup_logging 

# ========================
# --- Configuração de Logging ---
# ========================
setup_logging(log_level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# ========================
# --- Função de Setup do Middleware CORS ---
# ========================
def _setup_cors_middleware(app_instance: FastAPI, current_settings: Settings):
    """Configura o middleware CORS para a aplicação."""
    if current_settings.CORS_ALLOWED_ORIGINS:
        logger.info(f"Configurando CORS para origens: {current_settings.CORS_ALLOWED_ORIGINS}")
        app_instance.add_middleware(
            CORSMiddleware,
            allow_origins=current_settings.CORS_ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        logger.warning(
            "Nenhuma origem CORS configurada (settings.CORS_ALLOWED_ORIGINS está vazia). "
            "API pode não ser acessível de frontends em outros domínios."
        )

# ========================
# --- Ciclo de Vida (Lifespan) ---
# ========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.

    Conecta ao MongoDB e cria índices no startup.
    Fecha a conexão com o MongoDB no shutdown.
    """
    logger.info("Iniciando ciclo de vida da aplicação...")
    db_connection = await connect_to_mongo()

    if db_connection is None:
        logger.critical("Falha fatal ao conectar ao MongoDB na inicialização. App pode não funcionar corretamente.")
        yield
        logger.info("Encerrando ciclo de vida (conexão DB falhou no início).")
        return

    app.state.db = db_connection 
    logger.info("Conectado ao MongoDB.")

    try:
        db_instance = app.state.db
        logger.info("Tentando criar/verificar índices...")
        await create_user_indexes(db_instance)
        await create_task_indexes(db_instance)
        logger.info("Criação/verificação de índices concluída.")
    except Exception as e:
        logger.error(f"Erro durante a criação de índices: {e}", exc_info=True)

    logger.info("Aplicação iniciada e pronta.") # pragma: no cover
    yield # pragma: no cover

    # Código abaixo é executado no shutdown da aplicação
    logger.info("Iniciando processo de encerramento...")
    await close_mongo_connection()
    logger.info("Conexão com MongoDB fechada.")
    logger.info("Aplicação encerrada.")

# ========================
# --- Instância FastAPI ---
# ========================
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
    lifespan=lifespan
)

# ========================
# --- Configuração de Middlewares ---
# ========================
_setup_cors_middleware(app, settings)

# ========================
# --- Rotas (Routers) ---
# ========================
app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["Authentication"])
app.include_router(tasks.router, prefix=settings.API_V1_STR, tags=["Tasks"])
app.include_router(health.router)

# ========================
# --- Endpoint Raiz ---
# ========================
@app.get("/", tags=["Root"])
async def read_root():
    """Endpoint raiz para verificar se a API está online."""
    return {"message": f"Bem-vindo à {settings.PROJECT_NAME}!"}

# ========================
# --- Execução (Uvicorn) ---
# ========================
if __name__ == "__main__": # pragma: no cover
    import uvicorn # pragma: no cover
    logger.info("Iniciando servidor Uvicorn para desenvolvimento...") # pragma: no cover
    uvicorn.run( # pragma: no cover
        "main:app", # pragma: no cover
        host="0.0.0.0", # pragma: no cover
        port=8000, # pragma: no cover
        reload=True, # pragma: no cover
        log_level=settings.LOG_LEVEL.lower() # pragma: no cover
    )