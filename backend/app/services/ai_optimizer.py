import json
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app.core.config import settings

_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            groq_api_key=settings.GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile",
            temperature=0.3,
        )
    return _llm


def _extract_json(text: str) -> dict:
    """Parse JSON from model output, tolerating markdown fences and unescaped newlines."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj_str = cleaned[start : end + 1]
            try:
                return json.loads(obj_str)
            except json.JSONDecodeError:
                # Try to fix unescaped newlines in strings, a common LLM error
                # We replace literal newlines with \n, but keep structural newlines if possible?
                # Actually, json.loads handles single-line JSON perfectly well.
                # If we replace ALL \n with \\n, structural \n become escaped \n, which json.loads
                # will complain about if they appear outside strings!
                # Instead, we can use a regex to escape newlines ONLY inside quotes.
                def replace_newlines(match):
                    return match.group(0).replace("\n", "\\n")

                # Matches everything between double quotes, taking escaped quotes into account
                fixed_str = re.sub(r'"([^"\\]*(\\.[^"\\]*)*)"', replace_newlines, obj_str)
                try:
                    return json.loads(fixed_str)
                except json.JSONDecodeError:
                    pass
        raise


def _build_focus_block(relevant_chunks: list | None) -> str:
    if not relevant_chunks:
        return ""
    joined = "\n---\n".join(relevant_chunks[:6])
    return f"\nMost relevant resume evidence for this JD (vector-retrieved):\n{joined}\n"


def _parse_optimize_payload(content: str, original_text: str) -> dict:
    """Parse LLM JSON. ATS numeric score is NEVER taken from the model."""
    try:
        data = _extract_json(content)
    except Exception:
        data = {}

    tailored = data.get("tailored_resume") or content or original_text
    if not isinstance(tailored, str):
        tailored = json.dumps(tailored, indent=2)

    improvements = data.get("improvements") or data.get("key_improvements") or []
    strengths = data.get("strengths") or []

    return {
        "tailored_resume": tailored,
        "key_improvements": improvements if isinstance(improvements, list) else [],
        "strengths": strengths if isinstance(strengths, list) else [],
        "cover_letter": data.get("cover_letter")
        or "Cover letter generation failed. Please try again.",
        "llm_suggested_keywords": data.get("target_keywords") or data.get("missing_keywords") or [],
        "qualitative_fit": data.get("qualitative_fit"),
        "qualitative_summary": data.get("qualitative_summary") or data.get("narrative") or "",
        "improvements": improvements if isinstance(improvements, list) else [],
    }


def _format_rule_brief(pre_rules: dict) -> str:
    """Compact rule-engine snapshot for the LLM (Phase 2 prompt input)."""
    comps = pre_rules.get("components") or {}
    kw = comps.get("keyword_coverage") or {}
    sec = comps.get("sections") or {}
    quant = comps.get("quantified_impact") or {}
    verbs = comps.get("action_verbs") or {}
    length = comps.get("length_structure") or {}
    lines = [
        f"Rule score (raw scaled later): {pre_rules.get('score')}/{pre_rules.get('max')}",
        f"Keyword coverage: {kw.get('ratio_pct', 0)}% "
        f"({len(kw.get('matched') or [])}/{kw.get('total_keywords', 0)})",
        f"Matched keywords: {', '.join((kw.get('matched') or [])[:12]) or 'none'}",
        f"Missing keywords: {', '.join((kw.get('missing') or [])[:12]) or 'none'}",
        f"Sections present: {', '.join(sec.get('present') or []) or 'none'}",
        f"Sections missing: {', '.join(sec.get('missing') or []) or 'none'}",
        f"Quantified metrics found: {quant.get('evidence_count', 0)}",
        f"Action verbs unique: {verbs.get('count', 0)} "
        f"({', '.join((verbs.get('unique_verbs') or [])[:8]) or 'none'})",
        f"Length band: {length.get('band')} ({length.get('word_count', 0)} words, "
        f"{length.get('bullet_lines', 0)} bullets)",
    ]
    return "\n".join(lines)


def _run_llm_optimize(
    original_text: str,
    job_description: str,
    focus: str,
    pre_rules: dict,
) -> dict:
    """
    Phase 2: LLM rewrite + rubric-based qualitative assessment.

    Inputs include full rule-based analysis so the model scores consistently
    against gaps — but it still must NOT invent a 0–100 ATS number.
    """
    gaps = ", ".join((pre_rules.get("missing_keywords") or [])[:18]) or "none listed"
    rule_brief = _format_rule_brief(pre_rules)

    prompt = ChatPromptTemplate.from_template(
        """You are an expert career coach and ATS writing specialist.

## Original Resume
{resume}

## Vector-retrieved evidence (most JD-relevant chunks)
{focus}

## Job Description
{job}

## Rule-based ATS pre-analysis (ground truth for gaps — use this)
{rule_brief}

