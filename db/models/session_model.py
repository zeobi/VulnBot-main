from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, String

from db.session import Base


class SessionModel(Base):
    __tablename__ = "sessions"
    id = Column(String(32), primary_key=True)
    name = Column(String(50))
    init_description = Column(String(512))
    current_role_name = Column(String(50))
    current_planner_id = Column(String(32), index=True)
    history_planner_ids = Column(String(256))


class ArrayField(List):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return handler(List)

class Session(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    init_description: Optional[str] = None
    current_role_name: Optional[str] = None
    current_planner_id: Optional[str] = None
    history_planner_ids: ArrayField[str] = Field(default_factory=list)

    @field_validator('history_planner_ids', mode='before')
    @classmethod
    def parse_history_planner_ids(cls, value):
        if isinstance(value, str):
            return value.split(',') if value else []
        return value

    class Config:
        from_attributes = True
