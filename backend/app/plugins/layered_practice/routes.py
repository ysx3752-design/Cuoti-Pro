"""场景2: 分层练习 API 路由（单模型版）"""
import json

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse

from scenario_2_practice.schemas import PracticeCreateRequest
from scenario_2_practice.service import run_practice, run_answer, detect_weak_points_from_mistakes
from scenario_2_practice.prompts import PROMPT_GEN, PROMPT_GRADE_PRACTICE
from tools.llm_tool import llm_stream, parse_json_from_text
from tools.db_tool import update_mastery

router = APIRouter(tags=["scenario2-practice"])


def sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/practice/generate")
async def api_practice_generate(
    student_id: str = Form(...),
    weak_points: str = Form(""),
    difficulty: str = Form("base"),
    subject: str = Form("数学"),
    max_questions: int = Form(10),
):
    """启动一轮分层练习。

    weak_points 为空时自动从错题数据检测薄弱点。
    """
    try:
        wps = [w.strip() for w in weak_points.split(",") if w.strip()]
        r = run_practice(
            student_id=student_id,
            weak_points=wps if wps else None,
            subject=subject,
            difficulty=difficulty,
            max_questions=max_questions,
        )
        if "error" in r:
            raise HTTPException(400, detail=r["error"])
        return {
            "code": 0,
            "data": {
                "questions": r.get("questions", []),
                "session_summary": r.get("session_summary", ""),
                "memory_updates": r.get("memory_updates"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.post("/practice/answer")
async def api_practice_answer(
    student_id: str = Form(...),
    question_json: str = Form(...),
    student_answer: str = Form(...),
    subject: str = Form("数学"),
):
    """单题提交批改（不分层循环，仅批改）。"""
    try:
        q = json.loads(question_json)
        r = run_answer(student_id, q, student_answer, subject=subject)
        for kp in q.get("knowledge_points", []):
            update_mastery(student_id, kp, 0.1 if r["is_correct"] else -0.15)
        return {"code": 0, "data": r}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.get("/practice/weak-points/{student_id}")
async def api_detect_weak_points(student_id: str, subject: str = "数学"):
    """检测学生的薄弱知识点。"""
    try:
        wps = detect_weak_points_from_mistakes(student_id, subject)
        return {"code": 0, "data": {"weak_points": wps}}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# ── 流式端点（SSE） ────────────────────────────────────────

@router.post("/practice/generate/stream")
async def api_practice_gen_stream(
    student_id: str = Form(...),
    weak_points: str = Form(""),
    difficulty: str = Form("base"),
    subject: str = Form("数学"),
    max_questions: int = Form(10),
):
    def generate():
        try:
            wps = [w.strip() for w in weak_points.split(",") if w.strip()]
            if not wps:
                yield sse_event("step", {"message": "正在分析错题数据，查找薄弱知识点..."})
                wps = detect_weak_points_from_mistakes(student_id, subject)
            if not wps:
                yield sse_event("error", {"message": "未找到薄弱知识点"})
                return

            yield sse_event("step", {"message": f"薄弱知识点：{', '.join(wps)}，正在出题..."})
            from scenario_2_practice.schemas import DIFFICULTY_CN
            diff_cn = DIFFICULTY_CN.get(difficulty, difficulty)
            prompt = PROMPT_GEN.format(
                subject=subject, difficulty=difficulty, difficulty_cn=diff_cn,
                weak_points=", ".join(wps), done_count=0,
            )
            full_text = ""
            for token in llm_stream(prompt, temperature=0.8):
                full_text += token
                yield sse_event("token", {"text": token})
            result = parse_json_from_text(full_text)
            yield sse_event("result", {"result": {**result, "weak_points": wps}})
        except Exception as e:
            yield sse_event("error", {"message": str(e)})
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/practice/answer/stream")
async def api_practice_ans_stream(
    student_id: str = Form(...),
    question_json: str = Form(...),
    student_answer: str = Form(...),
    subject: str = Form("数学"),
):
    def generate():
        try:
            yield sse_event("step", {"message": "正在批改练习题..."})
            q = json.loads(question_json)
            prompt = PROMPT_GRADE_PRACTICE.format(
                question=q.get("question", ""),
                correct_answer=q.get("answer", ""),
                student_answer=student_answer,
            )
            full_text = ""
            for token in llm_stream(prompt):
                full_text += token
                yield sse_event("token", {"text": token})
            result = parse_json_from_text(full_text)
            for kp in q.get("knowledge_points", []):
                update_mastery(student_id, kp, 0.1 if result.get("is_correct") else -0.15)
            yield sse_event("result", {"result": result})
        except Exception as e:
            yield sse_event("error", {"message": str(e)})
    return StreamingResponse(generate(), media_type="text/event-stream")