Missing / weak keywords to weave in ONLY if truthful:
{gaps}

## Strict qualitative rubric (1–10 for qualitative_fit)
Score qualitative_fit using ONLY this rubric:
- 9–10: Strong keyword alignment, clear metrics, relevant experience, clean structure
- 7–8: Good fit; minor gaps in keywords or quantifiable impact
- 5–6: Partial fit; missing several core JD skills or weak structure
- 3–4: Poor alignment; major sections/keywords missing
- 1–2: Resume does not meaningfully match the JD

Also rate these coaching dimensions 1–10 (integers):
- keyword_alignment
- structure_clarity
- role_relevance

## Tasks
1) Rewrite the resume to close rule-engine gaps while staying 100% truthful.
2) Prefer vector-retrieved evidence; add metrics only when already implied.
3) Provide coaching breakdown + actionable suggestions.

Respond with ONLY valid JSON (no markdown):
{{
  "tailored_resume": "Full tailored resume with sections: Summary, Skills, Experience, Education, Projects if any",
  "strengths": ["..."],
  "improvements": ["actionable suggestion 1", "actionable suggestion 2", "actionable suggestion 3"],
  "target_keywords": ["keywords still hard to support honestly"],
  "qualitative_fit": 7,
  "rubric_scores": {{
    "keyword_alignment": 7,
    "structure_clarity": 8,
    "role_relevance": 7
  }},
  "qualitative_summary": "2-3 sentences on overall fit after rewrite",
  "cover_letter": "Full professional cover letter tailored to the JD"
}}

Hard rules:
- qualitative_fit and rubric_scores are integers 1–10 only.
- Do NOT output ats_score or any 0–100 overall ATS percentage (a separate engine owns that).
- Do not invent employers, degrees, tools, or achievements not supported by the resume.
- CRITICAL: Use `\n` for newlines inside strings. Do NOT output raw unescaped newlines inside the JSON string values.
"""
    )
    chain = prompt | get_llm()
    result = chain.invoke(
        {
            "resume": original_text[:12000],
            "job": job_description[:8000],
            "focus": focus[:4000] or "(no vector chunks)",
            "gaps": gaps,
            "rule_brief": rule_brief[:2500],
        }
    )
    content = result.content if hasattr(result, "content") else str(result)
    parsed = _parse_optimize_payload(content, original_text)
    # Attach rubric if present
    try:
        data = _extract_json(content)
        parsed["rubric_scores"] = data.get("rubric_scores") or {}
    except Exception:
        parsed["rubric_scores"] = {}
    return parsed


def optimize_resume(
    original_text: str,
    job_description: str,
    relevant_chunks: list | None = None,
    semantic_distances: list | None = None,
) -> dict:
    """
    3-layer hybrid optimize pipeline:

    1) Rule pre-score on original (find gaps for the LLM prompt)
    2) LLM rewrite + qualitative coaching (improved prompt)
    3) Final hybrid score = Rules + Semantic (Chroma) + LLM qualitative (bounded)
    """
    from app.services.ats_analyzer import (
        layer1_rules,
        score_before_after,
    )

    focus = _build_focus_block(relevant_chunks)
    used_vector = bool(relevant_chunks) or bool(semantic_distances)
    distances = list(semantic_distances or [])
    chunk_count = len(relevant_chunks or [])

    # Pre-pass rules → feed full analysis into LLM prompt
    pre_rules = layer1_rules(original_text, job_description)
    pre_missing = pre_rules.get("missing_keywords") or []

    llm_ok = True
    try:
        parsed = _run_llm_optimize(original_text, job_description, focus, pre_rules)
    except Exception as e:
        print(f"AI optimize error: {e}")
        llm_ok = False
        parsed = {
            "tailored_resume": original_text,
            "key_improvements": [
                "AI rewrite unavailable — scored original resume with rules + semantic only.",
                f"Error: {str(e)[:120]}",
            ],
            "strengths": [],
            "cover_letter": "Unable to generate cover letter at this time. Please try again shortly.",
            "llm_suggested_keywords": pre_missing[:10],
            "qualitative_fit": None,
            "qualitative_summary": "",
            "improvements": [],
            "rubric_scores": {},
        }

    llm_qual = None
    if llm_ok:
        llm_qual = {
            "qualitative_fit": parsed.get("qualitative_fit"),
            "strengths": parsed.get("strengths") or [],
            "improvements": parsed.get("improvements") or parsed.get("key_improvements") or [],
            "qualitative_summary": parsed.get("qualitative_summary") or "",
            "key_improvements": parsed.get("key_improvements") or [],
        }

    comparison = score_before_after(
        original_text,
        parsed["tailored_resume"],
        job_description,
        semantic_distances=distances or None,
        semantic_chunk_count=chunk_count,
        llm_qualitative=llm_qual,
    )
    after = comparison["after_detail"]

    missing = list(after.get("missing_keywords") or [])
    for kw in parsed.get("llm_suggested_keywords") or []:
        if kw and str(kw).lower() not in {m.lower() for m in missing}:
            missing.append(str(kw))

    improvements = (
        parsed.get("key_improvements")
        or parsed.get("improvements")
        or (after.get("suggestions") or after.get("summary") or [])[:5]
    )
    # Prefer display suggestions for UI when present
    suggestions = after.get("suggestions") or improvements

    return {
        "tailored_resume": parsed["tailored_resume"],
        "ats_score": after["ats_score"],
        "key_improvements": improvements,
        "missing_keywords": missing[:25],
        "matched_keywords": after.get("matched_keywords") or [],
        "cover_letter": parsed["cover_letter"],
        "used_vector_context": used_vector,
        "ats_breakdown": after.get("breakdown") or {},
        "ats_summary": after.get("summary") or [],
        "ats_method": after.get("method") or "hybrid-3layer-v2",
        "ats_layers": after.get("layers") or {},
        "layer_scores": after.get("layer_scores") or {},
        "display_scores": after.get("display_scores") or {},
        "suggestions": suggestions[:8],
        "score_before": comparison["before"],
        "score_delta": comparison["delta"],
        "qualitative_summary": parsed.get("qualitative_summary") or "",
        "strengths": parsed.get("strengths") or [],
        "rubric_scores": parsed.get("rubric_scores") or {},
    }


def generate_interview_feedback(job_description: str, transcript: str) -> dict:
    prompt = ChatPromptTemplate.from_template(
        """You are an expert interview coach.

