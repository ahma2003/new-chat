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

# --- ✨ 1. إضافة ذاكرة لتتبع المحادثات ✨ ---
CONVERSATION_STARTED = set()

# ---
openai_client = None
chroma_collection = None
model = None
RAG_ENABLED = False

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI client ready")
else:
    print("❌ OpenAI API Key not found in environment variables.")

try:
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

# --- ✨ 2. تحسين دالة البحث لجلب المزيد من النتائج ✨ ---
def retrieve_from_chroma(user_query, top_k=3): # تم تغييرها إلى 3
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

# --- ✨ 3. اللوجيك الرئيسي الجديد مع إدارة حالة المحادثة ✨ ---
def get_chatgpt_response(message, from_number):
    # تحديد ما إذا كانت هذه هي الرسالة الأولى
    is_first_message = from_number not in CONVERSATION_STARTED
    if is_first_message:
        CONVERSATION_STARTED.add(from_number)

    context_str = "لا توجد معلومات إضافية."
    if RAG_ENABLED:
        retrieved_context = retrieve_from_chroma(message)
        if retrieved_context:
            # تنسيق السياق ليكون واضحًا لـ GPT
            context_items = []
            for i, item in enumerate(retrieved_context):
                context_items.append(f"--- معلومة ذات صلة رقم {i+1} ---\nالسؤال: {item['question']}\nالإجابة: {item['answer']}")
            context_str = "\n\n".join(context_items)

    # اختيار البرومت المناسب بناءً على حالة المحادثة
    if is_first_message:
        system_prompt = f"""
        أنت مساعد خدمة عملاء لمكتب "الركائز البشرية للاستقدام". مهمتك هي الرد على استفسار العميل الأول.
        
        **قواعد الرد:**
        1.  **الترحيب:** ابدأ بترحيب حار وودود باللهجة السعودية.
        2.  **التعريف:** بعد الترحيب مباشرة، عرف بالمكتب بشكل مختصر، قل: "مكتب الركائز البشرية بخدمتك في أي استفسار عن الاستقدام." وأضف إيموجي مناسب.
        3.  **الإجابة على السؤال:** استخدم "المعلومات ذات الصلة" التالية للإجابة على سؤال العميل الأول بدقة ووضوح. اختر المعلومة الأكثر تطابقًا مع سؤال العميل.
        
        **معلومات ذات صلة من قاعدة المعرفة:**
        {context_str}
        
        **ملاحظات هامة:**
        - حافظ على أسلوب مهذب ومحترف.
        - لا تقترح أي مساعدة إضافية في هذا الرد الأول.
        """
    else: # هذا البرومت للرسائل التالية
        system_prompt = f"""
        أنت مساعد خدمة عملاء لمكتب "الركائز البشرية للاستقدام". العميل في منتصف محادثة معك.
        
        **قواعد الرد:**
        1.  **مباشرة:** اذهب مباشرة إلى إجابة سؤال العميل بدون أي ترحيب أو مقدمات.
        2.  **الدقة:** استخدم "المعلومات ذات الصلة" التالية كأساس أساسي لإجابتك. اختر المعلومة الأكثر فائدة ودقة من بين الخيارات المتاحة.
        3.  **إذا لم تجد إجابة:** إذا كانت المعلومات غير كافية، رد بلطف: "استفسارك يتطلب مساعدة من أحد موظفينا. سيتم التواصل معك قريبًا إن شاء الله."
        4.  **الخاتمة:** في نهاية ردك، اسأل دائمًا بلطف إذا كان بإمكانك المساعدة في شيء آخر، مثل: "تحب أساعدك في شي ثاني؟ 🙂"
        
        **معلومات ذات صلة من قاعدة المعرفة:**
        {context_str}
        """

    if not openai_client:
        return "عذرًا، خدمة OpenAI غير متاحة حاليًا."
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "عذراً، أواجه مشكلة فنية في الوقت الحالي."

# --- Webhook and Sending Functions (مع تعديل بسيط) ---
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
                                # ✨ 4. تمرير رقم المستخدم للدالة الرئيسية ✨
                                bot_response = get_chatgpt_response(user_message, from_number)
                                send_whatsapp_message(from_number, bot_response)
        return 'OK', 200
    return 'Unsupported method', 405

@app.route('/')
def index():
    # ... (يمكن ترك هذه الدالة كما هي)
    status = "<h1>Recruitment Office WhatsApp RAG Bot</h1>"
    # ...
    return status