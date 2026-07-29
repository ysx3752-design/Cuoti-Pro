"""场景1: 批改 API 路由（单模型版）"""
import os, tempfile, json, asyncio

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from scenario_1_grading.schemas import GradeRequest, GradeResult
from scenario_1_grading.service import run_grader, run_paper_grader
from scenario_1_grading.prompts import GRADE_PROMPT
from tools.llm_tool import llm_stream, parse_json_from_text
from tools.db_tool import add_mistake, update_mastery, add_knowledge_point

router = APIRouter(tags=["scenario1-grading"])


def sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 单题批改 ───────────────────────────────────────────────

@router.post("/grade")
async def api_grade(req: GradeRequest):
    try:
        r = run_grader(req.student_id, req.question, req.student_answer, req.subject)
        return {"code": 0, "data": r}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.post("/grade/image")
async def api_grade_image(
    file: UploadFile = File(...),
    question: str = Form(""),
    student_id: str = Form("s001"),
    subject: str = Form("数学"),
):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    try:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
        tmp.close()
        result = run_grader(student_id=student_id, question=question, student_answer="", subject=subject, image_path=tmp_path)
        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── 整卷批改 ───────────────────────────────────────────────

@router.post("/grade/paper")
async def api_grade_paper(
    file: UploadFile = File(None),
    student_id: str = Form("s001"),
    subject: str = Form("数学"),
    raw_text: str = Form(""),
):
    """整卷批改：上传图片/PDF 或直接传入文本。"""
    tmp_path = None
    try:
        if file:
            content = await file.read()
            ext = ".pdf" if file.filename and file.filename.endswith(".pdf") else ".jpg"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp.write(content)
            tmp_path = tmp.name
            tmp.close()

        if tmp_path and tmp_path.endswith(".pdf"):
            result = run_paper_grader(student_id=student_id, subject=subject, image_path=tmp_path)
        elif tmp_path:
            result = run_paper_grader(student_id=student_id, subject=subject, image_path=tmp_path)
        else:
            result = run_paper_grader(student_id=student_id, subject=subject, raw_text=raw_text)

        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── 流式批改（SSE） ────────────────────────────────────────

@router.post("/grade/stream")
async def api_grade_stream(req: GradeRequest):
    def generate():
        try:
            yield sse_event("step", {"message": "正在批改题目..."})
            prompt = GRADE_PROMPT.format(
                question=req.question, student_answer=req.student_answer,
                subject=req.subject,
            )
            full_text = ""
            for token in llm_stream(prompt, temperature=0.1):
                full_text += token
                yield sse_event("token", {"text": token})
            result = parse_json_from_text(full_text)
            for kp in result.get("knowledge_points", []):
                add_knowledge_point(kp, subject=req.subject)
            if not result.get("is_correct", False):
                add_mistake(req.student_id, {
                    "question": req.question, "student_answer": req.student_answer,
                    "subject": req.subject,
                    "correct_answer": result.get("correct_answer", ""),
                    "analysis": result.get("analysis", ""),
                    "knowledge_points": result.get("knowledge_points", []),
                    "score": result.get("score", 0),
                })
                for kp in result.get("knowledge_points", []):
                    update_mastery(req.student_id, kp, -0.2)
            else:
                for kp in result.get("knowledge_points", []):
                    update_mastery(req.student_id, kp, 0.1)
            yield sse_event("result", {"result": result})
        except Exception as e:
            yield sse_event("error", {"message": str(e)})
    return StreamingResponse(generate(), media_type="text/event-stream")
