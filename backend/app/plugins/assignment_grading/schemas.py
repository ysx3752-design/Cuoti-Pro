"""场景1: 数据模型（Pydantic + TypedDict）"""
from __future__ import annotations
from typing import Optional, TypedDict
from pydantic import BaseModel, Field


# ── API 请求/响应模型 ──────────────────────────────────────

class GradeRequest(BaseModel):
    student_id: str
    question: str
    student_answer: str = ""
    subject: str = "数学"


class GradeResult(BaseModel):
    correct_answer: str = ""
    is_correct: bool = False
    score: float = 0.0
    analysis: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: str = "medium"


class GradeResponse(BaseModel):
    code: int = 0
    data: GradeResult


class PaperQuestionResult(BaseModel):
    number: str = ""
    question: str = ""
    student_answer: str = ""
    correct_answer: str = ""
    is_correct: bool = False
    score: float = 0.0
    analysis: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    question_type: str = "other"


class PaperSummary(BaseModel):
    total: int = 0
    correct: int = 0
    wrong: int = 0
    partial: int = 0
    avg_score: float = 0.0


class PaperGradeResponse(BaseModel):
    questions: list[PaperQuestionResult] = Field(default_factory=list)
    summary: PaperSummary = Field(default_factory=PaperSummary)
    error: str | None = None


# ── LangGraph 内部状态 ─────────────────────────────────────

class SingleGradeState(TypedDict, total=False):
    student_id: str
    question: str
    student_answer: str
    subject: str
    image_path: str | None
    ocr_text: str | None
    correct_answer: str
    is_correct: bool
    score: float
    analysis: str
    knowledge_points: list[str]
    difficulty: str
    memory_updates: list | None
    recalled_memory_summary: str | None


class PaperGradeState(TypedDict, total=False):
    student_id: str
    subject: str
    raw_text: str
    image_path: str | None
    source_type: str
    questions: list[dict]
    results: list[dict]
    summary: dict
    memory_updates: list | None
