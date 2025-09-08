# app.py
import os
import json
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
import chromadb
from sentence_transformers import SentenceTransformer

# --- Configuration ---
# Heroku will provide these as environment variables
ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Initialize Flask app
app = Flask(__name__)

# Initialize OpenAI Client
client = OpenAI(api_key=OPENAI_API_KEY)

# --- إعدادات RAG (الاتصال بـ ChromaDB) ---
MODEL_NAME = 'intfloat/multilingual-e5-large'
PERSIST_DIRECTORY = "my_chroma_db"
COLLECTION_NAME = "recruitment_qa"
chroma_collection = None # Initialize as None

# Wrap initialization in a try-except block to handle potential startup errors
try:
    # 1. تحميل نموذج تحويل الجمل
    print(f"جاري تحميل النموذج: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    print("تم تحميل النموذج بنجاح.")

    # 2. الاتصال بقاعدة بيانات ChromaDB (التي تم رفعها مع المشروع)
    print("جاري الاتصال بقاعدة بيانات ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    chroma_collection = chroma_client.get_collection(name=COLLECTION_NAME)
    print(f"تم الاتصال بنجاح بـ ChromaDB. المجموعة تحتوي على {chroma_collection.count()} مستند.")

except Exception as e:
    print(f"!!! خطأ فادح أثناء الإعداد الأولي: {e}")
    print("!!! تأكد من وجود مجلد 'my_chroma_db' وأنه يحتوي على قاعدة بيانات صحيحة.")


# --- RAG: Retrieval Function ---
def retrieve_from_chroma(user_query, top_k=2):
    if not chroma_collection:
        print("خطأ: لم يتم تهيئة مجموعة ChromaDB.")
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
    retrieved_context = retrieve_from_chroma(message)
    
    context_str = "لا توجد معلومات إضافية."
    if retrieved_context:
        context_str = "\n\n".join([f"السؤال ذو الصلة: {item['question']}\nالإجابة المسجلة: {item['answer']}" for item in retrieved_context])

    system_prompt = f"""
    أنت مساعد ذكي وودود لمكتب الاستقدام "مكتب الركائز البشرية" في عنيزة – القصيم، السعودية.  
    ⏰ مواعيد العمل من 9 صباحًا إلى 5 مساءً.  

    طريقة الرد:
    1.  ابدأ بترحيب ودود باللهجة السعودية في اول رساله فقط، بعدها تعطي تعريف مختصر بالمكتب مثل: "مكتب الركائز البشرية بخدمتك في أي استفسار عن الاستقدام." وحط إيموجي واحد خفيف.  
    2. لا تعيد الترحيب أو تعريف المكتب في أي رد بعد كذا. انتقل مباشرة لجواب سؤال العميل.  
    3. استخدم المعلومات التالية من قاعدة المعرفة كمصدر أساسي للإجابة:  
    ---
    {context_str}
    ---
    4. إذا كانت المعلومات أعلاه تجيب على سؤال العميل، قدم له إجابة واضحة، مختصرة، وبأسلوب مهذب وودود.  
    5. إذا ما كانت المعلومات كافية، ابحث في الإنترنت أولاً، وإذا برضو ما حصلت جواب مناسب، رد بلطف:  
    "استفسارك يتطلب مساعدة من أحد موظفينا. بنكون على تواصل معك قريب إن شاء الله لمساعدتك بشكل أفضل."  
    6. خلي أسلوبك دايمًا ودود، مبسط، وكأنك تكلم العميل وجهًا لوجه.  
    7. في نهاية كل رد (ما عدا أول رد)، اقترح مساعدة إضافية بشكل خفيف مثل: "تحب أساعدك في شي ثاني؟ 🙂"
    """

    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "عذراً، أواجه مشكلة فنية في الوقت الحالي. يرجى المحاولة مرة أخرى لاحقاً."

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
                            if message_data.get('type') == 'text' and chroma_collection is not None:
                                from_number = message_data['from']
                                user_message = message_data['text']['body']
                                print(f"Received message: '{user_message}' from {from_number}")
                                bot_response = get_chatgpt_response(user_message)
                                print(f"Sending response: '{bot_response}' to {from_number}")
                                send_whatsapp_message(from_number, bot_response)
        return 'OK', 200
    
    return 'Unsupported method', 405

@app.route('/')
def index():
    return "<h1>Recruitment Office WhatsApp RAG Bot with ChromaDB is running!</h1>"
