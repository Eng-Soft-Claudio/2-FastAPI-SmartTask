# app/routers/health.py

# ========================
# --- Importações ---
# ========================
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.db.mongodb_utils import check_mongo_connection
from redis import Redis, RedisError


# ========================
# --- Configuração do Router ---
# ========================
router = APIRouter()


# ========================
# --- Rotas da API ---
# ========================
@router.get("/health", tags=["Health"])
async def health_check():
    # Verifica o status do Redis
    try:
        redis_client = Redis(host='smarttask-redis', port=6379)
        redis_client.ping()
    except RedisError:
        return JSONResponse(content={"status": "error", "message": "Redis não está disponível"}, status_code=503)
    
    # Verifica o status do MongoDB
    if not await check_mongo_connection():
        return JSONResponse(content={"status": "error", "message": "MongoDB não está disponível"}, status_code=503)
    
    return JSONResponse(content={"status": "ok"})
