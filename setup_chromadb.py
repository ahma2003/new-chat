# setup_chromadb.py
import json
import chromadb
from sentence_transformers import SentenceTransformer

# --- الإعدادات ---
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

# --- تحميل النموذج ---
print(f"جاري تحميل النموذج: {MODEL_NAME}...")
model = SentenceTransformer(MODEL_NAME)
print("تم تحميل النموذج بنجاح.")

# --- إعداد ChromaDB ---
client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)

# --- إنشاء أو إعادة إنشاء المجموعة (Collection) ---
print(f"جاري إعداد المجموعة '{COLLECTION_NAME}' في ChromaDB...")
# نحذف المجموعة إذا كانت موجودة لضمان عدم تكرار البيانات عند إعادة التشغيل
try:
    client.delete_collection(name=COLLECTION_NAME)
    print("تم حذف المجموعة القديمة بنجاح.")
# --- هذا هو السطر الذي تم تعديله ---
except Exception as e:
    # هذا الكود سيتجاهل الخطأ إذا لم تكن المجموعة موجودة، وهو المطلوب
    print(f"لم يتم العثور على مجموعة قديمة (وهذا طبيعي في أول تشغيل). رسالة الخطأ: {e}")

collection = client.create_collection(name=COLLECTION_NAME)
print("تم إنشاء المجموعة بنجاح.")

# --- قراءة البيانات وتجهيزها ---
knowledge_base = load_knowledge_base(JSON_FILE_PATH)
if not knowledge_base:
    print("لا توجد بيانات للمعالجة. تم إنهاء العملية.")
else:
    questions = [item['question'] for item in knowledge_base]
    answers = [item['answer'] for item in knowledge_base]
    ids = [str(i) for i in range(len(questions))]

    print("جاري تحويل الأسئلة إلى متجهات (Embeddings)...")
    prefixed_questions = [f"query: {q}" for q in questions]
    embeddings = model.encode(prefixed_questions, normalize_embeddings=True, show_progress_bar=True)
    
    print(f"تم إنشاء {len(embeddings)} متجه. جاري إضافتها إلى ChromaDB...")
    metadatas = [{"question": q, "answer": a} for q, a in zip(questions, answers)]
    
    collection.add(
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
        ids=ids
    )

    print("=" * 50)
    print(f"نجاح! تم تخزين {collection.count()} مستند في قاعدة بيانات ChromaDB.")
    print(f"قاعدة البيانات محفوظة في مجلد: '{PERSIST_DIRECTORY}'")
    print("=" * 50)