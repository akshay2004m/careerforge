from app.services.ats_analyzer import (
    combine_layers,
    layer1_rules,
    layer2_semantic,
    layer3_from_llm_payload,
    score_before_after,
)
from app.services.ats_scorer import compute_ats_score

SAMPLE_RESUME = """
Jane Doe
jane@example.com | linkedin.com/in/jane

Summary
Software engineer with API experience.

Experience
- Built REST APIs with Python and FastAPI
- Improved query performance by 40%
- Led a team of 3 engineers on AWS migrations

Skills
Python, FastAPI, SQL, AWS, Docker

Projects
- Open-source CLI tools for deploy automation

Education
B.S. Computer Science
"""

SAMPLE_JD = """
We need a Senior Software Engineer with Python, FastAPI, SQL, cloud (AWS),
Docker, leadership skills, and experience shipping reliable APIs.
"""


def test_layer1_rules_has_components():
    l1 = layer1_rules(SAMPLE_RESUME, SAMPLE_JD)
    assert l1["score"] <= l1["max"]
    assert l1["score"] > 0
    assert "keyword_coverage" in l1["components"]
    assert len(l1["matched_keywords"]) >= 1


def test_layer2_semantic_from_distances():
    # Low distances → high score
    good = layer2_semantic([0.15, 0.25, 0.3], chunk_count=3)
    assert good["available"] is True
    assert good["score"] > 10
    empty = layer2_semantic(None)
    assert empty["score"] == 0
    assert empty["available"] is False


def test_layer3_qualitative_bounded():
    l3 = layer3_from_llm_payload(
        {
            "qualitative_fit": 8,
            "strengths": ["Clear metrics"],
            "improvements": ["Add cloud keywords"],
            "qualitative_summary": "Strong backend fit.",
        }
    )
    assert 0 < l3["score"] <= 20
    assert l3["qualitative_fit_1_to_10"] == 8


def test_three_layer_combine():
    l1 = layer1_rules(SAMPLE_RESUME, SAMPLE_JD)
    l2 = layer2_semantic([0.2, 0.3])
    l3 = layer3_from_llm_payload({"qualitative_fit": 7, "strengths": ["x"], "improvements": []})
    result = combine_layers(l1, l2, l3)
    assert 0 <= result["ats_score"] <= 100
    assert result["method"] == "hybrid-3layer-v2"
    assert "rule_based" in result["layers"]
    assert "semantic" in result["layers"]
    assert "llm_qualitative" in result["layers"]
    assert (
        result["layer_scores"]["rules"]
        + result["layer_scores"]["semantic"]
        + result["layer_scores"]["llm"]
        == result["ats_score"]
        or abs(
            result["layer_scores"]["rules"]
            + result["layer_scores"]["semantic"]
            + result["layer_scores"]["llm"]
            - result["ats_score"]
        )
        < 0.2
    )
    # Professional display cards
    ds = result["display_scores"]
    assert 0 <= ds["keyword_match"] <= 100
    assert 0 <= ds["structure_formatting"] <= 100
    assert 0 <= ds["relevance"] <= 100
    assert ds["overall"] == result["ats_score"]
    assert len(ds["suggestions"]) >= 1
    assert len(ds["cards"]) == 3


def test_compute_ats_score_compat():
    result = compute_ats_score(SAMPLE_RESUME, SAMPLE_JD)
    assert 0 <= result["ats_score"] <= 100
    assert result["method"] == "hybrid-3layer-v2"


def test_score_before_after_improves_with_better_resume():
    weak = "John\nI like coding."
    comp = score_before_after(
        weak,
        SAMPLE_RESUME,
        SAMPLE_JD,
        semantic_distances=[0.2],
        llm_qualitative={"qualitative_fit": 8, "strengths": ["metrics"], "improvements": []},
    )
    assert comp["after"] >= comp["before"]
