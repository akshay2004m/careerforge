import pytest
from app.services.ats_analyzer import (
    extract_jd_keywords,
    layer1_rules,
    W_KEYWORDS,
    W_SECTIONS,
    W_PROJECTS,
    W_QUANTIFIED,
    W_ACTION_VERBS,
    W_LENGTH,
)

def test_extract_jd_keywords():
    jd = "Looking for a Software Engineer with experience in Python, React, and SQL. Must have AWS knowledge."
    keywords = extract_jd_keywords(jd)
    # The extraction logic extracts based on KNOWN_SKILLS and token frequencies
    assert "python" in keywords
    assert "react" in keywords
    assert "sql" in keywords
    assert "aws" in keywords

def test_layer1_rules_perfect_resume():
    jd = "We need python, react, sql, aws, and docker."
    resume_text = """
    Jane Doe - Software Engineer
    Professional Summary: Experienced developer.
    Skills: Python, React, SQL, AWS, Docker.
    Experience: 
    - Designed and engineered a scalable system.
    - Improved performance by 50% and increased revenue by 20%.
    Projects: Built a personal website.
    Education: B.S. in Computer Science.
    """
    
    # Needs some length to score well on length penalty
    # Just repeating some text to artificially boost length for length rule
    resume_text += " " + ("developer " * 300)
    
    result = layer1_rules(resume_text, jd)
    components = result["components"]
    
    # Keywords
    assert len(components["keyword_coverage"]["matched"]) >= 4
    
    # Sections (Summary, Skills, Experience, Projects, Education all present)
    assert len(components["sections"]["present"]) >= 5
    
    # Projects
    assert components["sections"].get("projects_bonus", 0) > 0
    
    # Quantified
    assert components["quantified_impact"]["evidence_count"] >= 2
    
    # Action verbs
    assert components["action_verbs"]["count"] > 0
    
    # The total score is capped at 55.0
    assert result["score"] <= 55.0
    assert result["score"] > 40.0

def test_layer1_rules_poor_resume():
    jd = "python react sql"
    resume_text = "I am a guy who likes computers."
    
    result = layer1_rules(resume_text, jd)
    components = result["components"]
    
    # No keywords, no sections, no projects, no quantities, no verbs
    assert len(components["keyword_coverage"]["matched"]) == 0
    assert len(components["sections"]["present"]) == 0
    assert components["sections"].get("projects_bonus", 0) == 0
    assert components["quantified_impact"]["evidence_count"] == 0
    assert components["action_verbs"]["count"] == 0
    
    # Length penalty should be high because it's too short
    assert components["length_structure"]["score"] < W_LENGTH
    
    assert result["score"] < 10.0
