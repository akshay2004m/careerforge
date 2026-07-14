import os
import asyncio
from app.core.config import settings
from app.services.ai_optimizer import _run_llm_optimize

async def main():
    resume = """
    Akshay Vadugu
    Software Engineer at Accenture
    Experience: 2 years building web applications.
    """
    job = """
    We are looking for a machine learning fresher with some web app experience.
    Must know CI/CD and ML integration.
    """
    try:
        print("Running optimization...")
        result = _run_llm_optimize(
            original_text=resume,
            job_description=job,
            focus="",
            pre_rules={"score": 50, "max": 100, "missing_keywords": ["CI/CD", "Machine Learning"]}
        )
        print("Result:", result)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
