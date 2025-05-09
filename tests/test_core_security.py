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
from typing import Optional
from venv import logger
import pytest
from datetime import datetime, timedelta, timezone
from jose import ExpiredSignatureError, jwt
import uuid


# --- Módulos da Aplicação ---
from app.core.config import settings
from app.core.security import  ALGORITHM, decode_token, get_password_hash, verify_password, create_access_token

# =====================================
# --- Constantes de Teste ---
# =====================================
TEST_PLAIN_PASSWORD = "!@#$_uma_SENHA_extremamente_SEGURA_para_TESTES_!@#$"
TEST_USER_ID_JWT = str(uuid.uuid4())
TEST_USERNAME_JWT = "test_jwt_user"
CUSTOM_EXPIRATION_MINUTES = 15

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

# =================================================
# --- Testes para JWT (create_access_token, decode_token) ---
# =================================================

def test_create_access_token_with_custom_expires_delta():
    """
    Testa se `create_access_token` utiliza o `expires_delta` fornecido
    para definir o tempo de expiração do token.
    Cobre a linha onde `expire = datetime.now(timezone.utc) + expires_delta` é executada.
    """
    print(f"\nTeste: create_access_token com expires_delta customizado")
    custom_delta = timedelta(minutes=CUSTOM_EXPIRATION_MINUTES)
    
    # --- Act: Criar o token com expires_delta customizado ---
    start_time = datetime.now(timezone.utc)
    token = create_access_token(
        subject=TEST_USER_ID_JWT,
        username=TEST_USERNAME_JWT,
        expires_delta=custom_delta
    )
    end_time = datetime.now(timezone.utc)
    print(f"  Token gerado: '{token[:20]}...'")

    # --- Assert: Decodificar e verificar o payload e a expiração ---
    assert token is not None, "Token não deveria ser None."
    assert isinstance(token, str), "Token deveria ser uma string."
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        print(f"  Payload decodificado: {payload}")
        expected_sub = str(TEST_USER_ID_JWT)
        assert payload.get("sub") == expected_sub, \
            f"Claim 'sub' incorreto. Esperado: {expected_sub}, Obtido: {payload.get('sub')}"
        assert payload.get("username") == TEST_USERNAME_JWT, \
            f"Claim 'username' incorreto. Esperado: {TEST_USERNAME_JWT}, Obtido: {payload.get('username')}"
        exp_timestamp = payload.get("exp")
        assert exp_timestamp is not None, "Claim 'exp' não encontrado no token."
        expected_expire_earliest = start_time + custom_delta
        expected_expire_latest = end_time + custom_delta
        token_expiration_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        assert expected_expire_earliest - timedelta(seconds=5) <= token_expiration_time <= expected_expire_latest + timedelta(seconds=5), \
            f"Tempo de expiração fora do esperado. Esperado ~{start_time + custom_delta}, Obtido: {token_expiration_time}"
        print(f"  Sucesso: Token criado com expires_delta customizado e claims corretos.")
    except jwt.JWTError as e:
        pytest.fail(f"Falha ao decodificar o token gerado: {e}")

def test_decode_token_with_expired_token_returns_none_and_logs(caplog): 
    """
    Testa se `decode_token` retorna `None` e registra um log informativo
    quando um token JWT sintaticamente válido, mas expirado, é fornecido.
    Cobre as linhas 134-135 (logger.info e return None dentro da verificação de expiração).
    """
    print(f"\nTeste: decode_token com token expirado")
    
    # --- Arrange: Criar um token que já está expirado ---
    expired_delta = timedelta(hours=-1)
    expire_time = datetime.now(timezone.utc) + expired_delta
    to_encode = {
        "exp": expire_time, 
        "sub": str(TEST_USER_ID_JWT),
        "username": TEST_USERNAME_JWT,
    }
    expired_token = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    print(f"  Token expirado gerado: '{expired_token[:20]}...'")

    # --- Act: Tentar decodificar o token expirado ---

    decoded_payload = decode_token(expired_token)

    # --- Assert: Verificar se o resultado é None e o log foi feito ---
    assert decoded_payload is None, "Token expirado deveria resultar em None."
    
    log_messages = [record.getMessage() for record in caplog.records if record.name == 'app.core.security']
    assert any("Token JWT expirado (verificação dupla)." in message for message in log_messages), \
        "Mensagem de log para token expirado não encontrada."
    print("  Sucesso: decode_token retornou None para token expirado e logou a informação.")

def test_decode_token_without_expiration_claim(caplog):
    """
    Testa se `decode_token` processa corretamente um token válido
    que não possui o claim 'exp'. Espera-se que retorne os dados do token.
    Cobre o bloco 'else: pass' na verificação de token_data.exp.
    """
    print("\nTeste: decode_token com token válido sem claim 'exp'")
    user_id_as_string = str(uuid.uuid4()) 
    to_encode_no_exp = {
        "sub": user_id_as_string,
        "username": TEST_USERNAME_JWT,
    }
    token_no_exp = jwt.encode(
        to_encode_no_exp, 
        settings.JWT_SECRET_KEY, 
        algorithm=ALGORITHM
    )
    print(f"  Token sem 'exp' gerado: '{token_no_exp[:20]}...'")
    decoded_payload = decode_token(token_no_exp)
    assert decoded_payload is not None, "Token sem 'exp' deveria ser decodificado se 'exp' é opcional."
    assert str(decoded_payload.sub) == user_id_as_string
    assert decoded_payload.username == TEST_USERNAME_JWT
    assert decoded_payload.exp is None, "O campo 'exp' do payload deveria ser None."
    assert not any("Token JWT expirado (verificação dupla)." in record.getMessage() for record in caplog.records if record.name == 'app.core.security'), \
        "Log de token expirado não deveria ser emitido para token sem claim 'exp'."
    print("  Sucesso: decode_token processou token sem 'exp' e retornou payload.")

def test_decode_token_handles_direct_expired_signature_error_from_jose(mocker, caplog):
    """
    Testa o tratamento do bloco `except ExpiredSignatureError` em `decode_token`.
    Isso simula o caso onde `jwt.decode` diretamente levanta ExpiredSignatureError,
    mesmo que a lógica atual use `options={'verify_exp': False}`.
    Cobre as linhas 133-134.
    """
    print("\nTeste: decode_token com ExpiredSignatureError direta do jose")
    some_token_string = "um.token.qualquer_expirado_simulado"
    mocked_jwt_decode = mocker.patch("app.core.security.jwt.decode", side_effect=ExpiredSignatureError("Simulated JOSE expiration"))
    decoded_payload = decode_token(some_token_string)
    assert decoded_payload is None, "Deveria retornar None quando ExpiredSignatureError é capturada."
    mocked_jwt_decode.assert_called_once_with(
        some_token_string,
        settings.JWT_SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_exp": False} 
    )
    log_messages = [record.getMessage() for record in caplog.records if record.name == 'app.core.security']
    assert any("Token JWT detectado como expirado pela biblioteca JOSE" in message for message in log_messages), \
        "Mensagem de log esperada para ExpiredSignatureError não encontrada."
    print("  Sucesso: decode_token lidou com ExpiredSignatureError direta e logou corretamente.")