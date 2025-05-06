# app/main.py
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from app.routers import tasks
from app.routers import auth
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection
from app.db.user_crud import create_user_indexes
from app.db.task_crud import create_task_indexes
from app.core.config import settings
import logging
import sys
from loguru import logger as loguru_logger 

# Interceptar logs padrão do Python com Loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

# Configurar Loguru 
loguru_logger.remove() 
loguru_logger.add(
    sys.stderr,
    level="INFO", 
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
# Capturar logs do logging padrão 
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
logger = loguru_logger

# Gerenciador de contexto de vida útil (eventos startup/shutdown)
# Docs: https://fastapi.tiangolo.com/advanced/events/#lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_connection = await connect_to_mongo()
    if db_connection is None:
         logger.critical("Falha fatal ao conectar ao MongoDB na inicialização.")
         yield 
         return

    app.state.db = db_connection
    logger.info("Conectado ao MongoDB.")
    try:
        db_instance = app.state.db
        await create_user_indexes(db_instance)
        await create_task_indexes(db_instance) 
    except Exception as e:
        logger.error(f"Erro durante a criação de índices: {e}", exc_info=True)

    # Permite que a aplicação rode
    yield

    # Código de shutdown (executa ao parar a app)
    await close_mongo_connection()
    logger.info("Conexão com MongoDB fechada.")
    
# Instância FastAPI
app = FastAPI(
    title="SmartTask API",
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

# Inclusões
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth")
app.include_router(tasks.router, prefix=settings.API_V1_STR)


# Endpoint Raiz
@app.get("/", tags=["Root"]) 
async def read_root():
    return {"message": f"Bem-vindo à {settings.PROJECT_NAME}!"}


if __name__ == "__main__":
    import uvicorn
    reload=True # reinicia o servidor automaticamente ao salvar alterações 
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)