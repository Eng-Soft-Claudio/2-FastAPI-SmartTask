# tests/test_core_utils.py
"""
Este módulo contém testes unitários para as funções utilitárias definidas
em `app.core.utils`, especificamente aquelas relacionadas à lógica de
negócios de tarefas, como cálculo de pontuação de prioridade e
identificação de tarefas urgentes.

Os testes utilizam `freezegun` para mockar a data/hora atual, permitindo
testes consistentes e previsíveis de funcionalidades baseadas em datas.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.core.utils import calculate_priority_score, is_task_urgent
from app.models.task import Task, TaskStatus # TaskStatus é usado aqui

# ========================
# --- Testes para `calculate_priority_score` ---
# ========================
def test_calculate_priority_score_with_invalid_importance_returns_none():
    """
    Testa se `calculate_priority_score` retorna `None` (ou o valor default se alterado na função)
    quando o valor de `importance` fornecido está fora do intervalo válido (1-5).
    """
    print("\nTeste: calculate_priority_score com importância inválida.")
    # --- Arrange & Act ---
    score_low_importance = calculate_priority_score(importance=0, due_date=None)
    print(f"  Score para importância 0: {score_low_importance}")
    # --- Assert ---
    assert score_low_importance is None, "Score deveria ser None para importância 0."

    # --- Arrange & Act ---
    score_high_importance = calculate_priority_score(importance=6, due_date=None)
    print(f"  Score para importância 6: {score_high_importance}")
    # --- Assert ---
    assert score_high_importance is None, "Score deveria ser None para importância 6."
    print("  Sucesso: Importância inválida resulta em score None.")


@freeze_time("2025-05-04")
def test_calculate_priority_score_with_no_due_date():
    """
    Testa o cálculo da pontuação de prioridade quando a tarefa não tem data de entrega (`due_date=None`).
    A pontuação deve ser baseada no `PRIORITY_DEFAULT_SCORE_NO_DUE_DATE` mais o peso da importância.
    """
    print("\nTeste: calculate_priority_score sem data de entrega (due_date=None) em 2025-05-04.")
    # --- Cenário 1 ---
    importance_3 = 3
    expected_score_importance_3 = (settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE or 0.0) + \
                                 (importance_3 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    actual_score_importance_3 = calculate_priority_score(importance=importance_3, due_date=None)
    print(f"  Importância 3: Score esperado={expected_score_importance_3:.2f}, "
          f"Calculado={actual_score_importance_3}")
    assert actual_score_importance_3 == round(expected_score_importance_3, 2)

    # --- Cenário 2 ---
    importance_5 = 5
    expected_score_importance_5 = (settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE or 0.0) + \
                                 (importance_5 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    actual_score_importance_5 = calculate_priority_score(importance=importance_5, due_date=None)
    print(f"  Importância 5: Score esperado={expected_score_importance_5:.2f}, "
          f"Calculado={actual_score_importance_5}")
    assert actual_score_importance_5 == round(expected_score_importance_5, 2)
    print("  Sucesso: Scores para tarefas sem data de entrega calculados corretamente.")


@freeze_time("2025-05-04")
def test_calculate_priority_score_with_due_date_today():
    """
    Testa o cálculo da pontuação de prioridade quando a data de entrega da tarefa é hoje.
    """
    print("\nTeste: calculate_priority_score com data de entrega HOJE (2025-05-04).")
    # --- Arrange ---
    due_date_is_today = date.today()
    test_importance = 4
    days_factor_for_today = 1.0
    expected_score = (settings.PRIORITY_WEIGHT_DUE_DATE / days_factor_for_today) + \
                     (test_importance * settings.PRIORITY_WEIGHT_IMPORTANCE)
    # --- Act ---
    actual_score = calculate_priority_score(importance=test_importance, due_date=due_date_is_today)
    # --- Assert ---
    print(f"  Importância {test_importance}, Due Date Hoje: Score esperado={expected_score:.2f}, "
          f"Calculado={actual_score}")
    assert actual_score == round(expected_score, 2)
    print("  Sucesso: Score para tarefa com entrega hoje calculado corretamente.")


@freeze_time("2025-05-04")
def test_calculate_priority_score_with_due_date_in_future():
    """
    Testa o cálculo da pontuação de prioridade quando a data de entrega da tarefa
    está no futuro (10 dias a partir de "hoje").
    """
    print("\nTeste: calculate_priority_score com data de entrega no FUTURO (2025-05-04 + 10 dias).")
    # --- Arrange ---
    due_date_in_future = date.today() + timedelta(days=10)
    test_importance = 2
    days_to_due = 10.0
    expected_score = (settings.PRIORITY_WEIGHT_DUE_DATE / days_to_due) + \
                     (test_importance * settings.PRIORITY_WEIGHT_IMPORTANCE)
    # --- Act ---
    actual_score = calculate_priority_score(importance=test_importance, due_date=due_date_in_future)
    # --- Assert ---
    print(f"  Importância {test_importance}, Due Date em {days_to_due} dias: "
          f"Score esperado={expected_score:.2f}, Calculado={actual_score}")
    assert actual_score == round(expected_score, 2)
    print("  Sucesso: Score para tarefa com entrega futura calculado corretamente.")


@freeze_time("2025-05-04")
def test_calculate_priority_score_for_overdue_task():
    """
    Testa o cálculo da pontuação de prioridade para uma tarefa que já está atrasada (5 dias).
    """
    print("\nTeste: calculate_priority_score para tarefa ATRASADA (2025-05-04 - 5 dias).")
    # --- Arrange ---
    overdue_date = date.today() - timedelta(days=5)
    test_importance = 5
    expected_score = settings.PRIORITY_SCORE_IF_OVERDUE + \
                     (test_importance * settings.PRIORITY_WEIGHT_IMPORTANCE)
    # --- Act ---
    actual_score = calculate_priority_score(importance=test_importance, due_date=overdue_date)
    # --- Assert ---
    print(f"  Importância {test_importance}, Tarefa Atrasada: "
          f"Score esperado={expected_score:.2f}, Calculado={actual_score}")
    assert actual_score == round(expected_score, 2)
    print("  Sucesso: Score para tarefa atrasada calculado corretamente.")

# ========================
# --- Testes para `is_task_urgent` ---
# ========================
def _create_dummy_test_task(**kwargs) -> Task:
    """
    Função auxiliar para criar instâncias de `Task` para os testes de `is_task_urgent`.
    """
    base_task_data = {
        "id": uuid.uuid4(),
        "owner_id": uuid.uuid4(),
        "title": "Tarefa de Teste Dummy",
        "description": "Descrição da tarefa dummy.",
        "importance": 3,
        "status": TaskStatus.PENDING,
        "tags": None,
        "project": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
        "due_date": None,
        "priority_score": None,
    }
    final_task_data = {**base_task_data, **kwargs}
    if final_task_data.get("priority_score") is None and \
       (final_task_data.get("importance") or final_task_data.get("due_date")):
        calc_importance = final_task_data.get("importance", base_task_data["importance"])
        final_task_data["priority_score"] = calculate_priority_score(
            importance=calc_importance,
            due_date=final_task_data.get("due_date")
        )
    try:
        return Task(**final_task_data)
    except Exception as e: # pragma: no cover
        print(f"Erro ao criar Dummy Task com dados: {final_task_data}. Erro: {e}")
        raise

def test_is_task_urgent_when_no_score_and_no_due_date():
    """
    Testa se uma tarefa sem pontuação de prioridade e sem data de entrega
    NÃO é considerada urgente.
    """
    print("\nTeste: is_task_urgent - Tarefa sem score e sem data de entrega.")
    # --- Arrange ---
    task_no_urgency_factors = _create_dummy_test_task(importance=3, priority_score=None, due_date=None)
    task_no_urgency_factors.priority_score = None # Força o score para None
    print(f"  Tarefa para teste: score={task_no_urgency_factors.priority_score}, due_date={task_no_urgency_factors.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_no_urgency_factors)
    # --- Assert ---
    assert is_urgent_result is False, "Tarefa sem score nem data de entrega não deveria ser urgente."
    print("  Sucesso: Tarefa sem fatores de urgência não é urgente.")

@freeze_time("2025-05-04")
def test_is_task_urgent_with_high_priority_score():
    """
    Testa se uma tarefa com `priority_score` acima do `EMAIL_URGENCY_THRESHOLD`
    é considerada urgente, mesmo que a data de entrega não seja iminente.
    """
    print("\nTeste: is_task_urgent - Tarefa com pontuação de prioridade alta (acima do threshold).")
    # --- Arrange ---
    high_score = settings.EMAIL_URGENCY_THRESHOLD + 10.0
    task_high_score = _create_dummy_test_task(priority_score=high_score, due_date=date.today() + timedelta(days=30))
    print(f"  Tarefa: score={task_high_score.priority_score} (Threshold={settings.EMAIL_URGENCY_THRESHOLD}), due_date={task_high_score.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_high_score)
    # --- Assert ---
    assert is_urgent_result is True, "Tarefa com score alto deveria ser urgente."
    print("  Sucesso: Tarefa com score alto é urgente.")

@freeze_time("2025-05-04")
def test_is_task_urgent_with_score_below_threshold_and_future_due_date():
    """
    Testa se uma tarefa com `priority_score` abaixo do `EMAIL_URGENCY_THRESHOLD`
    e com data de entrega no futuro NÃO é considerada urgente.
    """
    print("\nTeste: is_task_urgent - Score baixo e data de entrega futura.")
    # --- Arrange ---
    low_score = settings.EMAIL_URGENCY_THRESHOLD - 10.0
    due_date_in_future = date.today() + timedelta(days=10)
    task_low_score_future = _create_dummy_test_task(priority_score=low_score, due_date=due_date_in_future)
    print(f"  Tarefa: score={task_low_score_future.priority_score} (Threshold={settings.EMAIL_URGENCY_THRESHOLD}), "
          f"due_date={task_low_score_future.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_low_score_future)
    # --- Assert ---
    assert is_urgent_result is False, "Tarefa com score baixo e entrega futura não deveria ser urgente."
    print("  Sucesso: Tarefa com score baixo e entrega futura não é urgente.")

@freeze_time("2025-05-04")
def test_is_task_urgent_when_due_date_is_today():
    """
    Testa se uma tarefa com data de entrega para HOJE é considerada urgente,
    mesmo que sua `priority_score` esteja abaixo do `EMAIL_URGENCY_THRESHOLD`.
    """
    print("\nTeste: is_task_urgent - Data de entrega é HOJE (2025-05-04).")
    # --- Arrange ---
    score_below_threshold = settings.EMAIL_URGENCY_THRESHOLD - 5.0
    due_date_is_today = date.today()
    task_due_today = _create_dummy_test_task(due_date=due_date_is_today, priority_score=score_below_threshold)
    print(f"  Tarefa: score={task_due_today.priority_score}, due_date={task_due_today.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_due_today)
    # --- Assert ---
    assert is_urgent_result is True, "Tarefa com entrega hoje deveria ser urgente, independentemente do score."
    print("  Sucesso: Tarefa com entrega hoje é urgente.")

@freeze_time("2025-05-04")
def test_is_task_urgent_when_overdue():
    """
    Testa se uma tarefa que está ATRASADA (data de entrega no passado) é considerada urgente,
    mesmo que sua `priority_score` esteja abaixo do `EMAIL_URGENCY_THRESHOLD`.
    """
    print("\nTeste: is_task_urgent - Tarefa ATRASADA (entrega em 2025-05-03).")
    # --- Arrange ---
    score_below_threshold = settings.EMAIL_URGENCY_THRESHOLD - 15.0
    overdue_date = date.today() - timedelta(days=1)
    task_overdue = _create_dummy_test_task(due_date=overdue_date, priority_score=score_below_threshold)
    print(f"  Tarefa: score={task_overdue.priority_score}, due_date={task_overdue.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_overdue)
    # --- Assert ---
    assert is_urgent_result is True, "Tarefa atrasada deveria ser urgente."
    print("  Sucesso: Tarefa atrasada é urgente.")

# ========================
# --- Testes de Casos de Borda para `is_task_urgent` ---
# ========================
@freeze_time("2025-05-04")
def test_is_task_urgent_when_score_is_exactly_at_threshold_and_due_date_is_future():
    """
    Testa o comportamento de `is_task_urgent` quando a `priority_score` é
    EXATAMENTE igual ao `EMAIL_URGENCY_THRESHOLD` e a data de entrega está no futuro.
    """
    print("\nTeste de Borda: is_task_urgent - Score no limiar, entrega futura.")
    # --- Arrange ---
    score_at_threshold = settings.EMAIL_URGENCY_THRESHOLD
    due_date_in_future = date.today() + timedelta(days=5)
    task_at_threshold = _create_dummy_test_task(priority_score=score_at_threshold, due_date=due_date_in_future)
    if task_at_threshold.priority_score != score_at_threshold: # pragma: no cover (Defensivo)
        print(f"  AVISO: Score recalculado para {task_at_threshold.priority_score}")
        task_at_threshold.priority_score = score_at_threshold
    print(f"  Tarefa: score={task_at_threshold.priority_score} (Threshold={settings.EMAIL_URGENCY_THRESHOLD}), "
          f"due_date={task_at_threshold.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_at_threshold)
    # --- Assert ---
    assert is_urgent_result is False, \
        f"Tarefa com score no limiar ({task_at_threshold.priority_score}) e entrega futura não deveria ser urgente."
    print("  Sucesso: Tarefa com score no limiar (e entrega futura) não é urgente.")

@freeze_time("2025-05-04")
def test_is_task_urgent_when_score_is_slightly_above_threshold_and_due_date_is_future():
    """
    Testa se `is_task_urgent` considera uma tarefa urgente quando sua `priority_score`
    é LIGEIRAMENTE ACIMA do `EMAIL_URGENCY_THRESHOLD` e a data de entrega está no futuro.
    """
    print("\nTeste de Borda: is_task_urgent - Score ligeiramente acima do limiar, entrega futura.")
    # --- Arrange ---
    score_slightly_above_threshold = settings.EMAIL_URGENCY_THRESHOLD + 0.01
    due_date_in_future = date.today() + timedelta(days=5)
    task_above_threshold = _create_dummy_test_task(priority_score=score_slightly_above_threshold, due_date=due_date_in_future)
    if task_above_threshold.priority_score != score_slightly_above_threshold: # pragma: no cover (Defensivo)
         print(f"  AVISO: Score recalculado para {task_above_threshold.priority_score}")
         task_above_threshold.priority_score = score_slightly_above_threshold
    print(f"  Tarefa: score={task_above_threshold.priority_score} (Threshold={settings.EMAIL_URGENCY_THRESHOLD}), "
          f"due_date={task_above_threshold.due_date}")
    # --- Act ---
    is_urgent_result = is_task_urgent(task_above_threshold)
    # --- Assert ---
    assert is_urgent_result is True, \
        f"Tarefa com score ({task_above_threshold.priority_score}) ligeiramente acima do limiar deveria ser urgente."
    print("  Sucesso: Tarefa com score ligeiramente acima do limiar (e entrega futura) é urgente.")