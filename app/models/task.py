# app/models/task.py

from pydantic import BaseModel, Field
from typing import Optional, List 
from datetime import date, datetime, timezone
import uuid 
from enum import Enum
from pydantic import ConfigDict

class TaskStatus(str, Enum):
    PENDING = "pendente"
    IN_PROGRESS = "em_progresso"
    COMPLETED = "concluída"
    CANCELLED = "cancelada"

# Modelo base para os campos comuns de uma tarefa
class TaskBase(BaseModel):
    title: str = Field(..., title="Título da Tarefa", min_length=3, max_length=100)
    description: Optional[str] = Field(None, title="Descrição Detalhada", max_length=500)
    importance: int = Field(..., ge=1, le=5, title="Importância (1-5)")
    due_date: Optional[date] = Field(None, title="Data de Vencimento")
    status: TaskStatus = Field(default=TaskStatus.PENDING, title="Status da Tarefa")
    tags: Optional[List[str]] = Field(None, title="Etiquetas/Tags")
    project: Optional[str] = Field(None, title="Projeto Associado")
    # owner_id: Optional[uuid.UUID] = Field(None, title="ID do Proprietário da Tarefa")
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "Finalizar relatório mensal",
                    "description": "Compilar dados e escrever o relatório final.",
                    "importance": 4,
                    "due_date": "2024-08-15",
                    "status": "pendente",
                    "tags": ["relatorios", "financeiro"],
                    "project": "Relatórios Q3"
                    # owner_id não precisa estar no exemplo de criação base
                }
            ]
        }
    }

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, title="Título da Tarefa", min_length=3, max_length=100)
    description: Optional[str] = Field(None, title="Descrição Detalhada", max_length=500)
    importance: Optional[int] = Field(None, ge=1, le=5, title="Importância (1-5)")
    due_date: Optional[date] = Field(None, title="Data de Vencimento")
    status: Optional[TaskStatus] = Field(None, title="Status da Tarefa")
    tags: Optional[List[str]] = Field(None, title="Etiquetas/Tags")
    project: Optional[str] = Field(None, title="Projeto Associado")
    priority_score: Optional[float] = Field(None, title="Pontuação de Prioridade (para ajustes manuais, talvez?)")

    model_config = {
         "json_schema_extra": {
            "examples": [
                {
                    "title": "Revisar relatório mensal v2",
                    "status": TaskStatus.IN_PROGRESS,
                    "importance": 5
                }
            ]
        }
    }


class TaskInDBBase(TaskBase):
    id: uuid.UUID = Field(..., title="ID Único da Tarefa")
    owner_id: uuid.UUID = Field(..., title="ID do Proprietário da Tarefa")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), title="Data de Criação")
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")
    priority_score: Optional[float] = Field(None, title="Pontuação de Prioridade Calculada") 
    model_config = ConfigDict(from_attributes=True)

class Task(TaskInDBBase):
    model_config = ConfigDict(
         from_attributes=True, 
         json_schema_extra={ 
             "examples": [
                {
                    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    "owner_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef", 
                    "title": "Finalizar relatório mensal",
                    "description": "Compilar dados e escrever o relatório final.",
                    "importance": 4,
                    "due_date": "2024-08-15",
                    "status": "pendente",
                    "tags": ["relatorios", "financeiro"],
                    "project": "Relatórios Q3",
                    "created_at": "2024-07-28T10:00:00Z",
                    "updated_at": None,
                    "priority_score": None 
                }
            ]
         }
     )