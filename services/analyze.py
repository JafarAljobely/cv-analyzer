import re
import os
import json
import math
from thefuzz import fuzz
import pdfplumber
from docx import Document


def _edit_distance(a: str, b: str) -> int:
    """
    حساب Levenshtein edit distance بين كلمتين (أقل عدد تعديلات حرف واحد
    لتحويل كلمة لأخرى). تُستخدم لاكتشاف أخطاء OCR الشائعة (استبدال حرف
    متشابه بصرياً مثل G/C أو O/0) بدون الحاجة لقاموس تصحيحات يدوي.
    """
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    previous_row = list(range(len(b) + 1))
    for i, c1 in enumerate(a):
        current_row = [i + 1]
        for j, c2 in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


# الطول الأدنى لاسم المهارة بقاعدة البيانات لتطبيق المطابقة المتسامحة (fuzzy).
# كلمات أقصر من هذا معرّضة لتطابقات عرضية مع كلمات عادية (مثل Git/Get)
# فنستثنيها من هذا الفحص حفاظاً على الدقة.
MIN_LENGTH_FOR_FUZZY = 5
# أقصى عدد تعديلات حرف مسموح به لاعتبار الكلمتين "نفس المهارة" مع خطأ OCR
MAX_EDIT_DISTANCE_FOR_FUZZY = 1

# ==========================================
# 1. قراءة قاعدة البيانات ديناميكياً من الـ JSON
# ==========================================

# تحديد مسار مجلد الـ data وملف الـ json بناءً على موقع ملف analyze.py الحالي
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE_PATH = os.path.join(BASE_DIR, "data", "skills_db.json")

# قراءة البيانات وتخزينها في المتغيرات الأساسية عند إقلاع السيرفر
# 🔥 ملاحظة: الملف الجديد يحوي مفتاحين: GLOBAL_SKILLS_POOL (مستودع مهارات عام وموسع
# يشمل مجالات إضافية مثل Mobile/DevOps/Design حتى لو لا يوجد لها مسار وظيفي بالكود)
# و SKILLS_DB (المسارات الوظيفية الخمسة المستخدمة لحساب نسبة التوافق فقط)
with open(JSON_FILE_PATH, "r", encoding="utf-8") as file:
    _raw_db = json.load(file)
    SKILLS_DB = _raw_db.get("SKILLS_DB", {})
    GLOBAL_SKILLS_POOL = _raw_db.get("GLOBAL_SKILLS_POOL", [])


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

# مهارات أساسية تُستنتج ضمنياً عند وجود مهارة/فريموورك مبني عليها، حتى لو
# لم يذكرها الشخص صراحة بالـ CV. مثلاً: امتلاك React.js يستحيل عملياً
# بدون معرفة HTML/CSS/JavaScript، فلا يُعقل اعتبارها "مهارات ناقصة".
# هذا قابل للتوسعة بسهولة بإضافة مفاتيح جديدة دون تكرار أي منطق.
IMPLIED_SKILLS = {
    "react.js": ["HTML", "CSS", "JavaScript"],
    "vue.js": ["HTML", "CSS", "JavaScript"],
    "angular": ["HTML", "CSS", "JavaScript", "TypeScript"],
    "next.js": ["HTML", "CSS", "JavaScript", "React.js"],
    "nuxt.js": ["HTML", "CSS", "JavaScript", "Vue.js"],
    "svelte": ["HTML", "CSS", "JavaScript"],
    "django": ["Python"],
    "flask": ["Python"],
    "fastapi": ["Python"],
    "spring": ["Java"],
    "spring boot": ["Java"],
    "laravel": ["PHP"],
    "ruby on rails": ["Ruby"],
    "node.js": ["JavaScript"],
    "express.js": ["Node.js", "JavaScript"],
    ".net": ["C#"],
}

# ==========================================
# 1.5 استنتاج مستوى الخبرة (junior / senior)
# ==========================================

EXPERIENCE_LEVEL_DEFAULT = "junior"

SENIOR_TITLE_KEYWORDS = [
    "senior", "lead", "principal", "architect", "head of",
    "خبير", "كبير مهندسين", "قائد فريق"
]
JUNIOR_TITLE_KEYWORDS = [
    "junior", "intern", "trainee", "fresh graduate", "entry level", "entry-level",
    "متدرب", "خريج حديث", "مبتدئ"
]

