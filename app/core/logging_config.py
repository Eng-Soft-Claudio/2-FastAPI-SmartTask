# app/core/logging_config.py

# ========================
# --- Importações ---
# ========================
import logging
import sys
from loguru import logger as loguru_logger 

# ============================
# --- Handler de Intercepção ---
# ============================
class InterceptHandler(logging.Handler):
    """
    Handler do logging que redireciona mensagens para o Loguru.
    """
    def emit(self, record: logging.LogRecord) -> None:
        """
        Recebe um registro de log padrão e o envia para o Loguru.
        """
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno 

        frame, depth = logging.currentframe(), 2
        while hasattr(frame, "f_code") and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            if frame is None: # pragma: no cover
                break # pragma: no cover
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# ============================
# --- Função de Setup ---
# ============================
def setup_logging(log_level: str = "INFO"):
    """
    Configura o sistema de logging usando Loguru.

    - Remove handlers padrão do Loguru.
    - Adiciona um handler para stderr com nível e formato configuráveis.
    - Configura o logging padrão do Python para usar o InterceptHandler.

    Args:
        log_level: O nível mínimo de log a ser exibido (ex: "DEBUG", "INFO").
    """
    log_level = log_level.upper()

    loguru_logger.remove()

    loguru_logger.add(
        sys.stderr,
        level=log_level,              
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True,
        diagnose=False                
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").propagate = False
    loguru_logger.disable("httpx")