"""
Backward-compatible re-exports.

Prefer importing from `app.services.ats_analyzer` (3-layer hybrid ATS).
"""

from app.services.ats_analyzer import (  # noqa: F401
    analyze_resume,
    combine_layers,
    compute_ats_score,
    extract_jd_keywords,
    layer1_rules,
    layer2_semantic,
    layer3_from_llm_payload,
    score_before_after,
)