# أنماط نصية بسيطة (عربي/انكليزي) للبحث عن أرقام جنب كلمات الخبرة
YEARS_EXPERIENCE_PATTERNS = [
    r'(\d+)\s*\+?\s*(?:years?|yrs?)\s*(?:of)?\s*experience',
    r'experience\s*(?:of)?\s*(\d+)\s*\+?\s*(?:years?|yrs?)',
    r'(\d+)\s*\+?\s*سن(?:ة|وات)\s*خبرة',
    r'خبرة\s*(?:تزيد\s*عن\s*)?(\d+)\s*\+?\s*سن(?:ة|وات)',
]

SENIOR_YEARS_THRESHOLD = 4
SENIOR_SKILLS_COUNT_THRESHOLD = 12


def extract_years_of_experience(text: str) -> int:
    """
    يدور على أنماط نصية بسيطة (عربي/انكليزي) لاستخراج عدد سنوات الخبرة
    المذكورة صراحة بالنص. يرجع أعلى رقم تم العثور عليه، أو 0 إن لم يُعثر
    على أي تطابق.
    """
    if not text:
        return 0

    found_numbers = []
    for pattern in YEARS_EXPERIENCE_PATTERNS:
        for m in re.findall(pattern, text):
            try:
                found_numbers.append(int(m))
            except (ValueError, TypeError):
                continue

    return max(found_numbers) if found_numbers else 0


def detect_experience_level(full_text: str, extracted_skills: list) -> str:
    """
    تستنتج مستوى خبرة المستخدم (junior/senior) من 3 مؤشرات تُحتسب كأصوات:
    سنوات الخبرة المصرّح بها، عدد المهارات المستخرجة، وكلمات مفتاحية
    بالعناوين الوظيفية. عند تعادل الأصوات أو عدم كفاية المؤشرات، نفترض
    "junior" افتراضياً (الخيار الأكثر أماناً، لا يستبعد متطلبات أساسية).
    """
    text_lower = (full_text or "").lower()
    senior_votes = 0
    junior_votes = 0

    # 1) سنوات الخبرة
    years = extract_years_of_experience(text_lower)
    if years >= SENIOR_YEARS_THRESHOLD:
        senior_votes += 1
    elif years > 0:
        junior_votes += 1

    # 2) عدد المهارات المستخرجة
    skills_count = len(extracted_skills or [])
    if skills_count >= SENIOR_SKILLS_COUNT_THRESHOLD:
        senior_votes += 1
    else:
        junior_votes += 1

    # 3) كلمات مفتاحية بالعناوين الوظيفية
    has_senior_kw = any(re.search(r'\b' + re.escape(k) + r'\b', text_lower) for k in SENIOR_TITLE_KEYWORDS)
    has_junior_kw = any(re.search(r'\b' + re.escape(k) + r'\b', text_lower) for k in JUNIOR_TITLE_KEYWORDS)

    if has_senior_kw and not has_junior_kw:
        senior_votes += 1
    elif has_junior_kw and not has_senior_kw:
        junior_votes += 1

    return "senior" if senior_votes > junior_votes else EXPERIENCE_LEVEL_DEFAULT



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

    # 1. الفحص يتم على المستودع العام للمهارات (يشمل كل المجالات حتى لو
    #    لم يكن لها مسار وظيفي معرّف بالكود، مثل Mobile/DevOps/Design/QA)
    all_db_skills = set(GLOBAL_SKILLS_POOL)

    # تجزيء النص لكلمات منفردة (نحتاجها لاحقاً لمطابقة fuzzy كلمة-بكلمة،
    # وليس فحص الكلمة داخل النص الكامل كسلسلة طويلة، لأن edit_distance
    # بين كلمة قصيرة ونص طويل غير منطقي وغير دقيق)
    text_words = full_text_clean.split()

    # 2. فحص وجود المهارات أو مرادفاتها داخل النص المنظف
    for skill in all_db_skills:
        skill_lower = skill.lower()
        skill_clean = skill_lower.replace(" ", "")

        # البحث عن الاسم الأصلي للمهارة بحدود كلمة كاملة
        if re.search(r'\b' + re.escape(skill_lower) + r'\b', full_text_clean):
            found_skills.add(skill)
            continue

        # البحث عن اسم المهارة بدون مسافات (مثل React.js كـ Reactjs).
        # هذا الفحص مقيّد بالمهارات المركبة فقط (تحتوي مسافة أو نقطة أو
        # رمز خاص بأصلها)، لأن تطبيقه على مهارة بكلمة واحدة بسيطة (مثل
        # "Go") يطابقها بالخطأ كـ substring داخل كلمات أطول غير متعلقة
        # (مثل "Algorithm")، وهي حالة مغطاة أصلاً بفحص حدود الكلمة أعلاه.
        is_compound_skill = (" " in skill_lower) or ("." in skill_lower) or ("-" in skill_lower)
        if is_compound_skill and skill_clean in full_text_clean.replace(" ", ""):
            found_skills.add(skill)
            continue

        # فحص المرادفات والاختصارات الشائعة للمهارة
        aliases = SKILL_ALIASES.get(skill_lower, [])
        matched_via_alias = False
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', full_text_clean):
                found_skills.add(skill)
                matched_via_alias = True
                break
        if matched_via_alias:
            continue

        # 3. fallback أخير: مطابقة متسامحة (fuzzy) لاكتشاف أخطاء OCR الشائعة
        # (مثل استبدال حرف متشابه بصرياً: NGINX -> NCINX). تُطبّق فقط على
        # مهارات بطول كافٍ (MIN_LENGTH_FOR_FUZZY) وبأقصى خطأ حرف واحد
        # (MAX_EDIT_DISTANCE_FOR_FUZZY) لتقليل احتمال التطابق العرضي
        # مع كلمات عادية لا علاقة لها بالمهارة (false positives).
        if skill_clean.isalpha() and len(skill_clean) >= MIN_LENGTH_FOR_FUZZY:
            for word in text_words:
                word_clean = re.sub(r'[^a-zA-Z]', '', word)
                if not word_clean or abs(len(word_clean) - len(skill_clean)) > MAX_EDIT_DISTANCE_FOR_FUZZY:
                    continue
                if _edit_distance(word_clean, skill_clean) <= MAX_EDIT_DISTANCE_FOR_FUZZY:
                    found_skills.add(skill)
                    break

    # 4. استنتاج المهارات الأساسية الضمنية: إذا وُجدت مهارة/فريموورك مبني
    # على مهارة أساسية أخرى (مثل React.js يفترض HTML/CSS/JavaScript)،
    # نضيف الأساسية ضمناً حتى لو لم تُذكر صراحة بالنص. نمر بحلقة متكررة
    # (حتى استقرار النتيجة) لتغطية حالات السلسلة مثل Next.js -> React.js
    # -> HTML/CSS/JavaScript دون الحاجة لتكرار القائمة الكاملة بكل مفتاح.
    changed = True
    while changed:
        changed = False
        for skill in list(found_skills):
            implied = IMPLIED_SKILLS.get(skill.lower(), [])
            for implied_skill in implied:
                if implied_skill not in found_skills:
                    found_skills.add(implied_skill)
                    changed = True

    return sorted(list(found_skills))