Job Description:
{job}

Candidate's Answer:
{answer}

Respond with ONLY valid JSON (no markdown):
{{
  "feedback": "3-4 sentences of constructive feedback",
  "score": 8,
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"]
}}

score is 1-10 overall quality of the answer.
"""
    )
    try:
        chain = prompt | get_llm()
        result = chain.invoke({"job": job_description[:4000], "answer": transcript[:4000]})
        content = result.content if hasattr(result, "content") else str(result)
        data = _extract_json(content)
        return {
            "feedback": data.get("feedback") or content,
            "score": data.get("score", 7),
            "strengths": data.get("strengths") or [],
            "improvements": data.get("improvements") or [],
        }
    except Exception as e:
        print(f"Interview feedback error: {e}")
        return {
            "feedback": "Thanks for practicing. Focus on a clear structure: situation, actions, and measurable results.",
            "score": 7,
            "strengths": ["You completed a practice answer"],
            "improvements": ["Add quantifiable outcomes", "Keep answers under 2 minutes"],
        }


COMMON_INTERVIEW_QUESTIONS = [
    "Tell me about yourself and why you're interested in this role.",
    "Walk me through a challenging project and how you handled it.",
    "What are your greatest strengths relevant to this position?",
    "Describe a time you worked under a tight deadline.",
    "Tell me about a conflict on a team and how you resolved it.",
    "Where do you see yourself growing in the next few years?",
    "Why are you leaving your current role (or why this opportunity now)?",
    "How do you prioritize when everything feels urgent?",
]


def generate_interview_questions(
    job_description: str,
    count: int = 5,
    include_common: bool = True,
) -> dict:
    """
    Returns role-specific questions (+ optional common bank).
    Shape: { "common": [...], "role_specific": [...], "questions": [...] }
    """
    role_count = max(3, count - (3 if include_common else 0)) if include_common else count
    prompt = ChatPromptTemplate.from_template(
        """You are an expert interview coach.
Based on this job description, generate {count} realistic, role-specific interview questions
(mix behavioral + technical when relevant). Avoid generic "tell me about yourself".

Job Description:
{job}

Respond with ONLY valid JSON array of strings, e.g. ["Question 1?", "Question 2?"]
"""
    )
    role_specific: list[str] = []
    try:
        chain = prompt | get_llm()
        result = chain.invoke({"job": job_description[:4000], "count": role_count})
        content = result.content if hasattr(result, "content") else str(result)
        cleaned = content.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence:
            cleaned = fence.group(1).strip()
        questions = json.loads(cleaned)
        if isinstance(questions, list) and questions:
            role_specific = [str(q) for q in questions][:role_count]
    except Exception as e:
        print(f"Interview questions error: {e}")
        role_specific = [
            "Which of your past projects best maps to this role's core responsibilities?",
            "How would you design a scalable solution for a key challenge in this job?",
            "Describe a time you improved a system or process end-to-end.",
        ][:role_count]

    common = COMMON_INTERVIEW_QUESTIONS[:3] if include_common else []
    combined = list(dict.fromkeys([*common, *role_specific]))[:count]
    return {
        "common": common,
        "role_specific": role_specific,
        "questions": combined,
    }
