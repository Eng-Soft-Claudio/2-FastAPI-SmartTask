# script_consolidar_codigo.py (ou o nome que você deu a ele)
"""
Este script percorre uma estrutura de diretórios especificada, identifica
todos os arquivos Python (.py), e consolida seus conteúdos em um único arquivo de texto.

Funcionalidades:
- Ignora diretórios comuns de desenvolvimento (ex: venv, __pycache__, test).
- Gera um índice no início do arquivo de saída, listando todos os arquivos .py
  encontrados, seus caminhos relativos e o número de linhas.
- Anexa o conteúdo completo de cada arquivo .py ao arquivo de saída.
- Lida com arquivos vazios (ignorando-os no índice e conteúdo se não tiverem linhas
  com conteúdo após remover espaços em branco).
- Registra erros caso algum arquivo não possa ser lido.
"""

# ========================
# --- Importações ---
# ========================
import os
import sys

# =====================================
# --- Configurações e Constantes ---
# =====================================

# Caminho para o diretório raiz do projeto a ser analisado.
# Altere este caminho conforme necessário para o seu ambiente.
PASTA_RAIZ_PROJETO = '/media/claudioh4x5w6l7/Desenvolvimento/SmartTask/'

# Nome do arquivo de saída que conterá o índice e o conteúdo consolidado.
NOME_BASE_ARQUIVO_SAIDA = 'global-content.txt'

# Lista de diretórios a serem ignorados durante a varredura.
PASTAS_IGNORADAS = ('venv', '__pycache__', 'descriptive', '.pytest_cache', '.git', '.idea', 'node_modules', '.env')

# Determina o diretório do script atual
# `os.path.abspath` garante que temos um caminho absoluto.
if getattr(sys, 'frozen', False):
    # Caso o script seja empacotado com PyInstaller ou similar
    DIRETORIO_DO_SCRIPT = os.path.dirname(sys.executable)
else:
    DIRETORIO_DO_SCRIPT = os.path.dirname(os.path.abspath(__file__))

# Caminho completo para o arquivo de saída consolidado.
ARQUIVO_SAIDA_CONSOLIDADO = os.path.join(DIRETORIO_DO_SCRIPT, NOME_BASE_ARQUIVO_SAIDA)

# ====================================
# --- Lógica Principal do Script ---
# ====================================

