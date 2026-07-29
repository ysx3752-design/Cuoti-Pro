"""场景2: 分层练习模块"""
from scenario_2_practice.schemas import (
    PracticeCreateRequest, PracticeAnswerInput, PracticeSubmitRequest,
    PracticeQuestionPayload, PracticeState, PracticeDifficulty,
)
from scenario_2_practice.service import run_practice, run_answer
