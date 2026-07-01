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

class CVAnalysisResponse(BaseModel):
    detected_language: str
    extracted_skills: List[str]
    experience_level: str  # 🔥 جديد: "junior" أو "senior"
    career_paths: List[CareerPathDetail]
    top_recommendation: str
    ats_analysis: ATSAnalysisDetail  # 🔥 ربط التقرير بالرد النهائي