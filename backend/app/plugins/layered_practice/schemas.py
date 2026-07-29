"""场景2: 数据模型"""
from __future__ import annotations
from typing import Optional, Literal, TypedDict
from pydantic import BaseModel, Field

PracticeDifficulty = Literal["base", "variant", "advanced", "exam"]
DIFFICULTY_ORDER = ["base", "variant", "advanced", "exam"]
DIFFICULTY_CN = {
    "base": "基础补漏", "variant": "同类变式",
    "advanced": "综合拔高", "exam": "高考真题",
}


class PracticeCreateRequest(BaseModel):
    student_id: str
    subject: str = "数学"
    weak_points: list[str] = Field(default_factory=list, description="薄弱知识点，为空时自动从错题检测")
    difficulty: PracticeDifficulty = "base"
    max_questions: int = Field(default=10, ge=1, le=20)


class PracticeAnswerInput(BaseModel):
    question_id: int
    answer: str = Field(min_length=1)


class PracticeSubmitRequest(BaseModel):
    student_id: str
    answers: list[PracticeAnswerInput] = Field(min_length=1)


class PracticeQuestionPayload(BaseModel):
    question: str
    answer: str
    solution: str
    knowledge_points: list[str]
    difficulty: PracticeDifficulty
    hint: str


# ── LangGraph 内部状态 ─────────────────────────────────────

class PracticeState(TypedDict, total=False):
    student_id: str
    subject: str
    weak_points: list[str]
    difficulty: str
    difficulty_changed: bool
    questions: list[dict]
    current_index: int
    current_question: dict
    student_answer: str
    is_correct: bool
    feedback: str
    correct_answer: str
    session_summary: str
    max_questions: int
    covered_points: list[str]
    memory_updates: list | None
    recalled_memory_summary: str | None
