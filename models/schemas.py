from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class CareerPathDetail(BaseModel):
    title: str
    match_score: int
    matched_skills: List[str]
    missing_skills: List[Any]

# 🔥 إضافة كلاس جديد يمثل شكل تقرير الـ ATS
class ATSAnalysisDetail(BaseModel):
    is_compliant: bool
    score: int
    issues: List[str]
    passed: List[str]
    ai_ats_report: str

class CVAnalysisResponse(BaseModel):
    detected_language: str
    extracted_skills: List[str]
    experience_level: str
    career_paths: List[CareerPathDetail]
    top_recommendation: str
    is_path_suitable: bool
    ai_path_feedback: str
    ats_analysis: ATSAnalysisDetail 