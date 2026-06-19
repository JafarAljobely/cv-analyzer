import re
import os
import json
from thefuzz import fuzz
import pdfplumber

# ==========================================
# 1. قراءة قاعدة البيانات ديناميكياً من الـ JSON
# ==========================================

# تحديد مسار مجلد الـ data وملف الـ json بناءً على موقع ملف analyze.py الحالي
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE_PATH = os.path.join(BASE_DIR, "data", "skills_db.json")

# قراءة البيانات وتخزينها في المتغير الأساسي SKILLS_DB عند إقلاع السيرفر
with open(JSON_FILE_PATH, "r", encoding="utf-8") as file:
    _raw = json.load(file)
    SKILLS_DB = _raw.get("SKILLS_DB", _raw)


# القاموس المساعد للمرادفات والاختصارات الشائعة
SKILL_ALIASES = {
    "javascript": ["js", "es6", "vanillajs"],
    "react.js": ["react", "reactjs", "react native"],
    "node.js": ["node", "nodejs"],
    "vue.js": ["vue", "vuejs"],
    "rest api": ["restful api", "apis", "rest", "restful"],
    "sql": ["mysql", "postgresql", "sqlite", "nosql", "database"],
    "git": ["github", "gitlab", "version control"],
    "fastapi": ["fast api"],
    "machine learning": ["ml", "scikit-learn", "sklearn"],
    "deep learning": ["dl", "neural networks"],
    "nlp": ["natural language processing", "spacy", "nltk"],
}

# ==========================================
# 2. دالة استخراج المهارات من النص (OCR Text)
# ==========================================
def extract_skills(ocr_data):
    """
    تستخرج المهارات التي يمتلكها المستخدم بناءً على مقارنتها بقاعدة البيانات وقاموس المرادفات
    """
    if not ocr_data:
        return []

    # تجميع الكتل النصية القادمة من المعالجة في نص واحد وبأحرف صغيرة
    full_text = " ".join([item[1] for item in ocr_data if len(item) > 1 and item[1]]).lower()
    
    # تنظيف النص من الرموز الخاصة لتسهيل المطابقة الدقيقة
    full_text_clean = re.sub(r'[^\w\s\.\-\+#]', ' ', full_text)
    
    found_skills = set()

    # 1. تجميع كل الكلمات الفريدة من قاعدة البيانات لفحصها
    all_db_skills = set()
   # for career, data in SKILLS_DB.get("career_paths", {}).items():
    for career, data in SKILLS_DB.items():
        all_db_skills.update(data.get("required_skills", []))
        all_db_skills.update(data.get("nice_to_have", []))

    # 2. فحص وجود المهارات أو مرادفاتها داخل النص المنظف
    for skill in all_db_skills:
        skill_lower = skill.lower()
        skill_clean = skill_lower.replace(" ", "")
        
        # البحث عن الاسم الأصلي للمهارة بحدود كلمة كاملة
        if re.search(r'\b' + re.escape(skill_lower) + r'\b', full_text_clean):
            found_skills.add(skill)
            continue
            
        # البحث عن اسم المهارة بدون مسافات (مثل React.js كـ Reactjs)
        if skill_clean in full_text_clean.replace(" ", ""):
            found_skills.add(skill)
            continue

        # فحص المرادفات والاختصارات الشائعة للمهارة
        aliases = SKILL_ALIASES.get(skill_lower, [])
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', full_text_clean):
                found_skills.add(skill)
                break

    return sorted(list(found_skills))

