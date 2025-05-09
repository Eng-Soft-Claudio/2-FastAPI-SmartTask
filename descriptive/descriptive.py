# descriptive/descriptive.py
"""
Este script varre recursivamente uma estrutura de diretórios a partir de um caminho raiz,
identifica todos os arquivos `.py`, e gera um arquivo de saída com estilo de **livro**.

O arquivo de saída possui:
- Uma capa e um sumário (índice) com todos os arquivos rastreados.
- Cada arquivo é tratado como um capítulo, com separadores e numeração.
- Arquivos vazios são ignorados.
- Em caso de erro de leitura, uma mensagem é registrada no local do capítulo correspondente.

Diretórios comuns de desenvolvimento (como venv, __pycache__, etc.) são ignorados.
"""

import os
import sys

# =========================
# --- Configurações ---
# =========================

# Caminho absoluto para o diretório raiz do projeto.
PASTA_RAIZ_PROJETO = '/media/claudioh4x5w6l7/Desenvolvimento/SmartTask/'

# Nome do arquivo de saída
NOME_BASE_ARQUIVO_SAIDA = 'livro_codigo_python.txt'

# Diretórios a serem ignorados durante a varredura
PASTAS_IGNORADAS = (
    'venv', '__pycache__', 'descriptive', '.pytest_cache',
    '.git', '.idea', 'node_modules', '.env'
)

# Caminho do diretório onde o script está localizado
if getattr(sys, 'frozen', False):
    DIRETORIO_DO_SCRIPT = os.path.dirname(sys.executable)
else:
    DIRETORIO_DO_SCRIPT = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_SAIDA_CONSOLIDADO = os.path.join(DIRETORIO_DO_SCRIPT, NOME_BASE_ARQUIVO_SAIDA)

# ===============================
# --- Função Principal ---
# ===============================

def gerar_livro_codigo(pasta_raiz: str, arquivo_saida: str, pastas_ignoradas: tuple):
    """
    Varre o diretório raiz do projeto e gera um arquivo no formato de livro contendo
    os códigos Python organizados em capítulos.

    Args:
        pasta_raiz (str): Caminho absoluto para a raiz do projeto.
        arquivo_saida (str): Caminho completo do arquivo de saída a ser gerado.
        pastas_ignoradas (tuple): Diretórios que devem ser ignorados na varredura.

    O arquivo de saída terá:
        - Uma capa com título
        - Um sumário (índice) com os nomes dos arquivos
        - Um capítulo para cada arquivo, com o código formatado
    """
    print(f"Iniciando varredura em: {pasta_raiz}")
    caminhos_arquivos = []
    capitulos = []

    # Coleta os caminhos de todos os arquivos .py
    for raiz, pastas, arquivos in os.walk(pasta_raiz):
        pastas[:] = [p for p in pastas if p not in pastas_ignoradas]
        for arquivo in arquivos:
            if arquivo.endswith('.py'):
                caminho_abs = os.path.join(raiz, arquivo)
                caminhos_arquivos.append(caminho_abs)

    caminhos_arquivos.sort()
    print(f"Total de arquivos .py encontrados: {len(caminhos_arquivos)}")

    # Processa os arquivos e prepara os capítulos
    for caminho_abs in caminhos_arquivos:
        caminho_rel = os.path.relpath(caminho_abs, pasta_raiz)
        try:
            with open(caminho_abs, 'r', encoding='utf-8') as f:
                linhas = f.readlines()

            if not any(l.strip() for l in linhas):
                print(f"  - Ignorado (vazio): {caminho_rel}")
                continue

            capitulos.append({
                'titulo': caminho_rel,
                'linhas': linhas
            })
        except Exception as e:
            print(f"  - Erro ao ler {caminho_rel}: {e}")
            capitulos.append({
                'titulo': caminho_rel,
                'linhas': [f"# ERRO AO LER ARQUIVO: {e}\n"]
            })

    print("Gerando arquivo final em formato de livro...")

    try:
        with open(arquivo_saida, 'w', encoding='utf-8') as f_out:
            escrever_capa_e_sumario(f_out, capitulos)
            escrever_capitulos(f_out, capitulos)
        print(f"Arquivo '{arquivo_saida}' gerado com sucesso no formato de livro.")
    except Exception as e:
        print(f"ERRO ao escrever o arquivo final: {e}")


def escrever_capa_e_sumario(arquivo, capitulos: list):
    """
    Escreve a capa e o sumário no arquivo de saída.

    Args:
        arquivo (file object): Objeto de arquivo já aberto para escrita.
        capitulos (list): Lista de dicionários com os capítulos a serem escritos.
    """
    arquivo.write("=" * 80 + "\n")
    arquivo.write("LIVRO DO CÓDIGO-FONTE DO PROJETO\n")
    arquivo.write("=" * 80 + "\n\n")

    arquivo.write("SUMÁRIO\n")
    arquivo.write("-" * 80 + "\n")
    for i, cap in enumerate(capitulos, 1):
        arquivo.write(f"Capítulo {i}: {cap['titulo']}\n")
    arquivo.write("\n\n")


def escrever_capitulos(arquivo, capitulos: list):
    """
    Escreve os capítulos (conteúdo dos arquivos) no arquivo de saída.

    Args:
        arquivo (file object): Objeto de arquivo já aberto para escrita.
        capitulos (list): Lista de dicionários com os capítulos e seu conteúdo.
    """
    for i, cap in enumerate(capitulos, 1):
        arquivo.write("=" * 80 + "\n")
        arquivo.write(f"Capítulo {i}: {cap['titulo']}\n")
        arquivo.write("=" * 80 + "\n\n")
        arquivo.writelines(cap['linhas'])
        arquivo.write("\n\n")


# ========================
# --- Execução ---
# ========================
if __name__ == "__main__":
    if not os.path.isdir(PASTA_RAIZ_PROJETO):
        print(f"ERRO: Caminho inválido: {PASTA_RAIZ_PROJETO}")
    else:
        gerar_livro_codigo(PASTA_RAIZ_PROJETO, ARQUIVO_SAIDA_CONSOLIDADO, PASTAS_IGNORADAS)
