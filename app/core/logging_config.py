# app/core/logging_config.py
import logging
import sys
from loguru import logger as loguru_logger

# Handler para interceptar logs padrão
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while hasattr(frame, "f_code") and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            if frame is None:
                break # Segurança caso frame seja None
            depth += 1

        # Verificar se frame não é None antes de acessar f_code
        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_level: str = "INFO"):
    """Configura o Loguru para interceptar logs padrão."""
    log_level = log_level.upper() # Garante que o nível seja maiúsculo
    loguru_logger.remove() # Remove handlers padrão
    loguru_logger.add(
        sys.stderr,
        level=log_level, # Usa o nível passado como argumento
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True, # Torna assíncrono 
        diagnose=False # Não mostrar variáveis locais no traceback por padrão
    )
    # Configura o logging padrão para usar nosso handler
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Configura loggers de bibliotecas específicas (opcional)
    # logging.getLogger("uvicorn.access").disabled = True # Exemplo: silenciar logs de acesso do uvicorn
    # logging.getLogger("uvicorn.error").propagate = False # Exemplo
    # loguru_logger.disable("httpx") # Exemplo: silenciar logs de debug do httpx

    # Define qual logger será usado globalmente se necessário
    # Neste caso, outros módulos podem continuar usando logging.getLogger()
    # pois o basicConfig acima configura o handler raiz.
    # Alternativamente, poderíamos fazer 'main.logger = loguru_logger'
    # e outros módulos importarem 'from app.main import logger'.