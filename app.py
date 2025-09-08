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

# --- ✨ 1. الذاكرة الجديدة لتتبع المحادثات بشكل منفصل ✨ ---
# نستخدم قاموس (dictionary) لتخزين حالة كل محادثة.
# المفتاح هو رقم الهاتف، والقيمة هي ببساطة True.
CONVERSATIONS = {}

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
    MODEL_NAME = 'intfloat/multilingual-e5-large'
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

# ---
def retrieve_from_chroma(user_query, top_k=3):
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

# --- ✨ 2. اللوجيك الرئيسي الجديد والمحسن بالكامل ✨ ---
def get_chatgpt_response(message, from_number):
    # تحديد ما إذا كانت هذه هي الرسالة الأولى لهذا المستخدم تحديدًا
    is_first_message = from_number not in CONVERSATIONS
    if is_first_message:
        CONVERSATIONS[from_number] = True # تسجيل أن هذا المستخدم بدأ محادثة

    context_str = "لا توجد معلومات ذات صلة في قاعدة المعرفة." # رسالة واضحة في حال عدم وجود نتائج
    if RAG_ENABLED:
        retrieved_context = retrieve_from_chroma(message)
        if retrieved_context:
            context_items = []
            for i, item in enumerate(retrieved_context):
                context_items.append(f"--- [معلومة محتملة رقم {i+1}] ---\nالسؤال: {item['question']}\nالإجابة: {item['answer']}")
            context_str = "\n".join(context_items)

    # اختيار البرومت المناسب بناءً على حالة المحادثة
    if is_first_message:
        system_prompt = f"""
        أنت مساعد خدمة عملاء خبير لمكتب "الركائز البشرية للاستقدام". مهمتك هي الرد على استفسار العميل الأول.

        **قواعد الرد الصارمة:**
        1.  **الترحيب:** ابدأ بترحيب حار وودود باللهجة السعودية.
        2.  **التعريف:** بعد الترحيب، عرف بالمكتب: "مكتب الركائز البشرية بخدمتك في أي استفسار عن الاستقدام."
        3.  **تحليل المعلومات:** انظر إلى "المعلومات المحتملة" أدناه. هل أي منها يجيب **بشكل مباشر ودقيق** على سؤال العميل؟
        4.  **الإجابة:**
            - **إذا وجدت إجابة مباشرة:** أجب على سؤال العميل باستخدام تلك المعلومة **فقط**. لا تخترع أو تخلط المعلومات.
            - **إذا لم تجد إجابة مباشرة:** رد بلطف: "حياك الله، استفسارك يتطلب مساعدة من أحد موظفينا. سيتم التواصل معك قريبًا إن شاء الله."
        
        **سؤال العميل:** "{message}"
        
        **معلومات محتملة من قاعدة المعرفة:**
        {context_str}
        """
    else: # البرومت للرسائل التالية
        system_prompt = f"""
        أنت مساعد خدمة عملاء خبير لمكتب "الركائز البشرية للاستقدام". العميل في منتصف محادثة.

        **قواعد الرد الصارمة:**
        1.  **مباشرة:** اذهب مباشرة لإجابة سؤال العميل بدون مقدمات.
        2.  **تحليل المعلومات:** انظر إلى "المعلومات المحتملة" أدناه. هل أي منها يجيب **بشكل مباشر ودقيق** على سؤال العميل؟
        3.  **الإجابة:**
            - **إذا وجدت إجابة مباشرة:** أجب على سؤال العميل باستخدام تلك المعلومة **فقط**. لا تخترع معلومات.
            - **إذا لم تجد إجابة مباشرة:** رد بلطف: "عفوًا، استفسارك يتطلب مساعدة من أحد موظفينا. سيتم التواصل معك قريبًا."
        4.  **الخاتمة:** اختم ردك دائمًا بسؤال: "هل أقدر أساعدك في شي ثاني؟"

        **سؤال العميل:** "{message}"

        **معلومات محتملة من قاعدة المعرفة:**
        {context_str}
        """

    if not openai_client:
        return "عذرًا، خدمة OpenAI غير متاحة حاليًا."
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4.1", # ✨ استخدام النموذج الأفضل والأحدث
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
                                bot_response = get_chatgpt_response(user_message, from_number)
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