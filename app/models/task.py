# app/models/task.py
"""
Este módulo define os modelos Pydantic utilizados para representar Tarefas (Tasks)
na aplicação. Inclui modelos para a criação, atualização, e representação
de tarefas como armazenadas e retornadas pelo banco de dados, além de
definições auxiliares como o status da tarefa.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

# ==============================
# --- Enumerações de Status ---
# ==============================

class TaskStatus(str, Enum):
    """Define os possíveis status de uma tarefa."""
    # Tarefa está aguardando para ser iniciada.
    PENDING = "pendente"
    # Tarefa está atualmente em execução.
    IN_PROGRESS = "em_progresso"
    # Tarefa foi finalizada com sucesso.
    COMPLETED = "concluída"
    # Tarefa foi cancelada e não será mais trabalhada.
    CANCELLED = "cancelada"

# ====================================
# --- Modelos Pydantic de Tarefa ---
# ====================================

# --- Modelo Base ---

class TaskBase(BaseModel):
    """
    Modelo base contendo os campos comuns e essenciais de uma tarefa.
    Serve como fundação para outros modelos de tarefa mais específicos.
    """
    title: str = Field(..., title="Título da Tarefa", min_length=3, max_length=100)
    description: Optional[str] = Field(None, title="Descrição Detalhada", max_length=500)
    importance: int = Field(..., ge=1, le=5, title="Importância (1-5)")
    due_date: Optional[date] = Field(None, title="Data de Vencimento")
    status: TaskStatus = Field(default=TaskStatus.PENDING, title="Status da Tarefa")
    tags: Optional[List[str]] = Field(None, title="Etiquetas/Tags")
    project: Optional[str] = Field(None, title="Projeto Associado")

    # O campo owner_id (ID do proprietário) geralmente é adicionado em estágios posteriores
    # da lógica da aplicação (ex: inferido a partir do token de autenticação do usuário)
    # e não é esperado como parte do payload de criação base de uma tarefa pelo cliente.
    # owner_id: Optional[uuid.UUID] = Field(None, title="ID do Proprietário da Tarefa")

    # Configurações do modelo Pydantic.
    # json_schema_extra é usado para prover exemplos para a documentação OpenAPI.
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

# --- Modelos para Operações ---

class TaskCreate(TaskBase):
    """
    Modelo utilizado para a criação de uma nova tarefa.
    Herda todos os campos de `TaskBase`, representando os dados
    necessários que o cliente deve fornecer.
    """
    pass 

class TaskUpdate(BaseModel):
    """
    Modelo utilizado para atualizar uma tarefa existente.
    Todos os campos são opcionais, permitindo que o cliente envie
    apenas os dados que deseja modificar (atualização parcial).
    """
    title: Optional[str] = Field(None, title="Título da Tarefa", min_length=3, max_length=100)
    description: Optional[str] = Field(None, title="Descrição Detalhada", max_length=500)
    importance: Optional[int] = Field(None, ge=1, le=5, title="Importância (1-5)")
    due_date: Optional[date] = Field(None, title="Data de Vencimento")
    status: Optional[TaskStatus] = Field(None, title="Status da Tarefa")
    tags: Optional[List[str]] = Field(None, title="Etiquetas/Tags")
    project: Optional[str] = Field(None, title="Projeto Associado")
    # Campo opcional para a pontuação de prioridade.
    # Pode ser usado para ajustes manuais ou atualizações específicas da prioridade.
    priority_score: Optional[float] = Field(None, title="Pontuação de Prioridade (Ajustável)")

    # Configurações do modelo Pydantic, incluindo exemplos para OpenAPI.
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

# --- Modelos para Representação no Banco de Dados ---

class TaskInDBBase(TaskBase):
    """
    Modelo base para tarefas como são armazenadas e recuperadas do banco de dados.
    Estende `TaskBase` adicionando campos gerenciados pelo sistema, como IDs
    e timestamps de criação/atualização.
    """
    id: uuid.UUID = Field(..., title="ID Único da Tarefa")
    owner_id: uuid.UUID = Field(..., title="ID do Proprietário da Tarefa")
    # Data e hora (UTC) em que a tarefa foi criada, definida automaticamente.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), title="Data de Criação")
    # Data e hora (UTC) da última atualização da tarefa. Nulo se nunca atualizada.
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")
    # Pontuação de prioridade, potencialmente calculada pela lógica de negócios da aplicação.
    priority_score: Optional[float] = Field(None, title="Pontuação de Prioridade Calculada")

    # Configuração Pydantic para permitir que o modelo seja instanciado a partir
    # de atributos de objetos (útil para mapear dados de ORMs/ODMs).
    model_config = ConfigDict(from_attributes=True)

class Task(TaskInDBBase):
    """
    Modelo completo representando uma tarefa, incluindo todos os campos
    gerenciados pelo sistema e campos de entrada do usuário.
    Este é tipicamente o modelo utilizado para retornar dados de tarefas da API.
    """
    # Configuração do modelo Pydantic.
    # from_attributes permite carregar dados de atributos de objetos.
    # json_schema_extra fornece um exemplo detalhado para a documentação OpenAPI.
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