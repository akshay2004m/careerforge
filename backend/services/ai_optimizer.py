from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from app.core.config import settings
import json

llm = ChatGroq(
    groq_api_key=settings.GROQ_API_KEY,
    model_name="llama-3.1-70b-versatile",
    temperature=0.3
)

def optimize_resume(original_text: str, job_description: str):
    prompt = PromptTemplate(
        input_variables=["resume", "job"],
        template="""You are an expert career coach and ATS specialist.
        
        Original Resume:
        {resume}
        
        Job Description:
        {job}
        
        Provide response in valid JSON format:
        {{
            "tailored_resume": "Full tailored resume text",
            "ats_score": 85,
            "key_improvements": ["improvement1", "improvement2"],
            "cover_letter": "Full cover letter"
        }}
        """
    )

    chain = LLMChain(llm=llm, prompt=prompt)
    result = chain.run(resume=original_text, job=job_description)
    
    try:
        return json.loads(result)
    except:
        return {
            "tailored_resume": result,
            "ats_score": 75,
            "key_improvements": [],
            "cover_letter": "Cover letter generation failed. Please try again."
        }