# ==========================================
# 3. دالة مطابقة المهارات وحساب المسار الوظيفي
# ==========================================
def analyze_career_paths(extracted_list, experience_level="junior"):
    """
    تقارن مهارات المستخدم المستخرجة مع كل المسارات الوظيفية وتحسب النسبة المئوية للتوافق.
    تعتمد على متطلبات المستوى المحدد (junior/senior) من قاعدة البيانات لكل مسار.
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

    # فحص وحساب توافق المهارات لكل مسار متوفر في الـ JSON، بناءً على
    # متطلبات المستوى المحدد (junior/senior). إذا لم يوجد المستوى المطلوب
    # لأي سبب، نرجع افتراضياً لـ junior كقيمة أكثر أماناً.
    for career_title, career_data in SKILLS_DB.items():
        level_data = career_data.get(experience_level, career_data.get("junior", {}))
        required = level_data.get("required_skills", [])
        nice_to_have = level_data.get("nice_to_have", [])

        matched_required = [s for s in required if is_skill_covered(s, extracted_clean)]
        matched_nice = [s for s in nice_to_have if is_skill_covered(s, extracted_clean)]

        missing_required_list = [s for s in required if not is_skill_covered(s, extracted_clean)]
        missing_nice_list = [s for s in nice_to_have if not is_skill_covered(s, extracted_clean)]

        # -----------------------------------------------------------
        # حساب match_score: يعتمد فقط على المهارات الأساسية (required).
        # امتلاك كل required → 100% تلقائياً. مهارات nice_to_have لا
        # تؤثر على السكور بأي شكل، وتبقى للعرض فقط (تظهر بقسم "matched"
        # إن وُجدت، أو بقسم "missing" تحت تصنيف "يفضل تعلمها") دون أن
        # تخفّض نتيجة الشخص لعدم امتلاكه أدوات إضافية خارج الأساسيات.
        #
        # نطبّق جذراً تربيعياً على النسبة الخام (بدل نسبة خطية مباشرة)
        # لتخفيف العقاب القاسي عند النقص الجزئي: مثلاً امتلاك نصف
        # الأساسيات يعطي نتيجة أعلى من 50% (وليس نتيجة قاسية كنسبة
        # خطية مباشرة)، بينما صفر يبقى صفر وامتلاك الكل يبقى 100%.
        # -----------------------------------------------------------
        required_ratio = (len(matched_required) / len(required)) if required else 1.0

        match_score = int(round(math.sqrt(required_ratio) * 100))
        match_score = max(0, min(100, match_score))

        # -----------------------------------------------------------
        # عرض أهم 5 مهارات ناقصة فقط (بالأولوية): الأساسية الناقصة أولاً،
        # ثم الإضافية الناقصة، بدل عرض كل القائمة (قد تتجاوز 15-20 عنصر)
        # -----------------------------------------------------------
        TOP_MISSING_LIMIT = 5
        prioritized_missing = (
            [{"skill": s, "importance": "required"} for s in missing_required_list] +
            [{"skill": s, "importance": "nice_to_have"} for s in missing_nice_list]
        )[:TOP_MISSING_LIMIT]

        career_paths_raw[career_title] = {
            "title": career_title,
            "match_score": match_score,
            "matched_skills": matched_required + matched_nice,
            "missing_skills": prioritized_missing
        }

    # ترتيب المسارات من الأعلى توافقاً إلى الأقل
    sorted_titles = sorted(career_paths_raw.keys(), key=lambda k: career_paths_raw[k]["match_score"], reverse=True)

    return {
        "career_paths": [career_paths_raw[t] for t in sorted_titles],
        "top_recommendation": sorted_titles[0] if sorted_titles else "Software Engineer"
    }

# ==========================================
# 4. دالة كشف تخطيط الأعمدة المتعددة (PDF)
# ==========================================
def detect_multi_column_layout(pdf_path, ocr_data=None):
    """
    يفحص توزيع الكلمات أفقياً على الصفحة لاكتشاف تخطيط أعمدة متعددة.
    1) يجرب pdfplumber أولاً (سريع، يعمل مع PDF النصي العادي).
    2) إذا رجع pdfplumber صفر كلمات (PDF صورة/ممسوح)، يستخدم ocr_data
       الجاهز (الممرر أصلاً من pdf_parser.py) بدون إعادة تشغيل OCR من جديد.

    المنطق: نقسم عرض الصفحة لخلايا أفقية صغيرة (buckets)، ونكتشف وجود
    فجوة فراغ متواصلة بين منطقتين فيهما كلمات كافية (مثل sidebar
    ضيق + محتوى رئيسي عريض)، بدل الاعتماد على نسبة عدد الكلمات
    التي تفشل عند تخطيطات الأعمدة غير المتساوية (sidebar صغير).
    """
    x_positions = []
    page_width = None

    # المحاولة 1: pdfplumber (للـ PDF النصي العادي)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                if words:
                    page_width = page.width
                    x_positions = [w['x0'] for w in words]
                    break
    except Exception:
        pass

    # المحاولة 2: استخدام ocr_data الجاهز فقط لو pdfplumber ما أعطى نتيجة
    # (هذا يحصل عندما يكون الملف صورة ممسوحة وتم استخراج نصه عبر easyocr)
    if not x_positions and ocr_data:
        # كل عنصر بـ ocr_data بشكل [bbox, text] حيث bbox = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        try:
            raw_x = [item[0][0][0] for item in ocr_data if item and len(item) > 0 and item[0]]
            if raw_x:
                x_positions = raw_x
                page_width = max(item[0][2][0] for item in ocr_data if item and len(item) > 0 and item[0])
        except (IndexError, TypeError):
            pass

    if not x_positions or len(x_positions) < 15 or not page_width:
        return False

    # تقسيم عرض الصفحة لـ 20 خلية، وعدّ الكلمات التي تبدأ بكل خلية
    num_buckets = 20
    bucket_width = page_width / num_buckets
    bucket_counts = [0] * num_buckets

    for x in x_positions:
        idx = min(int(x / bucket_width), num_buckets - 1)
        bucket_counts[idx] += 1

    # نبحث عن فجوة فراغ متواصلة بين منطقتين فيهما كلمات.
    # نتجاهل أول وآخر خليتين (هوامش الصفحة الطبيعية).
    gap_start = None
    for idx in range(2, num_buckets - 2):
        if bucket_counts[idx] == 0:
            if gap_start is None:
                gap_start = idx
        else:
            if gap_start is not None:
                gap_width = idx - gap_start  # عدد الخلايا الفاضية المتتالية
                left_density = sum(bucket_counts[:gap_start])
                right_density = sum(bucket_counts[idx:])
                smaller_side = min(left_density, right_density)
                larger_side = max(left_density, right_density)

                # الحالة 1: عمودان متقاربان نسبياً (كل جهة 10%+ من الإجمالي)
                balanced_case = smaller_side >= max(5, len(x_positions) * 0.1)

                # الحالة 2: عمود رفيع جداً (مثل sidebar فيه عناوين أقسام فقط)
                # نقبله إذا كان فيه 5+ كلمات مستقلة وفجوة عريضة بوضوح (2+ خلايا فاضية)
                # لتمييزه عن كلمة شاردة بزاوية الصفحة (false positive)
                narrow_sidebar_case = smaller_side >= 5 and gap_width >= 2

                if larger_side > 0 and (balanced_case or narrow_sidebar_case):
                    return True
                gap_start = None

    return False

# ==========================================
# 5. فحص التوافق الفعلي والحقيقي مع أنظمة ATS
# ==========================================
def analyze_cv_ats(pdf_path: str, extracted_text: str, expected_skills: list, ocr_data=None) -> dict:
    """
    تقوم بفحص حقيقي لبنية الملف وهيكليته ومصطلحاته لتقييم توافقه مع الـ ATS
    """
    issues = []
    passed = []
    score = 100

    # -----------------------------------------
    # 1. فحص وجود جداول حقيقية (PDF + DOCX)
    # -----------------------------------------
    has_tables = False

    if pdf_path.endswith('.pdf'):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    if page.extract_tables():
                        has_tables = True
                        break
        except Exception:
            pass

    elif pdf_path.endswith('.docx'):
        try:
            doc = Document(pdf_path)
            has_tables = len(doc.tables) > 0
        except Exception:
            pass

    if has_tables:
        issues.append("تم اكتشاف جداول داخل الملف. بعض أنظمة ATS تفشل في معالجتها، يفضل استخدام نصوص مباشرة متتالية.")
        score -= 30
    else:
        passed.append("بنية السيرة الذاتية ممتازة وخالية من الجداول المعقدة.")

    # -----------------------------------------
    # 2. فحص تخطيط الأعمدة المتعددة (PDF فقط)
    # -----------------------------------------
    multi_column = False
    if pdf_path.endswith('.pdf'):
        multi_column = detect_multi_column_layout(pdf_path, ocr_data=ocr_data)
        if multi_column:
            issues.append("تم اكتشاف تخطيط بصري متعدد الأعمدة. ترتيب قراءة النص قد يختلط عند بعض أنظمة ATS ويُفقد سياقه، يفضل استخدام عمود واحد متتالي.")
            score -= 20
        else:
            passed.append("تخطيط الصفحة بعمود واحد متتالي، سهل القراءة لأنظمة ATS.")

    # -----------------------------------------
    # 3. فحص العناوين الرئيسية القياسية
    # -----------------------------------------
    standard_headings = ["experience", "education", "skills", "summary", "profile", "projects", "work"]
    text_lower = extracted_text.lower()
    found_headings = [h for h in standard_headings if re.search(r'\b' + h + r'\b', text_lower)]

    if len(found_headings) >= 2:
        passed.append(f"تم استخدام عناوين أقسام قياسية واضحة لسهولة الفهرسة الآلية مثل ({', '.join(found_headings[:2])}).")
    else:
        issues.append("العناوين الرئيسية للأقسام غير واضحة أو تستخدم مصطلحات إبداعية. التزم بالعناوين القياسية مثل Experience و Skills.")
        score -= 30

    # -----------------------------------------
    # 4. فحص الكلمات المفتاحية الدقيقة
    # -----------------------------------------
    matched_keywords = [skill for skill in expected_skills if skill.lower() in text_lower]
    match_ratio = len(matched_keywords) / len(expected_skills) if expected_skills else 0

    if match_ratio >= 0.4:
        passed.append("تم تضمين المصطلحات التقنية الأساسية والكلمات المفتاحية المطلوبة بدقة.")
    else:
        issues.append("السيرة الذاتية تفتقر للكلمات المفتاحية والمصطلحات الدقيقة الخاصة بهذا المسار الوظيفي.")
        score -= 40

    score = max(0, min(100, score))
    is_compliant = score >= 60

    return {
        "is_compliant": is_compliant,
        "score": score,
        "issues": issues,
        "passed": passed
    }