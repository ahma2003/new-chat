# enhanced_app_optimized_v3.py
import os
import json
import requests
import threading
import time
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from openai import OpenAI
import chromadb
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Optional
import hashlib

# --- Configuration ---
ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

app = Flask(__name__)

# --- 🚀 نظام ذاكرة محادثات محسّن ---
class ConversationManager:
    def __init__(self):
        self.conversations = {}
        self.message_lock = threading.Lock()
        self.cleanup_interval = 3600
        
    def is_first_message(self, phone_number: str) -> bool:
        with self.message_lock:
            return phone_number not in self.conversations
    
    def register_conversation(self, phone_number: str):
        with self.message_lock:
            self.conversations[phone_number] = {
                'first_message_time': datetime.now(),
                'last_activity': datetime.now(),
                'message_count': 1
            }
    
    def update_activity(self, phone_number: str):
        with self.message_lock:
            if phone_number in self.conversations:
                self.conversations[phone_number]['last_activity'] = datetime.now()
                self.conversations[phone_number]['message_count'] += 1
    
    def cleanup_old_conversations(self):
        """تنظيف المحادثات القديمة (أكثر من 24 ساعة)"""
        cutoff_time = datetime.now() - timedelta(hours=24)
        with self.message_lock:
            expired = [phone for phone, data in self.conversations.items() 
                      if data['last_activity'] < cutoff_time]
            for phone in expired:
                del self.conversations[phone]
            if expired:
                print(f"🧹 تم تنظيف {len(expired)} محادثة قديمة")

