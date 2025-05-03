import os

# Caminho para a raiz do projeto
pasta_raiz = '/media/claudioh4x5w6l7/Desenvolvimento/SmartTask/app'

# Nome do arquivo final
arquivo_saida = 'conteudo.txt'

# Lista de arquivos válidos
caminhos_arquivos = []

# Caminhar pelas subpastas, ignorando venv e __pycache__
for raiz, pastas, arquivos in os.walk(pasta_raiz):
    pastas[:] = [p for p in pastas if p not in ('venv', '__pycache__')]
    for nome in arquivos:
        if nome.endswith('.py'):
            caminho_completo = os.path.join(raiz, nome)
            caminhos_arquivos.append(caminho_completo)

# Ordena os caminhos alfabeticamente
caminhos_arquivos.sort()

# Gera o arquivo de saída
with open(arquivo_saida, 'w', encoding='utf-8') as saida:
    for caminho in caminhos_arquivos:
        caminho_relativo = os.path.relpath(caminho, pasta_raiz)
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                linhas = f.readlines()
                linhas_limpa = [l for l in linhas if l.strip()]
            if not linhas_limpa:
                continue 

            num_linhas = len(linhas)
            saida.write(f"\n--- Início de {caminho_relativo} ({num_linhas} linhas) ---\n")
            saida.writelines(linhas)
            saida.write(f"--- Fim de {caminho_relativo} ---\n")

        except Exception as e:
            saida.write(f"[Erro ao ler {caminho_relativo}: {e}]\n")
