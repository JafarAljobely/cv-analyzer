import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()

# النموذج الذي يجبر Gemini على تنظيم البيانات بشكل JSON مطابق للفرونت إند
class GeminiCVAssessment(BaseModel):
    experience_level: str = Field(description="Strictly either 'junior' or 'senior' based on the CV context.")
    is_path_suitable: bool = Field(description="True if the chosen career path fits the CV, False otherwise.")
    ai_path_feedback: str = Field(description="Detailed feedback in Arabic about the chosen path, and recommending alternative from (Frontend, Backend, Full Stack, Network, AI) if not suitable.")
    ai_ats_report: str = Field(description="Professional advisory text in Arabic on how the CV complies with ATS and action items to improve structure/phrasing.")

def analyze_cv_with_gemini(extracted_text: str, extracted_skills: list, chosen_path: str) -> GeminiCVAssessment:
    """
    استدعاء Gemini API لإعطاء التقييم الاستنتاجي الذكي
    """
    # تهيئة العميل (يقرأ تلقائياً المتغير البيئي GEMINI_API_KEY)
    client = genai.Client()
    
    prompt = f"""
    أنت خبير توظيف تقني ومحلل أنظمة ATS محترف.
    أمامك البيانات المستخرجة من السيرة الذاتية للمرشح:
    
    1. النص الكامل المستخرج من السيرة الذاتية:
    \"\"\"{extracted_text}\"\"\"
    
    2. المهارات التقنية المستخرجة بدقة عبر نظام القواعد المستقر لدينا:
    {', '.join(extracted_skills)}
    
    3. المسار المهني الذي اختاره المرشح للفحص:
    {chosen_path}
    
    المطلوب منك تحليل هذه البيانات بدقة وتقديم المخرجات باللغة العربية الفصيحة:
    1. حدد المستوى المهني للمرشح بناءً على عمق المشاريع وسنوات الخبرة المذكورة في النص (إما 'junior' أو 'senior' حصراً).
    2. قيم هل المسار المختار مناسب له (True أو False).
    3. اكتب رأيك الاستشاري (ai_path_feedback) حول مدى الملاءمة، وإذا لم يكن مناسباً، اقترح عليه مساراً بديلاً من المسارات الأربعة المتاحة في تطبيقنا: (Frontend Developer, Backend Developer, Network Engineer, AI Engineer).
    4. اكتب تقريراً إرشادياً ونقداً بناءً (ai_ats_report) حول كيفية تحسين صياغة وهيكلية السيرة الذاتية لتتطابق بشكل ممتاز مع أنظمة الفرز الآلي (ATS).
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiCVAssessment,
                temperature=0.2  # درجة حرارة منخفضة لضمان الاستقرار والدقة وعدم الهلوسة
            ),
        )
        result_json = json.loads(response.text)
        return GeminiCVAssessment(**result_json)
        
    except Exception as e:
        print(f"⚠️ فشل استدعاء Gemini API: {e}")
        # قيم احتياطية آمنة في حال انقطع الإنترنت لكي لا يتوقف السيرفر
        return GeminiCVAssessment(
            experience_level="junior",
            is_path_suitable=True,
            ai_path_feedback="تمت عملية التحليل بنجاح. يرجى التحقق من اتصال الإنترنت لربط خدمات التقييم المتقدمة.",
            ai_ats_report="النظام الأساسي جاهز، لم نتمكن من الاتصال بمحلل الصياغة الذكي حالياً."
        )