# tests/test_core_utils.py
import pytest
from datetime import date, datetime, timedelta, timezone
from freezegun import freeze_time 
from app.core.utils import calculate_priority_score, is_task_urgent
from app.models.task import Task, TaskStatus 
from app.core.config import settings 
import uuid 

# === Testes para calculate_priority_score ===

def test_calculate_priority_invalid_importance():
    """Testa que score é None se importância for inválida."""
    assert calculate_priority_score(importance=0, due_date=None) is None
    assert calculate_priority_score(importance=6, due_date=None) is None

@freeze_time("2025-05-04")
def test_calculate_priority_no_due_date():
    """Testa cálculo sem data de vencimento."""
    expected_score = settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE + (3 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    assert calculate_priority_score(importance=3, due_date=None) == round(expected_score, 2)

    expected_score_max = settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE + (5 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    assert calculate_priority_score(importance=5, due_date=None) == round(expected_score_max, 2)

@freeze_time("2025-05-04") 
def test_calculate_priority_due_today():
    """Testa cálculo com vencimento hoje."""
    today = date.today()
    expected_score = (settings.PRIORITY_WEIGHT_DUE_DATE / 1.0) + (4 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    assert calculate_priority_score(importance=4, due_date=today) == round(expected_score, 2)

@freeze_time("2025-05-04")
def test_calculate_priority_due_future():
    """Testa cálculo com vencimento no futuro."""
    future_date = date.today() + timedelta(days=10)
    expected_score = (settings.PRIORITY_WEIGHT_DUE_DATE / 10.0) + (2 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    assert calculate_priority_score(importance=2, due_date=future_date) == round(expected_score, 2)

@freeze_time("2025-05-04")
def test_calculate_priority_overdue():
    """Testa cálculo com tarefa atrasada."""
    past_date = date.today() - timedelta(days=5)
    expected_score = settings.PRIORITY_SCORE_IF_OVERDUE + (5 * settings.PRIORITY_WEIGHT_IMPORTANCE)
    assert calculate_priority_score(importance=5, due_date=past_date) == round(expected_score, 2)

# === Testes para is_task_urgent ===

def create_dummy_task(**kwargs) -> Task:
    base_data = {
        "id": uuid.uuid4(),
        "owner_id": uuid.uuid4(),
        "title": "Dummy Task",
        "importance": 3,
        "status": TaskStatus.PENDING,
        "created_at": datetime.now(timezone.utc), 
        "due_date": None,
        "priority_score": None,
    }
    task_data = {**base_data, **kwargs}

    if task_data.get("priority_score") is None and (task_data.get("importance") or task_data.get("due_date")):
         task_data["priority_score"] = calculate_priority_score(
             importance=task_data["importance"],
             due_date=task_data["due_date"]
         )

    return Task(**task_data)

def test_is_task_urgent_no_score_no_due_date():
    """Testa que tarefa sem score e sem prazo não é urgente."""
    task = create_dummy_task(priority_score=None, due_date=None)
    assert is_task_urgent(task) is False

@freeze_time("2025-05-04")
def test_is_task_urgent_high_score():
    """Testa que tarefa com score alto é urgente."""
    high_score = calculate_priority_score(importance=5, due_date=date(2025, 5, 1))
    assert high_score > settings.EMAIL_URGENCY_THRESHOLD
    task = create_dummy_task(priority_score=high_score)
    assert is_task_urgent(task) is True

@freeze_time("2025-05-04")
def test_is_task_urgent_score_below_threshold():
    """Testa que tarefa com score baixo (e não vencida) não é urgente."""
    low_score = settings.EMAIL_URGENCY_THRESHOLD - 10.0
    future_date = date(2025, 5, 10) 
    task = create_dummy_task(priority_score=low_score, due_date=future_date)
    assert task.priority_score < settings.EMAIL_URGENCY_THRESHOLD
    assert is_task_urgent(task) is False

@freeze_time("2025-05-04")
def test_is_task_urgent_due_today():
    """Testa que tarefa com vencimento hoje é urgente (mesmo com score baixo)."""
    low_score = settings.EMAIL_URGENCY_THRESHOLD - 10.0
    today = date.today()
    task = create_dummy_task(due_date=today, priority_score=low_score)
    assert is_task_urgent(task) is True

@freeze_time("2025-05-04")
def test_is_task_urgent_overdue():
    """Testa que tarefa atrasada é urgente (mesmo com score baixo inicial)."""
    low_score = settings.EMAIL_URGENCY_THRESHOLD - 10.0
    past_date = date.today() - timedelta(days=1)
    task = create_dummy_task(due_date=past_date, priority_score=low_score) 
    assert is_task_urgent(task) is True

@freeze_time("2025-05-04")
def test_is_task_urgent_due_future_low_score():
    """Testa que tarefa futura com score baixo não é urgente."""
    future_date = date.today() + timedelta(days=5)
    low_score = settings.EMAIL_URGENCY_THRESHOLD - 20.0
    task = create_dummy_task(due_date=future_date, priority_score=low_score)
    assert is_task_urgent(task) is False

# === Testes de Borda ===

@freeze_time("2025-05-04")
def test_is_task_urgent_score_exactly_at_threshold():
    """Testa que tarefa com score exatamente no limiar não é urgente (usa >)."""
    score_at_threshold = settings.EMAIL_URGENCY_THRESHOLD
    future_date = date.today() + timedelta(days=5) 
    task = create_dummy_task(priority_score=score_at_threshold, due_date=future_date)
    if task.priority_score != score_at_threshold:
        print(f"\nWARN: Score foi recalculado para {task.priority_score} em vez de {score_at_threshold}")
    assert is_task_urgent(task) is False, f"Falhou com score {task.priority_score}, esperado False"

@freeze_time("2025-05-04")
def test_is_task_urgent_score_slightly_above_threshold():
    """Testa que tarefa com score ligeiramente acima do limiar é urgente."""
    score_above_threshold = settings.EMAIL_URGENCY_THRESHOLD + 0.01
    future_date = date.today() + timedelta(days=5) 
    task = create_dummy_task(priority_score=score_above_threshold, due_date=future_date)
    if task.priority_score != score_above_threshold:
         print(f"\nWARN: Score foi recalculado para {task.priority_score} em vez de {score_above_threshold}")
    assert is_task_urgent(task) is True, f"Falhou com score {task.priority_score}, esperado True"