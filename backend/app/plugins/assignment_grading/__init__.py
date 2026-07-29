"""场景1: 作业批改模块 — 单模型集成"""
from scenario_1_grading.schemas import (
    GradeRequest, GradeResult,
    PaperQuestionResult, PaperSummary, PaperGradeResponse,
    SingleGradeState, PaperGradeState,
)
from scenario_1_grading.service import run_grader, run_paper_grader
