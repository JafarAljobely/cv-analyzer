import easyocr
import numpy as np
import pdfplumber
from pdf2image import convert_from_path


reader = easyocr.Reader(['ar', 'en'], gpu=True)

def extract_text_from_pdf(file_path: str):

    try:
        all_text = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()

                if text and text.strip():
                    all_text.append([None, text])

        full_text = " ".join(
            item[1] for item in all_text if len(item) > 1
        )

        if len(full_text.strip()) > 100:
            print("✅ Text PDF detected")
            return all_text

    except Exception as e:
        print(f"pdfplumber failed: {e}")


      # المحاولة الثانية: OCR
    print("📄 Scanned PDF detected -> OCR")


    images = convert_from_path(file_path, dpi=300)

    all_page_data = []
    
    for img in images:
        page_result = reader.readtext(np.array(img), detail=1, paragraph=True)
        all_page_data.extend(page_result)
        
    return all_page_data # سنعيد القائمة كاملة لملف الـ extractor