# ==========================================
# 3. دالة مطابقة المهارات وحساب المسار الوظيفي
# ==========================================
def analyze_career_paths(extracted_list):
    """
    تقارن مهارات المستخدم المستخرجة مع كل المسارات الوظيفية وتحسب النسبة المئوية للتوافق
    """
    career_paths_raw = {}
    extracted_clean = [s.lower().replace(" ", "") for s in extracted_list]

    def is_skill_covered(skill_name, extracted_list_clean):
        skill_lower = skill_name.lower()
        skill_clean = skill_lower.replace(" ", "")
        
        # مطابقة مباشرة
        if skill_clean in extracted_list_clean:
            return True
            
        # مطابقة بناءً على المرادفات
        aliases = SKILL_ALIASES.get(skill_lower, [])
        for alias in aliases:
            alias_clean = alias.replace(" ", "")
            if alias_clean in extracted_list_clean:
                return True
                
        return False

    # فحص وحساب توافق المهارات لكل مسار متوفر في الـ JSON
    # for career_title, career_data in SKILLS_DB.get("career_paths", {}).items():
    for career_title, career_data in SKILLS_DB.items():
        required = career_data.get("required_skills", [])
        nice_to_have = career_data.get("nice_to_have", [])

        matched_required = [s for s in required if is_skill_covered(s, extracted_clean)]
        matched_nice = [s for s in nice_to_have if is_skill_covered(s, extracted_clean)]

        missing_required = [{"skill": s, "importance": "required"} for s in required if not is_skill_covered(s, extracted_clean)]
        missing_nice = [{"skill": s, "importance": "nice_to_have"} for s in nice_to_have if not is_skill_covered(s, extracted_clean)]

        # حساب النقاط (الأساسية وزنها 20، والإضافية وزنها 10)
        user_points = (len(matched_required) * 20) + (len(matched_nice) * 10)
        base_target_points = len(required) * 20 if required else 20
        match_score = int(min((user_points / base_target_points) * 100, 100))

        career_paths_raw[career_title] = {
            "title": career_title,
            "match_score": match_score,
            "matched_skills": matched_required + matched_nice,
            "missing_skills": missing_required + missing_nice
        }

    # ترتيب المسارات من الأعلى توافقاً إلى الأقل
    sorted_titles = sorted(career_paths_raw.keys(), key=lambda k: career_paths_raw[k]["match_score"], reverse=True)
    
    return {
        "career_paths": [career_paths_raw[t] for t in sorted_titles],
        "top_recommendation": sorted_titles[0] if sorted_titles else "Software Engineer"
    }

# ==========================================
# 4. فحص التوافق الفعلي والحقيقي مع أنظمة ATS
# ==========================================
def analyze_cv_ats(pdf_path: str, extracted_text: str, expected_skills: list) -> dict:
    """
    تقوم بفحص حقيقي لبنية الملف وهيكليته ومصطلحاته لتقييم توافقه مع الـ ATS
    """
    issues = []
    passed = []
    score = 100

    has_tables = False
    # 1. فحص وجود جداول وأعمدة حقيقية بالاعتماد على pdfplumber
    if pdf_path.endswith('.pdf'):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    if page.extract_tables():
                        has_tables = True
                        break
        except Exception:
            pass

    if has_tables:
        issues.append("تم اكتشاف جداول أو تخطيط أعمدة متعددة. بعض أنظمة ATS تفشل في معالجتها، يفضل استخدام نصوص مباشرة متتالية.")
        score -= 20
    else:
        passed.append("بنية السيرة الذاتية ممتازة وخالية من الجداول المعقدة.")

    # 2. فحص العناوين الرئيسية القياسية والمباشرة
    standard_headings = ["experience", "education", "skills", "summary", "profile", "projects", "work"]
    text_lower = extracted_text.lower()
    found_headings = [h for h in standard_headings if re.search(r'\b' + h + r'\b', text_lower)]

    if len(found_headings) >= 2:
        passed.append(f"تم استخدام عناوين أقسام قياسية واضحة لسهولة الفهرسة الآلية مثل ({', '.join(found_headings[:2])}).")
    else:
        issues.append("العناوين الرئيسية للأقسام غير واضحة أو تستخدم مصطلحات إبداعية. التزم بالعناوين القياسية مثل Experience و Skills.")
        score -= 15

    # 3. فحص الكلمات المفتاحية الدقيقة وتطابقها مع الوصف الوظيفي للمسار
    matched_keywords = [skill for skill in expected_skills if skill.lower() in text_lower]
    match_ratio = len(matched_keywords) / len(expected_skills) if expected_skills else 0
    
    if match_ratio >= 0.4:
        passed.append("تم تضمين المصطلحات التقنية الأساسية والكلمات المفتاحية المطلوبة بدقة.")
    else:
        issues.append("السيرة الذاتية تفتقر للكلمات المفتاحية والمصطلحات الدقيقة الخاصة بهذا المسار الوظيفي.")
        score -= 15

    score = max(0, min(100, score))
    is_compliant = score >= 70

    return {
        "is_compliant": is_compliant,
        "score": score,
        "issues": issues,
        "passed": passed
    }