# --- ⚡ نظام الردود السريعة المطور ---
class QuickResponseSystem:
    def __init__(self):
        # --- أرقام التواصل الثابتة ---
        self.SUPPORT_NUMBERS = "📞 537422332\n📞 556914447"
        self.CUSTOMER_SERVICE_NUMBERS = "📞 0556914447\n📞 0506207444\n📞 0537914445\n📞 0573694447\n📞 0559720444\n📞 0556535444\n📞 0554834447"

        # ردود الترحيب السريعة
        self.welcome_patterns = {
            'سلام', 'السلام', 'عليكم', 'مرحبا', 'مرحبتين', 'هلا', 'اهلا', 'كيفك', 'كيف الحال',
            'شلونك', 'وش اخبارك', 'صباح', 'مساء', 'اهلين', 'حياك', 'حياكم', 'يعطيك العافية',
            'تسلم', 'الله يعطيك العافية', 'هاي', 'هالو', 'hello', 'hi', 'good morning',
            'good evening', 'ايش اخبارك', 'وش مسوي', 'كيف اموركم'
        }
        
        # كلمات دلالية للأسعار - محسّنة
        self.price_keywords = [
            'سعر', 'اسعار', 'أسعار', 'تكلفة', 'كلفة', 'تكاليف', 'كم', 'فلوس', 'ريال', 'مبلغ',
            'رسوم', 'أجور', 'اجور', 'عرض', 'عروض', 'باقة', 'باقات', 'خصم', 'خصومات', 'ثمن',
            'مصاريف', 'مصروف', 'دفع', 'يكلف', 'تكلف', 'بكام'
        ]
        
        # جمل كاملة للأسعار
        self.price_phrases = [
            'كم السعر', 'ايش السعر', 'وش السعر', 'كم التكلفة', 'كم الثمن', 'كم يكلف',
            'ابغى اعرف السعر', 'عايز اعرف السعر', 'ايه الاسعار', 'وش الاسعار',
            'رسوم الاستقدام', 'اسعار الاستقدام', 'تكلفة الاستقدام'
        ]

        # كلمات دلالية لمشاكل التواصل
        self.contact_keywords = [
            'اتصلت', 'أتصل', 'اتصال', 'ما تردون', 'محد يرد', 'مافي رد', 'مشغول',
            'اكلمكم', 'أتواصل', 'تواصل', 'مشكلة', 'الدعم', 'المساندة'
        ]
        
        self.contact_phrases = [
            'ابغى اكلمكم', 'كيف اتواصل معكم', 'ليش ما تردون', 'الرقم ما يرد'
        ]

    def is_greeting_message(self, message: str) -> bool:
        """فحص سريع للرسائل الترحيبية"""
        if not message or len(message.strip()) == 0:
            return False
            
        message_clean = message.lower().strip()
        words = message_clean.split()
        
        if len(words) <= 6:
            for word in words:
                clean_word = re.sub(r'[^\w\sأ-ي]', '', word)
                if clean_word in self.welcome_patterns:
                    return True
        return False
    
    def is_price_inquiry(self, message: str) -> bool:
        """فحص سريع ودقيق للسؤال عن الأسعار"""
        if not message or len(message.strip()) == 0:
            return False
        message_clean = message.lower().strip()
        for phrase in self.price_phrases:
            if phrase in message_clean:
                return True
        words = message_clean.split()
        for word in words:
            clean_word = re.sub(r'[^\w\sأ-ي]', '', word)
            if clean_word in self.price_keywords:
                return True
        return False

    def is_contact_inquiry(self, message: str) -> bool:
        """فحص سريع لمشاكل التواصل"""
        if not message or len(message.strip()) == 0:
            return False
        message_clean = message.lower().strip()
        for phrase in self.contact_phrases:
            if phrase in message_clean:
                return True
        words = message_clean.split()
        for word in words:
            clean_word = re.sub(r'[^\w\sأ-ي]', '', word)
            if clean_word in self.contact_keywords:
                return True
        return False

    def get_welcome_response(self) -> str:
        """رد الترحيب السريع"""
        return """أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟

نحن هنا لخدمتك ومساعدتك في جميع احتياجاتك من العمالة المنزلية المدربة والمؤهلة.

كيف يمكنني مساعدتك اليوم؟ 😊"""

    def get_price_response(self) -> tuple:
        """رد الأسعار المختصر مع الصورة"""
        text_response = """حياك الله عميلنا العزيز، إليك عروضنا الحالية للعمالة المنزلية المدربة 💼

🎉 عرض خاص ومميز 🎉

للاستفسار والحجز، يسعدنا تواصلك على الأرقام التالية:
📞 0556914447
📞 0506207444
📞 0537914445"""
        image_url = "https://i.imghippo.com/files/La2232xjc.jpg"
        return text_response, image_url
        
    def get_contact_response(self) -> str:
        """رد مخصص لمشاكل التواصل"""
        return f"""عميلنا العزيز، نعتذر عن أي صعوبة واجهتها في التواصل معنا 🙏.

📝 لحل أي مشكلة تخص عاملة منزلية موجودة لديك حاليًا، يمكنك التواصل مع قسم الدعم والمساندة:
{self.SUPPORT_NUMBERS}

🌟 للاستفسارات العامة، الحجوزات، أو في حال لم يتم الرد على الأرقام الأخرى، يمكنك التواصل مع موظفات خدمة العملاء (متاحين 24 ساعة):
{self.CUSTOMER_SERVICE_NUMBERS}

نسعد بخدمتك دائمًا!"""

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 3) -> tuple:
        """استرجاع أفضل 3 مطابقات لتقديم سياق أغنى"""
        if not self.model or not self.collection:
            return [], 0.0
        
        try:
            query_embedding = self.model.encode([f"query: {user_query}"], normalize_embeddings=True)
            results = self.collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=top_k
            )
            
            if not results.get('metadatas') or not results['metadatas'][0]:
                return [], 0.0
            
            best_score = 1 - results['distances'][0][0] if 'distances' in results else 0
            results_data = results['metadatas'][0]
            
            return results_data, best_score
            
        except Exception as e:
            print(f"❌ خطأ في البحث: {e}")
            return [], 0.0