def gerar_consolidado_codigo(pasta_raiz: str, arquivo_saida: str, pastas_ignoradas: tuple):
    """
    Função principal que varre os arquivos, gera o índice e o conteúdo consolidado.

    Args:
        pasta_raiz (str): O caminho absoluto para o diretório raiz do projeto.
        arquivo_saida (str): O nome do arquivo onde o conteúdo consolidado será salvo.
        pastas_ignoradas (tuple): Uma tupla de nomes de pastas a serem ignoradas.
    """
    print(f"Iniciando a varredura de arquivos Python em: {pasta_raiz}")
    caminhos_arquivos_py = []
    indice_arquivos = []

    # --- Primeira Etapa: Coletar todos os caminhos de arquivos .py ---
    for raiz_atual, pastas_atuais, arquivos_atuais in os.walk(pasta_raiz):
        # Modifica a lista de pastas em `os.walk` para pular os diretórios ignorados.
        pastas_atuais[:] = [p for p in pastas_atuais if p not in pastas_ignoradas]

        for nome_arquivo in arquivos_atuais:
            if nome_arquivo.endswith('.py'):
                caminho_completo_arquivo = os.path.join(raiz_atual, nome_arquivo)
                caminhos_arquivos_py.append(caminho_completo_arquivo)

    # Ordena os caminhos dos arquivos alfabeticamente para consistência.
    caminhos_arquivos_py.sort()
    print(f"Encontrados {len(caminhos_arquivos_py)} arquivos .py.")

    # --- Segunda Etapa: Gerar o índice dos arquivos ---
    # Este passo também verifica se os arquivos estão vazios (em termos de conteúdo real).
    print("Gerando índice dos arquivos...")
    for caminho_abs in caminhos_arquivos_py:
        caminho_rel = os.path.relpath(caminho_abs, pasta_raiz)
        try:
            with open(caminho_abs, 'r', encoding='utf-8') as f_temp:
                linhas_arquivo = f_temp.readlines()
            # Considera o arquivo para inclusão apenas se tiver alguma linha com conteúdo.
            linhas_com_conteudo = [l for l in linhas_arquivo if l.strip()]
            if not linhas_com_conteudo:
                print(f"  - Ignorando arquivo vazio (sem conteúdo): {caminho_rel}")
                continue # Pula para o próximo arquivo.
            indice_arquivos.append((caminho_rel, len(linhas_arquivo)))
        except Exception as e:
            print(f"  - Erro ao processar {caminho_rel} para o índice: {e}")
            indice_arquivos.append((caminho_rel, f"Erro ao ler/processar: {e}"))
    print("Índice gerado.")

    # --- Terceira Etapa: Escrever o arquivo de saída consolidado ---
    print(f"Escrevendo o arquivo de saída: {arquivo_saida}")
    try:
        with open(arquivo_saida, 'w', encoding='utf-8') as f_saida:
            # Escreve o cabeçalho do índice.
            f_saida.write("====================================\n")
            f_saida.write("   ÍNDICE DOS ARQUIVOS PYTHON\n")
            f_saida.write("====================================\n\n")

            # Escreve cada entrada do índice.
            for i, (caminho_rel_idx, info_idx) in enumerate(indice_arquivos, 1):
                if isinstance(info_idx, int):
                    f_saida.write(f"{i}. {caminho_rel_idx:<70} ({info_idx} linhas)\n")
                else: # Caso de erro ao ler o arquivo.
                    f_saida.write(f"{i}. {caminho_rel_idx:<70} [{info_idx}]\n")

            f_saida.write("\n" + "=" * 70 + "\n\n") # Separador entre índice e conteúdo.

            # Escreve o conteúdo de cada arquivo.
            for i, (caminho_rel_cont, info_cont) in enumerate(indice_arquivos, 1):
                f_saida.write(f"\n{'-'*3} {i}. INÍCIO DE: {caminho_rel_cont} {'-'*3}\n")
                if isinstance(info_cont, int): # Se não houve erro ao processar para o índice.
                    try:
                        caminho_abs_cont = os.path.join(pasta_raiz, caminho_rel_cont)
                        with open(caminho_abs_cont, 'r', encoding='utf-8') as f_conteudo:
                            # Lê e escreve diretamente as linhas, mantendo a formatação original.
                            f_saida.writelines(f_conteudo.readlines())
                    except Exception as e:
                        f_saida.write(f"\n[!!! ERRO AO LER O CONTEÚDO DE {caminho_rel_cont}: {e} !!!]\n")
                else: # Se houve erro registrado no índice, repete a mensagem de erro.
                    f_saida.write(f"\n[!!! ERRO REGISTRADO PARA {caminho_rel_cont}: {info_cont} !!!]\n")
                f_saida.write(f"{'-'*3} FIM DE: {caminho_rel_cont} {'-'*70}\n")
        print(f"Arquivo '{arquivo_saida}' gerado com sucesso!")
    except Exception as e_global:
        print(f"Erro GERAL ao tentar escrever o arquivo de saída '{arquivo_saida}': {e_global}")

# --- Bloco de Execução Principal ---
if __name__ == "__main__":
    # Verifica se o caminho raiz existe para evitar erros.
    if not os.path.isdir(PASTA_RAIZ_PROJETO):
        print(f"ERRO: O caminho raiz '{PASTA_RAIZ_PROJETO}' não existe ou não é um diretório.")
        print("Por favor, verifique a constante PASTA_RAIZ_PROJETO no script.")
    else:
        gerar_consolidado_codigo(PASTA_RAIZ_PROJETO, ARQUIVO_SAIDA_CONSOLIDADO, PASTAS_IGNORADAS)