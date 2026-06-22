from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, TEXT, func

from db.session import Base


class BenchmarkTaskModel(Base):
    __tablename__ = "benchmark_tasks"

    id = Column(String(128), primary_key=True)
    benchmark = Column(String(50), nullable=False, index=True)
    level = Column(String(50), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    task_index = Column(Integer, nullable=False)
    target = Column(String(255), nullable=False)
    vulnerability = Column(String(255), nullable=True)
    alias = Column(String(255), nullable=True)
    task_text = Column(TEXT, nullable=False)
    flag = Column(String(255), nullable=True)
    command_milestones = Column(JSON, default=list)
    stage_milestones = Column(JSON, default=list)
    create_time = Column(DateTime, default=func.now())


class BenchmarkRunModel(Base):
    __tablename__ = "benchmark_runs"

    id = Column(String(32), primary_key=True)
    benchmark_task_id = Column(String(128), ForeignKey("benchmark_tasks.id"), index=True)
    model_name = Column(String(100), nullable=True)
    session_id = Column(String(32), nullable=True, index=True)
    status = Column(String(50), default="created", index=True)
    score = Column(JSON, default=dict)
    notes = Column(TEXT, nullable=True)
    create_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())


class BenchmarkStepModel(Base):
    __tablename__ = "benchmark_steps"

    id = Column(String(32), primary_key=True)
    run_id = Column(String(32), ForeignKey("benchmark_runs.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    role = Column(String(100), nullable=True)
    task = Column(TEXT, nullable=True)
    commands = Column(JSON, default=list)
    approved = Column(Boolean, default=False)
    validation = Column(JSON, nullable=True)
    observation = Column(TEXT, nullable=True)
    create_time = Column(DateTime, default=func.now())


class BenchmarkTask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(...)
    benchmark: str = "autopenbench"
    level: str
    category: str
    task_index: int
    target: str
    vulnerability: Optional[str] = None
    alias: Optional[str] = None
    task_text: str
    flag: Optional[str] = None
    command_milestones: list[str] = Field(default_factory=list)
    stage_milestones: list[str] = Field(default_factory=list)
    create_time: Optional[datetime] = None

class BenchmarkRun(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    benchmark_task_id: str
    model_name: Optional[str] = None
    session_id: Optional[str] = None
    status: str
    score: dict = Field(default_factory=dict)
    notes: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

class BenchmarkStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    step_index: int
    role: Optional[str] = None
    task: Optional[str] = None
    commands: list[str] = Field(default_factory=list)
    approved: bool = False
    validation: Optional[dict] = None
    observation: Optional[str] = None
    create_time: Optional[datetime] = None
