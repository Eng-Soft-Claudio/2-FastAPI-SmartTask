# tests/test_core_security.py

import pytest
from app.core.security import verify_password, get_password_hash

# Usar uma senha fixa para os testes unitários
TEST_PASSWORD = "senha_super_segura_123"

def test_get_password_hash():
    """Testa se a função get_password_hash retorna uma string não vazia."""
    password_hash = get_password_hash(TEST_PASSWORD)
    assert isinstance(password_hash, str)
    assert len(password_hash) > 0
    assert password_hash != TEST_PASSWORD

def test_verify_password_correct():
    """Testa a verificação com a senha correta."""
    password_hash = get_password_hash(TEST_PASSWORD)
    assert verify_password(TEST_PASSWORD, password_hash) is True

def test_verify_password_incorrect():
    """Testa a verificação com uma senha incorreta."""
    password_hash = get_password_hash(TEST_PASSWORD)
    wrong_password = "senha_incorreta"
    assert verify_password(wrong_password, password_hash) is False

def test_verify_password_invalid_hash():
    """Testa a verificação com um formato de hash inválido."""
    invalid_hash_format = "nao_e_um_hash_bcrypt_valido"
    assert verify_password(TEST_PASSWORD, invalid_hash_format) is False

def test_verify_password_empty_password():
    """Testa a verificação com senha vazia (plain) contra um hash válido."""
    password_hash = get_password_hash(TEST_PASSWORD)
    assert verify_password("", password_hash) is False

def test_get_hash_different_for_same_password():
    """Testa se o hash gerado é diferente a cada vez (devido ao salt)."""
    hash1 = get_password_hash(TEST_PASSWORD)
    hash2 = get_password_hash(TEST_PASSWORD)
    assert hash1 != hash2
    assert verify_password(TEST_PASSWORD, hash1) is True
    assert verify_password(TEST_PASSWORD, hash2) is True