# app.py
import os
import json
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
import chromadb
from sentence_transformers import SentenceTransformer

# --- Configuration ---
ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Initialize Flask app
app = Flask(__name__)

# --- ✨✨✨ الجزء الذي تم تصحيحه ✨✨✨ ---
openai_client = None
chroma_collection = None
model = None
RAG_ENABLED = False

# Check for API key before initializing anything
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI client ready")
else:
    print("❌ OpenAI API Key not found in environment variables.")

try:
    # --- إعدادات RAG (الاتصال بـ ChromaDB) ---
    # ✨✨✨ استخدمنا الموديل الصحيح والصغير ✨✨✨
    MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    PERSIST_DIRECTORY = "my_chroma_db"
    COLLECTION_NAME = "recruitment_qa"

    print(f"جاري تحميل النموذج: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    print("✅ Sentence transformer model available")

    print("جاري الاتصال بقاعدة بيانات ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    chroma_collection = chroma_client.get_collection(name=COLLECTION_NAME)
    print(f"✅ ChromaDB available. المجموعة تحتوي على {chroma_collection.count()} مستند.")
    RAG_ENABLED = True
except Exception as e:
    print(f"❌ فشل تحميل مكونات RAG (ChromaDB/Model): {e}")
    print("!!! سيعمل البوت في الوضع الأساسي بدون قاعدة المعرفة.")

# --- RAG: Retrieval Function ---
def retrieve_from_chroma(user_query, top_k=2):
    if not RAG_ENABLED:
        return []
    try:
        prefixed_user_query = f"query: {user_query}"
        query_embedding = model.encode([prefixed_user_query], normalize_embeddings=True)
        results = chroma_collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=top_k
        )
        return results['metadatas'][0] if results.get('metadatas') else []
    except Exception as e:
        print(f"حدث خطأ أثناء البحث في ChromaDB: {e}")
        return []

# --- Main Logic ---
def get_chatgpt_response(message):
    context_str = "لا توجد معلومات إضافية."
    if RAG_ENABLED:
        retrieved_context = retrieve_from_chroma(message)
        if retrieved_context:
            context_str = "\n\n".join([f"السؤال ذو الصلة: {item['question']}\nالإجابة المسجلة: {item['answer']}" for item in retrieved_context])

    system_prompt = f"""
    أنت مساعد ذكي وودود لمكتب الاستقدام "مكتب الركائز البشرية".
    استخدم المعلومات التالية من قاعدة المعرفة كمصدر أساسي للإجابة:
    ---
    {context_str}
    ---
    إذا كانت المعلومات أعلاه تجيب على سؤال العميل، قدم له إجابة واضحة ومختصرة.
    إذا لم تكن المعلومات كافية، رد بلطف: "استفسارك يتطلب مساعدة من أحد موظفينا. سيتم التواصل معك قريبًا."
    حافظ على أسلوب ودود ومبسط باللهجة السعودية.
    """
    if not openai_client:
        return "عذرًا، خدمة OpenAI غير متاحة حاليًا."
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "عذراً، أواجه مشكلة فنية في الوقت الحالي."

# --- Webhook and Sending Functions ---
def send_whatsapp_message(to_number, message):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": message}}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        print(f"Message sent successfully to {to_number}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        else:
            return 'Verification token mismatch', 403
    if request.method == 'POST':
        data = request.get_json()
        if data and 'entry' in data:
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if 'messages' in value:
                        for message_data in value['messages']:
                            if message_data.get('type') == 'text':
                                from_number = message_data['from']
                                user_message = message_data['text']['body']
                                bot_response = get_chatgpt_response(user_message)
                                send_whatsapp_message(from_number, bot_response)
        return 'OK', 200
    return 'Unsupported method', 405

@app.route('/')
def index():
    status = "<h1>Recruitment Office WhatsApp RAG Bot</h1>"
    status += "<h2>Status:</h2><ul>"
    status += f"<li>{'✅ OpenAI client ready' if openai_client else '❌ OpenAI client not available'}</li>"
    status += f"<li>{'✅ ChromaDB available' if RAG_ENABLED else '❌ ChromaDB not available'}</li>"
    status += f"<li>{'✅ Sentence transformer model available' if model else '❌ Sentence transformer model not available'}</li>"
    status += "</ul>"
    if not RAG_ENABLED:
        status += "<p>Bot is running in basic mode!</p>"
    return status