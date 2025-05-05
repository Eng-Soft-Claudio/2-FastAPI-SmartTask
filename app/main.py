# app/main.py

# Importações
import logging
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from app.routers import tasks
from app.routers import auth
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection
from app.db.user_crud import create_user_indexes
from app.db.task_crud import create_task_indexes
from app.core.config import settings

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    return {"message": "Bem-vindo à {settings.PROJECT_NAME}!"}

# Adicione aqui mais endpoints e lógica da aplicação futuramente...

# (Para rodar localmente com Uvicorn, você usará o comando no terminal,
#  mas esta seção é útil se você fosse rodar o script diretamente)
if __name__ == "__main__":
    import uvicorn
    # Roda a aplicação usando o Uvicorn
    # host="0.0.0.0" permite acesso de fora do container/máquina local
    reload=True # reinicia o servidor automaticamente ao salvar alterações 
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)