# --- 🤖 نظام الردود الذكي السريع ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever, quick_system):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
    
    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> tuple:
        """
        إنتاج الرد - يرجع (response_text, should_send_image, image_url)
        """
        print(f"🔍 معالجة: '{user_message}' من {phone_number}")
        
        # 1. أولوية عليا للترحيب
        if self.quick_system.is_greeting_message(user_message):
            print("⚡ رد ترحيب فوري")
            return self.quick_system.get_welcome_response(), False, None
        
        # 2. أولوية عليا للأسعار
        if self.quick_system.is_price_inquiry(user_message):
            print("💰 طلب أسعار مكتشف")
            text_response, image_url = self.quick_system.get_price_response()
            return text_response, True, image_url
            
        # 3. أولوية لمشاكل التواصل
        if self.quick_system.is_contact_inquiry(user_message):
            print("📞 شكوى تواصل مكتشفة")
            return self.quick_system.get_contact_response(), False, None

        # 4. الردود الذكية المعتمدة على البحث
        print("🤔 معالجة ذكية")
        retrieved_data, _ = self.retriever.retrieve_best_matches(user_message) if self.retriever else ([], 0)
        
        if not self.openai_client:
            if retrieved_data:
                return f"بناءً على معلوماتنا:\n\n{retrieved_data[0]['answer']}\n\nهل يمكنني مساعدتك في شيء آخر؟", False, None
            else:
                return "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة.\n\nهل تريد معرفة أسعارنا الحالية؟", False, None
        
        try:
            context = self.generate_context_string(retrieved_data)
            intro = "أهلاً بك في مكتب الركائز البشرية للاستقدام! 🌟\n\n" if is_first else ""
                
            system_prompt = f"""أنت مساعد ذكي لمكتب "الركائز البشرية للاستقدام". مهمتك هي الإجابة على استفسارات العملاء بدقة وود.
- أجب بشكل مباشر ومختصر ومفيد.
- استخدم المعلومات المتوفرة في قسم "المعلومات" فقط. لا تخترع أي معلومة.
- إذا لم تكن المعلومات كافية للإجابة، قل: "عميلنا العزيز، للمزيد من التفاصيل الدقيقة حول هذا الموضوع، يرجى التواصل مع خدمة العملاء".
- ابدأ بردك بعبارة ترحيبية مثل "حياك الله عميلنا العزيز" أو "أهلاً بك".
- اختتم إجابتك بسؤال لطيف مثل "هل أقدر أساعدك بشيء ثاني؟" أو "هل لديك أي استفسار آخر؟".

المعلومات:
{context}
"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=250,
                temperature=0.1
            )
            
            final_response = intro + response.choices[0].message.content.strip()
            return final_response, False, None
            
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            if retrieved_data:
                return f"عميلنا العزيز، بناءً على خبرتنا:\n\n{retrieved_data[0]['answer']}\n\nللمزيد من المساعدة، اتصل بنا: 📞 0556914447", False, None
            else:
                return "أهلاً بك! 🌟 سيتواصل معك أحد متخصصينا قريباً.\n\nهل تريد معرفة عروضنا الحالية؟", False, None
    
    def generate_context_string(self, retrieved_data: List[Dict]) -> str:
        """إنشاء سياق غني من أفضل 3 نتائج"""
        if not retrieved_data:
            return "لا توجد معلومات محددة."
        
        context_parts = []
        for i, item in enumerate(retrieved_data):
            context_parts.append(f" معلومة {i+1}:\n- السؤال المشابه: {item['question']}\n- الإجابة: {item['answer']}")
        
        return "\n\n".join(context_parts)

# --- 📱 نظام WhatsApp السريع ---
class WhatsAppHandler:
    def __init__(self, quick_system):
        self.processing_messages = set()
        self.rate_limit = {}
        self.quick_system = quick_system
    
    def is_duplicate_message(self, message_id: str) -> bool:
        if message_id in self.processing_messages:
            return True
        self.processing_messages.add(message_id)
        threading.Timer(30.0, lambda: self.processing_messages.discard(message_id)).start()
        return False
    
    def check_rate_limit(self, phone_number: str) -> bool:
        now = time.time()
        if phone_number in self.rate_limit:
            if now - self.rate_limit[phone_number] < 0.5:
                return True
        self.rate_limit[phone_number] = now
        return False
    
    def send_message(self, to_number: str, message: str) -> bool:
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            print("❌ معلومات WhatsApp غير مكتملة")
            return False
            
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        message = message.strip()
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "text": {"body": message}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=8)
            response.raise_for_status()
            print(f"✅ تم الإرسال إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ WhatsApp: {e}")
            return False
    
    def send_image_with_text(self, to_number: str, message: str, image_url: str) -> bool:
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            return False
            
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": message
            }
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            print(f"✅ تم إرسال الصورة إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في الصورة: {e}")
            return self.send_message(to_number, f"{message}\n\n📞 لمشاهدة العروض، يرجى التواصل معنا على: 0556914447")

# --- 🎯 تهيئة النظام ---
conversation_manager = ConversationManager()
quick_system = QuickResponseSystem()
whatsapp_handler = WhatsAppHandler(quick_system)

openai_client = None
enhanced_retriever = None
response_generator = None

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI جاهز")

try:
    MODEL_NAME = 'intfloat/multilingual-e5-large'
    PERSIST_DIRECTORY = "my_chroma_db"
    COLLECTION_NAME = "recruitment_qa"
    
    print("📄 تحميل نموذج الذكاء الاصطناعي...")
    model = SentenceTransformer(MODEL_NAME)
    
    print("📄 الاتصال بقاعدة البيانات...")
    chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
    
    enhanced_retriever = EnhancedRetriever(model, collection)
    response_generator = SmartResponseGenerator(openai_client, enhanced_retriever, quick_system)
    
    print(f"✅ النظام جاهز! قاعدة البيانات: {collection.count()} مستند")

except Exception as e:
    print(f"❌ فشل تحميل AI: {e}")
    print("💡 سيعمل بالردود السريعة فقط")
    response_generator = SmartResponseGenerator(openai_client, None, quick_system)

# --- 🚀 المسارات الرئيسية (Webhooks) ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        return 'فشل التحقق', 403
    
    if request.method == 'POST':
        data = request.get_json()
        if data and 'entry' in data:
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if 'messages' in value:
                        for message_data in value['messages']:
                            if message_data.get('type') == 'text':
                                message_id = message_data.get('id', '')
                                phone_number = message_data.get('from', '')
                                user_message = message_data.get('text', {}).get('body', '').strip()
                                if phone_number and user_message:
                                    if not whatsapp_handler.is_duplicate_message(message_id):
                                        if not whatsapp_handler.check_rate_limit(phone_number):
                                            thread = threading.Thread(
                                                target=process_user_message_fast,
                                                args=(phone_number, user_message),
                                                daemon=True
                                            )
                                            thread.start()
        return 'OK', 200

def process_user_message_fast(phone_number: str, user_message: str):
    start_time = time.time()
    try:
        is_first = conversation_manager.is_first_message(phone_number)
        if is_first:
            conversation_manager.register_conversation(phone_number)
        else:
            conversation_manager.update_activity(phone_number)
        
        if response_generator:
            bot_response, should_send_image, image_url = response_generator.generate_response(
                user_message, phone_number, is_first
            )
            if should_send_image and image_url:
                whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
            else:
                whatsapp_handler.send_message(phone_number, bot_response)
        else:
            # Fallback system if AI fails
            if quick_system.is_greeting_message(user_message):
                bot_response = quick_system.get_welcome_response()
            elif quick_system.is_price_inquiry(user_message):
                bot_response, image_url = quick_system.get_price_response()
                whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
                return
            elif quick_system.is_contact_inquiry(user_message):
                bot_response = quick_system.get_contact_response()
            else:
                bot_response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك متخصص قريباً.\n📞 0556914447"
            whatsapp_handler.send_message(phone_number, bot_response)
        
        response_time = time.time() - start_time
        print(f"✅ استجابة في {response_time:.2f}s لـ {phone_number}")
        
    except Exception as e:
        print(f"❌ خطأ فادح في المعالجة: {e}")
        whatsapp_handler.send_message(phone_number, "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى أو التواصل معنا مباشرة على: 📞 0556914447")

@app.route('/')
def status():
    # ... (The status page code remains the same)
    active_conversations = len(conversation_manager.conversations)
    return f"""
    <html><head><title>بوت الركائز - سريع</title>
    <style>body{{font-family:Arial;margin:40px;background:#f0f8ff;}} .box{{background:white;padding:20px;border-radius:10px;margin:10px 0;}} .green{{color:#28a745;}} .red{{color:#dc3545;}}</style></head><body>
    <div class="box"><h1>🚀 مكتب الركائز - بوت سريع</h1></div>
    <div class="box"><h2>📊 الحالة:</h2>
    <p class="{'green' if openai_client else 'red'}">{'✅' if openai_client else '❌'} OpenAI API</p>
    <p class="{'green' if enhanced_retriever else 'red'}">{'✅' if enhanced_retriever else '❌'} قاعدة البيانات</p>
    <p class="green">⚡ الردود السريعة - نشط</p>
    <p class="green">📱 المحادثات النشطة: {active_conversations}</p></div>
    <div class="box"><h2>⚡ المميزات:</h2><ul>
    <li>✅ ردود ترحيب فورية</li>
    <li>✅ كشف أسعار تلقائي مع صورة</li>
    <li>✅ معالجة مخصصة لشكاوى التواصل</li>
    <li>✅ ردود ذكية معززة بسياق أوسع</li>
    </ul></div><p class="green"><strong>النظام يعمل بأقصى سرعة! 🚀</strong></p>
    </body></html>"""

# --- 🧹 التنظيف الدوري ---
def quick_cleanup():
    while True:
        time.sleep(1800)  # كل 30 دقيقة
        conversation_manager.cleanup_old_conversations()
        if len(whatsapp_handler.processing_messages) > 1000:
            whatsapp_handler.processing_messages.clear()
            print("🧹 تنظيف ذاكرة الرسائل")
        
        current_time = time.time()
        expired_numbers = [
            number for number, last_time in whatsapp_handler.rate_limit.items() 
            if current_time - last_time > 3600
        ]
        for number in expired_numbers:
            del whatsapp_handler.rate_limit[number]

cleanup_thread = threading.Thread(target=quick_cleanup, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("🚀 تشغيل بوت الركائز المطور...")
    print("=" * 40)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))