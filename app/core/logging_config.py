# app/core/logging_config.py
"""
Este módulo configura o sistema de logging da aplicação utilizando Loguru.
Inclui um InterceptHandler para redirecionar logs do sistema de logging
padrão do Python para o Loguru, garantindo um formato de log consistente.
"""

# ========================
# --- Importações ---
# ========================
import logging
import sys
from loguru import logger as loguru_logger

# ========================
# --- Handler de Intercepção ---
# ========================
class InterceptHandler(logging.Handler):
    """
    Handler do `logging` que redireciona mensagens para o Loguru.
    Permite que logs emitidos por bibliotecas que usam o `logging` padrão
    sejam formatados e gerenciados pelo Loguru.
    """
    def emit(self, record: logging.LogRecord) -> None:
        """
        Recebe um registro de log padrão e o envia para o Loguru,
        tentando manter o nível de log e informações de rastreamento.
        """
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while hasattr(frame, "f_code") and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back # pragma: no cover
            if frame is None: # pragma: no cover
                break # pragma: no cover
            depth += 1 # pragma: no cover

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

# ========================
# --- Função de Setup ---
# ========================
def setup_logging(log_level: str = "INFO"):
    """
    Configura o sistema de logging global da aplicação.

    - Remove handlers padrão do Loguru para evitar duplicação.
    - Adiciona um novo handler Loguru para `sys.stderr` com formato e nível configuráveis.
    - Configura o `logging` padrão do Python para usar o `InterceptHandler`,
      canalizando todos os logs para o Loguru.
    - Desabilita ou ajusta propagação para loggers específicos (Uvicorn, httpx)
      para evitar logs excessivos ou duplicados.

    Args:
        log_level: Nível mínimo de log a ser exibido (ex: "INFO", "DEBUG").
    """
    log_level = log_level.upper()

    loguru_logger.remove() # Limpa handlers pré-existentes do Loguru

    # Adiciona o handler principal para stderr
    loguru_logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True,    # Torna o logging assíncrono e seguro para threads/processos
        diagnose=False   # Desabilita diagnósticos detalhados de exceções por padrão
    )

    # Configura o logging padrão do Python para usar o InterceptHandler
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Ajustes específicos para loggers de bibliotecas comuns
    logging.getLogger("uvicorn.access").disabled = True # Desabilita logs de acesso do Uvicorn
    logging.getLogger("uvicorn.error").propagate = False # Evita duplicação de erros do Uvicorn

    # Desabilita logs de httpx, pois podem ser muito verbosos.
    # Se precisar depurar httpx, comente ou ajuste esta linha.
    loguru_logger.disable("httpx")