# tests/test_core_security.py
"""
Este módulo contém testes unitários para as funções de segurança relacionadas
a senhas, definidas em `app.core.security`.

As funções testadas são:
- `get_password_hash`: Para gerar o hash de uma senha.
- `verify_password`: Para verificar uma senha em texto puro contra um hash existente.

Os testes cobrem cenários de sucesso, falha (senha incorreta, hash inválido)
e a propriedade de que hashes diferentes são gerados para a mesma senha
devido ao uso de "salt".
"""

# ========================
# --- Importações ---
# ========================
import pytest 

# --- Módulos da Aplicação ---
from app.core.security import get_password_hash, verify_password

# =====================================
# --- Constantes de Teste ---
# =====================================
# Uma senha fixa usada em vários testes para consistência.
TEST_PLAIN_PASSWORD = "!@#$_uma_SENHA_extremamente_SEGURA_para_TESTES_!@#$"

# =================================================
# --- Testes para `get_password_hash` ---
# =================================================

def test_get_password_hash_returns_non_empty_string_different_from_plain_password():
    """
    Testa se a função `get_password_hash`:
    1. Retorna uma string.
    2. A string não é vazia.
    3. O hash retornado é diferente da senha original em texto puro.
    """
    print(f"\nTeste: get_password_hash com senha: '{TEST_PLAIN_PASSWORD}'")

    # --- Act: Gerar o hash da senha ---
    generated_hash = get_password_hash(TEST_PLAIN_PASSWORD)
    print(f"  Hash gerado: '{generated_hash[:20]}...' (parcial para brevidade)")

    # --- Assert: Verificar as propriedades do hash ---
    assert isinstance(generated_hash, str), "O hash retornado não é uma string."
    assert len(generated_hash) > 0, "O hash retornado está vazio."
    assert generated_hash != TEST_PLAIN_PASSWORD, "O hash retornado é igual à senha original (não deveria)."
    print("  Sucesso: Hash gerado é uma string não vazia e diferente da senha original.")

def test_get_password_hash_generates_different_hashes_for_same_password_due_to_salt():
    """
    Testa se `get_password_hash` gera hashes diferentes para a mesma senha
    quando chamada múltiplas vezes. Isso demonstra o uso correto de "salts"
    na função de hashing.

    Também verifica se ambos os hashes gerados são válidos para a senha original.
    """
    print(f"\nTeste: get_password_hash gera hashes diferentes para a mesma senha: '{TEST_PLAIN_PASSWORD}'")

    # --- Act: Gerar dois hashes para a mesma senha ---
    hash1 = get_password_hash(TEST_PLAIN_PASSWORD)
    hash2 = get_password_hash(TEST_PLAIN_PASSWORD)
    print(f"  Hash 1: '{hash1[:20]}...'")
    print(f"  Hash 2: '{hash2[:20]}...'")

    # --- Assert: Verificar as propriedades ---
    assert hash1 != hash2, "Os dois hashes gerados para a mesma senha são iguais (o salt pode não estar funcionando)."
    assert verify_password(TEST_PLAIN_PASSWORD, hash1) is True, "O primeiro hash não pôde ser verificado com a senha original."
    assert verify_password(TEST_PLAIN_PASSWORD, hash2) is True, "O segundo hash não pôde ser verificado com a senha original."
    print("  Sucesso: Hashes diferentes foram gerados e ambos são válidos.")

# =================================================
# --- Testes para `verify_password` ---
# =================================================

def test_verify_password_with_correct_password_succeeds():
    """
    Testa se `verify_password` retorna `True` quando a senha correta em
    texto puro é fornecida para um hash correspondente.
    """
    print(f"\nTeste: verify_password com senha correta: '{TEST_PLAIN_PASSWORD}'")
    # --- Arrange: Gerar um hash para a senha de teste ---
    password_hash = get_password_hash(TEST_PLAIN_PASSWORD)
    print(f"  Hash para verificação: '{password_hash[:20]}...'")

    # --- Act & Assert: Verificar a senha correta ---
    is_valid = verify_password(TEST_PLAIN_PASSWORD, password_hash)
    assert is_valid is True, "A verificação com a senha correta falhou (deveria ser True)."
    print("  Sucesso: Verificação com senha correta retornou True.")

def test_verify_password_with_incorrect_password_fails():
    """
    Testa se `verify_password` retorna `False` quando uma senha incorreta
    em texto puro é fornecida para um hash.
    """
    incorrect_test_password = "esta_e_uma_senha_errada_!"
    print(f"\nTeste: verify_password com senha incorreta: '{incorrect_test_password}'")
    # --- Arrange: Gerar um hash para a senha de teste original ---
    password_hash = get_password_hash(TEST_PLAIN_PASSWORD) 
    print(f"  Hash (da senha correta '{TEST_PLAIN_PASSWORD}'): '{password_hash[:20]}...'")

    # --- Act & Assert: Verificar a senha incorreta ---
    is_valid = verify_password(incorrect_test_password, password_hash)
    assert is_valid is False, "A verificação com senha incorreta passou (deveria ser False)."
    print("  Sucesso: Verificação com senha incorreta retornou False.")

def test_verify_password_with_empty_plain_password_fails():
    """
    Testa se `verify_password` retorna `False` quando uma senha vazia
    em texto puro é fornecida, mesmo contra um hash de uma senha não vazia.
    """
    empty_password = ""
    print(f"\nTeste: verify_password com senha vazia em texto puro ('{empty_password}')")
    # --- Arrange: Gerar um hash para a senha de teste original (não vazia) ---
    password_hash = get_password_hash(TEST_PLAIN_PASSWORD)
    print(f"  Hash (da senha correta '{TEST_PLAIN_PASSWORD}'): '{password_hash[:20]}...'")

    # --- Act & Assert: Verificar a senha vazia ---
    is_valid = verify_password(empty_password, password_hash)
    assert is_valid is False, "A verificação com senha vazia passou (deveria ser False)."
    print("  Sucesso: Verificação com senha vazia retornou False.")

def test_verify_password_with_plain_password_against_empty_hash_string_fails():
    """
    Testa se `verify_password` retorna `False` (ou levanta uma exceção esperada,
    dependendo da implementação de passlib) quando a string de hash fornecida
    é vazia.
    """
    empty_hash_string = ""
    print(f"\nTeste: verify_password com string de hash vazia ('{empty_hash_string}')")

    # --- Act & Assert: Verificar senha contra hash vazio ---
    is_valid = verify_password(TEST_PLAIN_PASSWORD, empty_hash_string)
    assert is_valid is False, \
        "A verificação contra um hash vazio deveria retornar False (ou a biblioteca pode ter outro comportamento)."
    print("  Sucesso: Verificação contra hash vazio retornou False.")

def test_verify_password_with_invalid_hash_format_fails():
    """
    Testa se `verify_password` retorna `False` (ou lida graciosamente)
    quando a string de hash fornecida não é um formato de hash bcrypt válido
    reconhecido pela biblioteca (passlib).
    """
    invalid_hash_string = "isto_claramente_nao_e_um_hash_bcrypt_valido_$"
    print(f"\nTeste: verify_password com formato de hash inválido: '{invalid_hash_string}'")

    # --- Act & Assert: Verificar senha contra hash inválido ---
    is_valid = verify_password(TEST_PLAIN_PASSWORD, invalid_hash_string)
    assert is_valid is False, \
        "A verificação contra um hash de formato inválido deveria retornar False."
    print("  Sucesso: Verificação contra hash de formato inválido retornou False.")