"""Extract skills from job descriptions — rule-based + optional LLM polish."""

from __future__ import annotations

import re

from langchain_core.prompts import ChatPromptTemplate

from app.services.ai_optimizer import _extract_json, get_llm

# Common tech/soft skills dictionary for fast offline extraction
KNOWN_SKILLS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "node.js",
    "fastapi",
    "django",
    "flask",
    "sql",
    "postgresql",
    "mysql",
    "mongodb",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "redis",
    "graphql",
    "rest",
    "api",
    "git",
    "ci/cd",
    "linux",
    "html",
    "css",
    "tailwind",
    "vue",
    "angular",
    "c++",
    "c#",
    "go",
    "rust",
    "kotlin",
    "swift",
    "scala",
    "r",
    "matlab",
    "pandas",
    "numpy",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "spark",
    "hadoop",
    "airflow",
    "kafka",
    "elasticsearch",
    "terraform",
    "ansible",
    "leadership",
    "communication",
    "agile",
    "scrum",
    "project management",
    "system design",
    "microservices",
    "machine learning",
    "data analysis",
    "nlp",
    "llm",
    "langchain",
    "prompt engineering",
    "excel",
    "tableau",
    "power bi",
    "figma",
    "product management",
    "stakeholder management",
    "unit testing",
    "pytest",
    "jest",
    "selenium",
    "security",
    "oauth",
]


def extract_skills_rules(job_description: str) -> list[str]:
    text = job_description.lower()
    found: list[str] = []
    for skill in KNOWN_SKILLS:
        # word-boundary-ish match
        pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            # pretty label
            label = (
                skill.upper()
                if skill in {"sql", "aws", "gcp", "api", "nlp", "llm", "ci/cd"}
                else skill.title()
            )
            if skill == "next.js":
                label = "Next.js"
            elif skill == "node.js":
                label = "Node.js"
            elif skill == "c++":
                label = "C++"
            elif skill == "c#":
                label = "C#"
            found.append(label)
    # de-dupe preserve order
    seen = set()
    out = []
    for s in found:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def extract_skills_llm(job_description: str) -> dict:
    prompt = ChatPromptTemplate.from_template(
        """Extract skills from this job description.
Return ONLY valid JSON:
{{
  "must_have": ["skill1", "skill2"],
  "nice_to_have": ["skill3"],
  "skills": ["all unique skills combined"]
}}

Job Description:
{job}
"""
    )
    try:
        chain = prompt | get_llm()
        result = chain.invoke({"job": job_description[:6000]})
        content = result.content if hasattr(result, "content") else str(result)
        data = _extract_json(content)
        skills = data.get("skills") or []
        must = data.get("must_have") or []
        nice = data.get("nice_to_have") or []
        if not skills:
            skills = list(dict.fromkeys([*must, *nice]))
        return {
            "skills": [str(s) for s in skills][:40],
            "must_have": [str(s) for s in must][:20],
            "nice_to_have": [str(s) for s in nice][:20],
        }
    except Exception as e:
        print(f"skill extract llm error: {e}")
        rules = extract_skills_rules(job_description)
        return {"skills": rules, "must_have": rules[:8], "nice_to_have": rules[8:16]}


def extract_skills(job_description: str, use_llm: bool = True) -> dict:
    rules = extract_skills_rules(job_description)
    if not use_llm:
        return {"skills": rules, "must_have": rules[:8], "nice_to_have": rules[8:]}
    llm = extract_skills_llm(job_description)
    # merge rule hits that LLM missed
    merged = list(dict.fromkeys([*llm.get("skills", []), *rules]))
    return {
        "skills": merged[:40],
        "must_have": llm.get("must_have") or rules[:8],
        "nice_to_have": llm.get("nice_to_have") or rules[8:16],
    }
