"""
Hybrid ATS Analyzer — Improved version (CareerForge)
3 layers: Rules (55) + Semantic (25) + LLM qualitative (20)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from app.services.skills import extract_skills_rules

logger = logging.getLogger("careerforge.ats")

# ─── Layer weights ───────────────────────────────────────────────────────────
W_KEYWORDS = 30
W_SECTIONS = 12
W_PROJECTS = 3
W_QUANTIFIED = 10
W_ACTION_VERBS = 10
W_LENGTH = 8
L1_RAW_MAX = W_KEYWORDS + W_SECTIONS + W_PROJECTS + W_QUANTIFIED + W_ACTION_VERBS + W_LENGTH  # 73
L1_CAP = 55.0
L2_CAP = 25.0
L3_CAP = 20.0

# ─── Skill aliases (biggest improvement) ─────────────────────────────────────
SKILL_ALIASES = {
    "ml": "machine learning",
    "machine learning": "machine learning",
    "nlp": "natural language processing",
    "natural language processing": "natural language processing",
    "cv": "computer vision",
    "computer vision": "computer vision",
    "dl": "deep learning",
    "deep learning": "deep learning",
    "ai": "artificial intelligence",
    "artificial intelligence": "artificial intelligence",
    "llm": "large language model",
    "llms": "large language model",
    "genai": "generative ai",
    "generative ai": "generative ai",
    "react.js": "react",
    "reactjs": "react",
    "react": "react",
    "next.js": "nextjs",
    "nextjs": "nextjs",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mongo": "mongodb",
    "mongodb": "mongodb",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "py": "python",
    "python": "python",
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "docker": "docker",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "aws": "amazon web services",
    "amazon web services": "amazon web services",
    "gcp": "google cloud",
    "azure": "microsoft azure",
    "sql": "sql",
    "nosql": "nosql",
    "rest": "rest api",
    "rest api": "rest api",
    "graphql": "graphql",
    "langchain": "langchain",
    "chromadb": "chroma",
    "chroma": "chroma",
    "whisper": "whisper",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
}

ACTION_VERBS = {
    "led",
    "built",
    "designed",
    "developed",
    "implemented",
    "improved",
    "optimized",
    "created",
    "managed",
    "delivered",
    "launched",
    "increased",
    "reduced",
    "automated",
    "architected",
    "migrated",
    "scaled",
    "collaborated",
    "mentored",
    "analyzed",
    "engineered",
    "deployed",
    "owned",
    "drove",
    "achieved",
    "streamlined",
    "spearheaded",
    "orchestrated",
    "refactored",
    "shipped",
    "negotiated",
    "established",
    "facilitated",
    "pioneered",
    "transformed",
    "accelerated",
    "enhanced",
    "resolved",
    "executed",
}

SOFT_SKILLS = {
    "leadership",
    "communication",
    "teamwork",
    "problem solving",
    "critical thinking",
    "collaboration",
    "mentoring",
    "ownership",
    "adaptability",
    "time management",
    "presentation",
    "stakeholder",
}

SECTION_PATTERNS = {
    "summary": re.compile(r"\b(summary|profile|objective|about me|professional summary)\b", re.I),
    "experience": re.compile(
        r"\b(experience|work history|employment|professional experience|work experience)\b", re.I
    ),
    "skills": re.compile(
        r"\b(skills|technologies|tech stack|competencies|technical skills)\b", re.I
    ),
    "education": re.compile(
        r"\b(education|university|bachelor|master|degree|b\.?s\.?|m\.?s\.?|phd)\b", re.I
    ),
    "projects": re.compile(
        r"\b(projects|personal projects|key projects|selected projects)\b", re.I
    ),
    "contact": re.compile(
        r"(\b[\w.+-]+@[\w.-]+\.\w{2,}\b)|(\+?\d[\d\s().-]{7,}\d)|(linkedin\.com|github\.com)",
        re.I,
    ),
}

STOP = {
    "and",
    "the",
    "for",
    "with",
    "you",
    "our",
    "are",
    "will",
    "this",
    "that",
    "from",
    "your",
    "have",
    "has",
    "been",
    "using",
    "work",
    "role",
    "team",
    "job",
    "ability",
    "strong",
    "experience",
    "years",
    "year",
    "etc",
    "including",
    "required",
    "preferred",
    "must",
    "should",
    "able",
    "plus",
    "well",
    "good",
    "great",
    "looking",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _canonicalize(skill: str) -> str:
    s = skill.lower().strip()
    return SKILL_ALIASES.get(s, s)


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1 — Rule-based (Improved)
# ═══════════════════════════════════════════════════════════════════════════


def extract_jd_keywords(job_description: str, limit: int = 50) -> list[str]:
    text = _normalize(job_description)
    found: list[str] = []

    # Known skills first
    for skill in extract_skills_rules(job_description):
        found.append(_canonicalize(skill))

    # Token frequency
    tokens = re.findall(r"[a-z][a-z0-9+.#/-]{2,}", text)
    counts = Counter(t for t in tokens if t not in STOP and not t.isdigit())
    for tok, _ in counts.most_common(40):
        canon = _canonicalize(tok)
        if canon not in found:
            found.append(canon)

    # Soft skills
    for soft in SOFT_SKILLS:
        if soft in text and soft not in found:
            found.append(soft)

    # Deduplicate while preserving order
    out, seen = [], set()
    for k in found:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:limit]


def _layer1_keywords(resume_text: str, keywords: list[str]) -> dict[str, Any]:
    resume = _normalize(resume_text)
    matched, missing = [], []

    for kw in keywords:
        # Check both original and canonical forms
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        if re.search(pattern, resume):
            matched.append(kw)
            continue

        # Check aliases
        found = False
        for alias, canon in SKILL_ALIASES.items():
            if canon == kw and re.search(
                r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", resume
            ):
                matched.append(kw)
                found = True
                break
        if not found:
            missing.append(kw)

    ratio = len(matched) / len(keywords) if keywords else 0.0
    return {
        "score": round(ratio * W_KEYWORDS, 1),
        "max": W_KEYWORDS,
        "ratio_pct": round(ratio * 100, 1),
        "matched": matched,
        "missing": missing[:20],
        "total_keywords": len(keywords),
    }


def _layer1_sections(resume_text: str) -> dict[str, Any]:
    present, absent = [], []
    for name, pat in SECTION_PATTERNS.items():
        if pat.search(resume_text or ""):
            present.append(name)
        else:
            absent.append(name)

    core_w = {"experience": 4, "skills": 3, "education": 2, "contact": 2, "summary": 1}
    earned = sum(core_w.get(s, 0) for s in present)
    core_max = sum(core_w.values())
    section_pts = round((earned / core_max) * W_SECTIONS, 1) if core_max else 0
    projects_pts = float(W_PROJECTS) if "projects" in present else 0.0

    return {
        "score": min(float(W_SECTIONS), section_pts),
        "max": W_SECTIONS,
        "projects_bonus": projects_pts,
        "projects_max": W_PROJECTS,
        "present": present,
        "missing": absent,
    }


def _layer1_quantified(resume_text: str) -> dict[str, Any]:
    text = resume_text or ""
    # Strong metrics get higher weight
    strong = re.findall(
        r"(\d+(?:\.\d+)?%|\$\d[\d,]*|\bincreased by\b|\breduced by\b|\bgrew by\b)", text, re.I
    )
    normal = re.findall(r"\b\d+(?:\.\d+)?\b", text)

    score = 0.0
    if strong:
        score = min(W_QUANTIFIED, 4 + len(strong) * 2)
    elif normal:
        score = min(W_QUANTIFIED * 0.7, len(normal) * 1.2)

    return {
        "score": round(score, 1),
        "max": W_QUANTIFIED,
        "evidence_count": len(strong) + len(normal),
        "strong_metrics": strong[:6],
        "samples": (strong + normal)[:8],
    }


def _layer1_action_verbs(resume_text: str) -> dict[str, Any]:
    words = re.findall(r"[A-Za-z]+", resume_text or "")
    lower = [w.lower() for w in words]
    hits = [w for w in lower if w in ACTION_VERBS]
    unique = sorted(set(hits))
    n = len(unique)

    if n >= 10:
        score = float(W_ACTION_VERBS)
    elif n >= 7:
        score = W_ACTION_VERBS * 0.85
    elif n >= 4:
        score = W_ACTION_VERBS * 0.65
    elif n >= 2:
        score = W_ACTION_VERBS * 0.4
    else:
        score = 0.0

    return {
        "score": round(score, 1),
        "max": W_ACTION_VERBS,
        "unique_verbs": unique[:12],
        "count": n,
    }


def _layer1_length_structure(resume_text: str) -> dict[str, Any]:
    words = len(re.findall(r"\b\w+\b", resume_text or ""))
    lines = [ln for ln in (resume_text or "").splitlines() if ln.strip()]
    bullets = sum(1 for ln in lines if re.match(r"^\s*[-•*·]", ln))

    if 300 <= words <= 850:
        length_score, band = float(W_LENGTH), "ideal"
    elif 200 <= words < 300 or 850 < words <= 1100:
        length_score, band = W_LENGTH * 0.75, "acceptable"
    elif 120 <= words < 200 or 1100 < words <= 1400:
        length_score, band = W_LENGTH * 0.45, "weak"
    else:
        length_score, band = W_LENGTH * 0.2, "poor"

    if bullets < 3 and words > 200:
        length_score = max(0, length_score - 1.5)

    return {
        "score": round(max(0.0, length_score), 1),
        "max": W_LENGTH,
        "word_count": words,
        "bullet_lines": bullets,
        "band": band,
        "note": "good bullet usage" if bullets >= 5 else "consider more bullet points",
    }


def layer1_rules(resume_text: str, job_description: str) -> dict[str, Any]:
    keywords = extract_jd_keywords(job_description)
    kw = _layer1_keywords(resume_text, keywords)
    sec = _layer1_sections(resume_text)
    quant = _layer1_quantified(resume_text)
    verbs = _layer1_action_verbs(resume_text)
    length = _layer1_length_structure(resume_text)

    raw = (
        kw["score"]
        + sec["score"]
        + sec.get("projects_bonus", 0)
        + quant["score"]
        + verbs["score"]
        + length["score"]
    )
    raw = min(float(L1_RAW_MAX), raw)
    scaled = round((raw / L1_RAW_MAX) * L1_CAP, 1) if L1_RAW_MAX else 0.0

    summary = [
        f"Keywords: {kw['ratio_pct']}% coverage ({len(kw['matched'])}/{kw['total_keywords']}).",
        f"Sections present: {', '.join(sec['present']) or 'none'}.",
        f"Quantified metrics: {quant['evidence_count']} found.",
        f"Action verbs: {verbs['count']} unique.",
        f"Length: {length['band']} ({length['word_count']} words).",
    ]
    if sec["missing"]:
        summary.append(f"Missing sections: {', '.join(sec['missing'])}.")

    return {
        "layer": 1,
        "name": "rule_based",
        "score": scaled,
        "max": L1_CAP,
        "raw_score": round(raw, 1),
        "raw_max": L1_RAW_MAX,
        "components": {
            "keyword_coverage": kw,
            "sections": sec,
            "quantified_impact": quant,
            "action_verbs": verbs,
            "length_structure": length,
        },
        "matched_keywords": kw["matched"],
        "missing_keywords": kw["missing"],
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 — Semantic (Chroma distances)
# ═══════════════════════════════════════════════════════════════════════════


def layer2_semantic(
    distances: list[float] | None = None,
    chunk_count: int = 0,
) -> dict[str, Any]:
    """
    Convert Chroma distances (cosine distance, lower = better) into 0–L2_CAP points.

    Chroma cosine distance is typically ~0 (identical) to ~2 (opposite).
    We map best-of-k distances to similarity then average.
    """
    if not distances:
        return {
            "layer": 2,
            "name": "semantic_vector",
            "score": 0.0,
            "max": L2_CAP,
            "chunk_count": chunk_count,
            "avg_similarity": 0.0,
            "best_similarity": 0.0,
            "available": False,
            "summary": "No vector matches (Chroma disabled or resume not indexed).",
        }

    sims = []
    for d in distances:
        # cosine distance → similarity in [0, 1]
        sim = max(0.0, min(1.0, 1.0 - float(d) / 2.0))
        sims.append(sim)

    avg_sim = sum(sims) / len(sims)
    best_sim = max(sims)
    # Emphasize best match slightly
    blend = 0.6 * best_sim + 0.4 * avg_sim
    score = round(blend * L2_CAP, 1)

    return {
        "layer": 2,
        "name": "semantic_vector",
        "score": score,
        "max": L2_CAP,
        "chunk_count": chunk_count or len(distances),
        "avg_similarity": round(avg_sim * 100, 1),
        "best_similarity": round(best_sim * 100, 1),
        "available": True,
        "summary": (
            f"Semantic fit: best {round(best_sim * 100, 1)}% · "
            f"avg {round(avg_sim * 100, 1)}% across {len(distances)} chunks."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3 — LLM qualitative (bounded)
# ═══════════════════════════════════════════════════════════════════════════


def layer3_from_llm_payload(payload: dict | None) -> dict[str, Any]:
    """
    Map LLM qualitative assessment into 0–L3_CAP points.
    Expects fields from improved optimize prompt (not a free-form ATS %).
    """
    payload = payload or {}
    # Prefer explicit 1–10 qualitative_fit; clamp
    raw = payload.get("qualitative_fit")
    try:
        fit = float(raw)
        fit = max(1.0, min(10.0, fit))
    except (TypeError, ValueError):
        # Derive from strengths/improvements counts if missing
        strengths = payload.get("strengths") or payload.get("key_improvements") or []
        improvements = payload.get("improvements") or payload.get("gaps") or []
        fit = 5.0 + min(3, len(strengths)) * 0.7 - min(3, len(improvements)) * 0.4
        fit = max(1.0, min(10.0, fit))

    score = round((fit / 10.0) * L3_CAP, 1)
    return {
        "layer": 3,
        "name": "llm_qualitative",
        "score": score,
        "max": L3_CAP,
        "qualitative_fit_1_to_10": round(fit, 1),
        "strengths": (payload.get("strengths") or [])[:6],
        "improvements": (payload.get("improvements") or payload.get("key_improvements") or [])[:6],
        "narrative": payload.get("qualitative_summary") or payload.get("narrative") or "",
        "available": True,
        "summary": f"LLM qualitative fit: {round(fit, 1)}/10 → {score}/{L3_CAP} pts.",
    }


def layer3_unavailable(reason: str = "LLM unavailable") -> dict[str, Any]:
    return {
        "layer": 3,
        "name": "llm_qualitative",
        "score": 0.0,
        "max": L3_CAP,
        "qualitative_fit_1_to_10": None,
        "strengths": [],
        "improvements": [],
        "narrative": "",
        "available": False,
        "summary": reason,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Combine layers
# ═══════════════════════════════════════════════════════════════════════════


def build_display_scores(
    l1: dict[str, Any],
    l2: dict[str, Any],
    l3: dict[str, Any],
    overall: float,
) -> dict[str, Any]:
    """
    Interview-friendly score cards for the UI:

      Overall ATS Score: 87
      Keyword Match: 92%
      Structure & Formatting: 78%
      Relevance: 85%
      Suggestions to improve: [...]
    """
    comps = l1.get("components") or {}
    kw = comps.get("keyword_coverage") or {}
    sec = comps.get("sections") or {}
    length = comps.get("length_structure") or {}
    quant = comps.get("quantified_impact") or {}
    verbs = comps.get("action_verbs") or {}

    # Keyword match → pure %
    keyword_pct = float(kw.get("ratio_pct") or 0.0)

    # Structure & formatting: sections + length + light bullet quality
    sec_max = float(sec.get("max") or W_SECTIONS) or 1.0
    len_max = float(length.get("max") or W_LENGTH) or 1.0
    sec_ratio = float(sec.get("score") or 0) / sec_max
    # projects bonus as small boost
    if float(sec.get("projects_bonus") or 0) > 0:
        sec_ratio = min(1.0, sec_ratio + 0.08)
    len_ratio = float(length.get("score") or 0) / len_max
    structure_pct = round((0.65 * sec_ratio + 0.35 * len_ratio) * 100, 1)

    # Relevance: semantic similarity + LLM qualitative + quantified/verbs signal
    if l2.get("available"):
        # best/avg already 0–100 style in layer2
        sem = (
            float(l2.get("best_similarity") or 0) * 0.6 + float(l2.get("avg_similarity") or 0) * 0.4
        )
    else:
        # fallback: keyword + impact blend when vectors missing
        q_max = float(quant.get("max") or 1) or 1.0
        v_max = float(verbs.get("max") or 1) or 1.0
        sem = (
            keyword_pct * 0.5
            + (float(quant.get("score") or 0) / q_max) * 30
            + (float(verbs.get("score") or 0) / v_max) * 20
        )
    if l3.get("available") and l3.get("qualitative_fit_1_to_10") is not None:
        llm_pct = float(l3["qualitative_fit_1_to_10"]) * 10.0
        relevance_pct = round(0.55 * sem + 0.45 * llm_pct, 1)
    else:
        relevance_pct = round(min(100.0, sem), 1)

    keyword_pct = round(max(0.0, min(100.0, keyword_pct)), 1)
    structure_pct = round(max(0.0, min(100.0, structure_pct)), 1)
    relevance_pct = round(max(0.0, min(100.0, relevance_pct)), 1)

    # Suggestions from gaps
    suggestions: list[str] = []
    missing_kw = (l1.get("missing_keywords") or [])[:8]
    if missing_kw:
        suggestions.append(
            "Add these JD keywords only if true for you: " + ", ".join(missing_kw[:6]) + "."
        )
    missing_sec = (sec.get("missing") or [])[:4]
    if missing_sec:
        suggestions.append("Add missing sections: " + ", ".join(missing_sec) + ".")
    if (quant.get("evidence_count") or 0) < 3:
        suggestions.append("Add more quantifiable achievements (%, $, counts) to impact bullets.")
    if (verbs.get("count") or 0) < 4:
        suggestions.append("Start more bullets with strong action verbs (Led, Built, Improved…).")
    if length.get("band") in {"weak", "poor"}:
        suggestions.append(
            f"Adjust length — currently {length.get('word_count', 0)} words ({length.get('band')})."
        )
    if l2.get("available") and float(l2.get("best_similarity") or 0) < 55:
        suggestions.append("Emphasize experience that maps more closely to the job description.")
    for imp in (l3.get("improvements") or [])[:3]:
        if imp and imp not in suggestions:
            suggestions.append(str(imp))

    if not suggestions:
        suggestions.append(
            "Strong overall fit — tailor a few bullets more specifically to this role."
        )

    return {
        "overall": overall,
        "keyword_match": keyword_pct,
        "structure_formatting": structure_pct,
        "relevance": relevance_pct,
        "suggestions": suggestions[:8],
        "cards": [
            {"key": "keyword_match", "label": "Keyword Match", "value": keyword_pct, "unit": "%"},
            {
                "key": "structure_formatting",
                "label": "Structure & Formatting",
                "value": structure_pct,
                "unit": "%",
            },
            {"key": "relevance", "label": "Relevance", "value": relevance_pct, "unit": "%"},
        ],
    }


def combine_layers(
    l1: dict[str, Any],
    l2: dict[str, Any],
    l3: dict[str, Any],
) -> dict[str, Any]:
    total = round(
        max(0.0, min(100.0, l1["score"] + l2["score"] + l3["score"])),
        1,
    )

    summary = list(l1.get("summary") or [])
    summary.append(l2.get("summary") or "")
    summary.append(l3.get("summary") or "")
    summary = [s for s in summary if s]

    # UI-friendly flat breakdown (compat with existing frontend)
    components = l1.get("components") or {}
    breakdown = {
        "keyword_coverage": {
            **(components.get("keyword_coverage") or {}),
            # remap keys for existing UI
            "ratio": (components.get("keyword_coverage") or {}).get("ratio_pct"),
        },
        "sections": components.get("sections") or {},
        "quantified_impact": components.get("quantified_impact") or {},
        "action_verbs": {
            **(components.get("action_verbs") or {}),
            "unique_verbs": (components.get("action_verbs") or {}).get("unique_verbs") or [],
        },
        "length": components.get("length_structure") or {},
        "semantic": {
            "score": l2.get("score"),
            "max": l2.get("max"),
            "avg_similarity": l2.get("avg_similarity"),
            "best_similarity": l2.get("best_similarity"),
            "available": l2.get("available"),
        },
        "llm_qualitative": {
            "score": l3.get("score"),
            "max": l3.get("max"),
            "fit": l3.get("qualitative_fit_1_to_10"),
            "available": l3.get("available"),
        },
    }

    display = build_display_scores(l1, l2, l3, total)

    return {
        "ats_score": total,
        "layers": {
            "rule_based": l1,
            "semantic": l2,
            "llm_qualitative": l3,
        },
        "breakdown": breakdown,
        "display_scores": display,
        "matched_keywords": l1.get("matched_keywords") or [],
        "missing_keywords": l1.get("missing_keywords") or [],
        "summary": summary,
        "suggestions": display.get("suggestions") or [],
        "method": "hybrid-3layer-v2",
        "layer_scores": {
            "rules": l1["score"],
            "semantic": l2["score"],
            "llm": l3["score"],
            "rules_max": L1_CAP,
            "semantic_max": L2_CAP,
            "llm_max": L3_CAP,
        },
    }


def analyze_resume(
    resume_text: str,
    job_description: str,
    *,
    semantic_distances: list[float] | None = None,
    semantic_chunk_count: int = 0,
    llm_qualitative: dict | None = None,
) -> dict[str, Any]:
    """Full 3-layer analysis for a resume against a JD."""
    l1 = layer1_rules(resume_text, job_description)
    l2 = layer2_semantic(semantic_distances, semantic_chunk_count)
    l3 = (
        layer3_from_llm_payload(llm_qualitative)
        if llm_qualitative is not None
        else layer3_unavailable("LLM qualitative not provided")
    )
    return combine_layers(l1, l2, l3)


def score_before_after(
    original_text: str,
    tailored_text: str,
    job_description: str,
    *,
    semantic_distances: list[float] | None = None,
    semantic_chunk_count: int = 0,
    llm_qualitative: dict | None = None,
) -> dict[str, Any]:
    """Score original vs tailored with shared semantic context."""
    before = analyze_resume(
        original_text,
        job_description,
        semantic_distances=semantic_distances,
        semantic_chunk_count=semantic_chunk_count,
        llm_qualitative=None,  # baseline rules+semantic only
    )
    after = analyze_resume(
        tailored_text,
        job_description,
        semantic_distances=semantic_distances,
        semantic_chunk_count=semantic_chunk_count,
        llm_qualitative=llm_qualitative,
    )
    return {
        "before": before["ats_score"],
        "after": after["ats_score"],
        "delta": round(after["ats_score"] - before["ats_score"], 1),
        "after_detail": after,
        "before_detail": before,
    }


# Back-compat aliases used by older imports / tests
def compute_ats_score(resume_text: str, job_description: str) -> dict[str, Any]:
    return analyze_resume(resume_text, job_description)
