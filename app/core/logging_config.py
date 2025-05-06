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
        # Tenta obter o nível de log do Loguru correspondente
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            # Usa o número do nível se não houver correspondência
            level = record.levelno 

        # Encontra o frame correto na stack para exibir o nome do arquivo/linha original
        frame, depth = logging.currentframe(), 2
        while hasattr(frame, "f_code") and frame.f_code.co_filename == logging.__file__:
            # Evita mostrar o próprio arquivo de logging como origem
            frame = frame.f_back
            # Segurança para evitar loop infinito ou erro se a stack for inesperada
            if frame is None:
                break
            depth += 1

        # Envia a mensagem para o Loguru, preservando informações de exceção
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
    # Garante que o nível de log esteja em maiúsculas
    log_level = log_level.upper()

    # Remove quaisquer handlers pré-configurados do Loguru para ter controle total
    loguru_logger.remove()

    # Adiciona um handler para enviar logs para a saída de erro padrão (terminal)
    loguru_logger.add(
        # Sink: Saída de erro padrão
        sys.stderr,
        # Nível mínimo a ser logado                   
        level=log_level,              
        # Formato do Log: inclui tempo, nível, nome do logger, função, linha e mensagem
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        # Torna o logging assíncrono
        enqueue=True,
        # Não incluir automaticamente variáveis locais nos tracebacks             
        diagnose=False                
    )

    # Configura o sistema de logging padrão do Python:
    # - handlers=[InterceptHandler()]: Usa nosso handler customizado para capturar logs padrão.
    # - level=0: Captura TUDO do logging padrão (Loguru filtrará pelo seu `level` depois).
    # - force=True: Substitui qualquer configuração de logging padrão existente.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").propagate = False
    loguru_logger.disable("httpx")