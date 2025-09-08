# enhanced_setup_chromadb.py
import json
import chromadb
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict

# --- الإعدادات المحسنة ---
MODEL_NAME = 'intfloat/multilingual-e5-large'
JSON_FILE_PATH = 'data.json'
PERSIST_DIRECTORY = "my_chroma_db"  
COLLECTION_NAME = "recruitment_qa" 

def load_knowledge_base(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"تم تحميل {len(data)} سؤال وجواب من '{file_path}'.")
        return data
    except FileNotFoundError:
        print(f"خطأ: لم يتم العثور على ملف قاعدة المعرفة '{file_path}'.")
        return []

def preprocess_text(text: str) -> str:
    """تحسين النصوص قبل التحويل إلى embeddings"""
    import re
    # إزالة الأرقام المتتالية والرموز الزائدة
    text = re.sub(r'\d+', ' رقم ', text)
    # توحيد المسافات
    text = re.sub(r'\s+', ' ', text)
    # إزالة علامات الترقيم الزائدة
    text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text)
    return text.strip()

def create_enhanced_embeddings(questions: List[str], answers: List[str], model) -> tuple:
    """إنشاء embeddings محسنة للأسئلة والإجابات معاً"""
    enhanced_texts = []
    
    for q, a in zip(questions, answers):
        # تحسين النصوص
        clean_q = preprocess_text(q)
        clean_a = preprocess_text(a)
        
        # دمج السؤال والإجابة لفهم أفضل للسياق
        combined_text = f"سؤال: {clean_q} إجابة: {clean_a}"
        enhanced_texts.append(f"query: {combined_text}")
    
    print("جاري إنشاء embeddings محسنة...")
    embeddings = model.encode(
        enhanced_texts, 
        normalize_embeddings=True, 
        show_progress_bar=True,
        batch_size=32  # تحسين الأداء
    )
    
    return embeddings, enhanced_texts

# --- تحميل النموذج ---
print(f"جاري تحميل النموذج المحسن: {MODEL_NAME}...")
model = SentenceTransformer(MODEL_NAME)
print("تم تحميل النموذج بنجاح.")

# --- إعداد ChromaDB ---
client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)

print(f"جاري إعداد المجموعة المحسنة '{COLLECTION_NAME}' في ChromaDB...")
try:
    client.delete_collection(name=COLLECTION_NAME)
    print("تم حذف المجموعة القديمة بنجاح.")
except Exception as e:
    print(f"لم يتم العثور على مجموعة قديمة: {e}")

# إنشاء مجموعة بمعايير تشابه محسنة
collection = client.create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}  # استخدام cosine similarity للغة العربية
)
print("تم إنشاء المجموعة المحسنة بنجاح.")

# --- قراءة ومعالجة البيانات ---
knowledge_base = load_knowledge_base(JSON_FILE_PATH)
if not knowledge_base:
    print("لا توجد بيانات للمعالجة. تم إنهاء العملية.")
else:
    questions = [item['question'] for item in knowledge_base]
    answers = [item['answer'] for item in knowledge_base]
    ids = [str(i) for i in range(len(questions))]

    # إنشاء embeddings محسنة
    embeddings, enhanced_texts = create_enhanced_embeddings(questions, answers, model)
    
    print(f"تم إنشاء {len(embeddings)} متجه محسن. جاري إضافتها إلى ChromaDB...")
    
    # إضافة metadata محسنة
    metadatas = []
    for i, (q, a) in enumerate(zip(questions, answers)):
        metadata = {
            "question": q,
            "answer": a,
            "question_clean": preprocess_text(q),
            "answer_clean": preprocess_text(a),
            "combined_text": enhanced_texts[i],
            "id": str(i)
        }
        metadatas.append(metadata)
    
    collection.add(
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
        ids=ids
    )

    print("=" * 60)
    print(f"✅ نجاح! تم تخزين {collection.count()} مستند محسن في ChromaDB")
    print(f"📁 قاعدة البيانات محفوظة في: '{PERSIST_DIRECTORY}'")
    print("🔍 النظام جاهز للبحث الذكي والدقيق")
    print("=" * 60)