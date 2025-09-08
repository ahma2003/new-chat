# enhanced_app.py
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

# --- 🚀 نظام ذاكرة محادثات متقدم ---
class ConversationManager:
    def __init__(self):
        self.conversations = {}
        self.message_lock = threading.Lock()
        self.cleanup_interval = 3600  # تنظيف كل ساعة
        
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

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
        self.arabic_keywords = self._load_arabic_keywords()
    
    def _load_arabic_keywords(self) -> Dict[str, List[str]]:
        """كلمات مفتاحية لتحسين البحث"""
        return {
            'تكلفة': ['سعر', 'تكاليف', 'رسوم', 'أجور', 'مبلغ', 'فلوس'],
            'مدة': ['وقت', 'فترة', 'زمن', 'متى', 'كم يوم'],
            'عاملة': ['خادمة', 'شغالة', 'مربية', 'عاملة منزلية'],
            'استقدام': ['جلب', 'إحضار', 'توظيف', 'تعيين'],
            'تأشيرة': ['فيزا', 'تصريح', 'إقامة'],
            'عقد': ['اتفاقية', 'التزام', 'شروط']
        }
    
    def preprocess_query(self, query: str) -> str:
        """تحسين الاستعلام قبل البحث"""
        # تنظيف النص
        query = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', query)
        query = re.sub(r'\s+', ' ', query).strip()
        
        # إضافة مرادفات للكلمات المهمة
        enhanced_query = query
        for main_word, synonyms in self.arabic_keywords.items():
            for synonym in synonyms:
                if synonym in query:
                    enhanced_query += f" {main_word}"
                    break
        
        return enhanced_query
    
    def calculate_relevance_score(self, query: str, metadata: dict) -> float:
        """حساب درجة الصلة بالموضوع"""
        query_words = set(query.split())
        question_words = set(metadata.get('question_clean', '').split())
        answer_words = set(metadata.get('answer_clean', '').split())
        
        # تطابق مع السؤال (وزن أعلى)
        question_overlap = len(query_words & question_words) / max(len(query_words), 1)
        
        # تطابق مع الإجابة
        answer_overlap = len(query_words & answer_words) / max(len(query_words), 1)
        
        # النتيجة النهائية
        return (question_overlap * 0.7) + (answer_overlap * 0.3)
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 5) -> List[dict]:
        """استرجاع أفضل المطابقات مع تصفية ذكية"""
        if not self.model or not self.collection:
            return []
        
        try:
            # تحسين الاستعلام
            enhanced_query = self.preprocess_query(user_query)
            prefixed_query = f"query: {enhanced_query}"
            
            # البحث في ChromaDB
            query_embedding = self.model.encode([prefixed_query], normalize_embeddings=True)
            results = self.collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=min(top_k * 2, 10)  # جلب أكثر للتصفية
            )
            
            if not results.get('metadatas') or not results['metadatas'][0]:
                return []
            
            # تحسين النتائج بناءً على الصلة
            candidates = []
            for i, metadata in enumerate(results['metadatas'][0]):
                relevance = self.calculate_relevance_score(enhanced_query, metadata)
                similarity = results['distances'][0][i] if 'distances' in results else 0
                
                # دمج درجة التشابه والصلة
                final_score = (1 - similarity) * 0.6 + relevance * 0.4
                
                candidates.append({
                    'metadata': metadata,
                    'score': final_score,
                    'similarity': similarity,
                    'relevance': relevance
                })
            
            # ترتيب وإرجاع الأفضل
            candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # تصفية النتائج الضعيفة
            threshold = 0.3
            filtered_results = [c for c in candidates if c['score'] > threshold]
            
            return [c['metadata'] for c in filtered_results[:top_k]]
            
        except Exception as e:
            print(f"❌ خطأ في البحث المحسن: {e}")
            return []

# --- 🤖 نظام الردود الذكي ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever):
        self.openai_client = openai_client
        self.retriever = retriever
    
    def generate_context_string(self, retrieved_data: List[dict]) -> str:
        """إنشاء نص السياق بطريقة منظمة"""
        if not retrieved_data:
            return "لا توجد معلومات محددة في قاعدة المعرفة حول هذا الموضوع."
        
        context_parts = []
        for i, item in enumerate(retrieved_data[:3], 1):  # أفضل 3 نتائج فقط
            context_parts.append(
                f"--- معلومة {i} ---\n"
                f"السؤال: {item['question']}\n"
                f"الإجابة: {item['answer']}\n"
            )
        
        return "\n".join(context_parts)
    
    def create_first_message_prompt(self, user_message: str, context: str) -> str:
        """بناء prompt للرسالة الأولى"""
        return f"""أنت مساعد ذكي لمكتب "الركائز البشرية للاستقدام" في السعودية.

**مهمتك في الرسالة الأولى:**
1. ابدأ بترحيب حار وودود: "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟"
2. اذكر أنك هنا لمساعدة العميل في أي استفسار
3. أجب على سؤاله بدقة إذا كانت المعلومة متوفرة

**قواعد الإجابة:**
- استخدم المعلومات الموثوقة من قاعدة البيانات فقط
- إذا لم تجد إجابة دقيقة، قل: "هذا الاستفسار يحتاج مراجعة من فريق الخبراء، سنتواصل معك قريباً"
- اجعل الرد ودود ومريح للعميل السعودي
- لا تخترع معلومات

**استفسار العميل:** {user_message}

**المعلومات المتوفرة:**
{context}

**اجعل ردك مختصر ومفيد ومريح.**"""

    def create_followup_prompt(self, user_message: str, context: str) -> str:
        """بناء prompt للرسائل التالية"""
        return f"""أنت مساعد خبير لمكتب الركائز البشرية للاستقدام.

**قواعد الرد:**
- أجب بشكل مباشر ومفيد
- استخدم المعلومات الموثوقة فقط
- إذا لم تعرف الإجابة الدقيقة: "أحتاج مراجعة هذا مع الفريق المختص"
- اختتم بـ "هل يمكنني مساعدتك في شيء آخر؟"

**السؤال:** {user_message}

**المعلومات:**
{context}"""

    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> str:
        """إنتاج الرد الذكي"""
        if not self.openai_client:
            return "عذراً، الخدمة غير متاحة مؤقتاً. سيتواصل معك أحد موظفينا قريباً."
        
        # البحث عن المعلومات
        retrieved_data = self.retriever.retrieve_best_matches(user_message)
        context = self.generate_context_string(retrieved_data)
        
        # اختيار النوع المناسب من الـ prompt
        if is_first:
            system_prompt = self.create_first_message_prompt(user_message, context)
        else:
            system_prompt = self.create_followup_prompt(user_message, context)
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=300,  # تحديد طول الرد
                temperature=0.3  # أقل إبداعاً، أكثر دقة
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            return "أعتذر، حدثت مشكلة تقنية. سيتواصل معك أحد الموظفين قريباً."

# --- 📱 نظام WhatsApp المحسن ---
class WhatsAppHandler:
    def __init__(self):
        self.processing_messages = set()  # منع المعالجة المتكررة
        self.rate_limit = {}  # منع الإسبام
    
    def is_duplicate_message(self, message_id: str) -> bool:
        """فحص الرسائل المكررة"""
        if message_id in self.processing_messages:
            return True
        self.processing_messages.add(message_id)
        return False
    
    def check_rate_limit(self, phone_number: str) -> bool:
        """فحص حد المعدل - رسالة واحدة كل 3 ثواني"""
        now = time.time()
        if phone_number in self.rate_limit:
            if now - self.rate_limit[phone_number] < 3:
                return True
        self.rate_limit[phone_number] = now
        return False
    
    def send_message(self, to_number: str, message: str) -> bool:
        """إرسال رسالة WhatsApp محسنة"""
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # تحسين الرسالة
        message = message.strip()
        if len(message) > 1000:  # حد أقصى للطول
            message = message[:950] + "... (للمزيد اتصل بنا)"
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "text": {"body": message}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            print(f"✅ تم إرسال الرسالة بنجاح إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في إرسال WhatsApp: {e}")
            return False

# --- 🎯 تهيئة النظام ---
conversation_manager = ConversationManager()
whatsapp_handler = WhatsAppHandler()

# تحميل مكونات الذكاء الاصطناعي
openai_client = None
enhanced_retriever = None
response_generator = None

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI جاهز")

# تحميل ChromaDB والنموذج
try:
    MODEL_NAME = 'intfloat/multilingual-e5-large'
    PERSIST_DIRECTORY = "my_chroma_db"
    COLLECTION_NAME = "recruitment_qa"
    
    print("🔄 جاري تحميل نموذج الذكاء الاصطناعي...")
    model = SentenceTransformer(MODEL_NAME)
    
    print("🔄 جاري الاتصال بقاعدة البيانات...")
    chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
    
    enhanced_retriever = EnhancedRetriever(model, collection)
    response_generator = SmartResponseGenerator(openai_client, enhanced_retriever)
    
    print(f"✅ النظام جاهز! قاعدة البيانات تحتوي على {collection.count()} مستند")

except Exception as e:
    print(f"❌ فشل في تحميل مكونات الذكاء الاصطناعي: {e}")
    print("💡 سيعمل البوت في الوضع الأساسي")

# --- 🚀 المسارات الرئيسية ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # التحقق من webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        return 'فشل التحقق', 403
    
    if request.method == 'POST':
        data = request.get_json()
        
        if not data or 'entry' not in data:
            return 'OK', 200
        
        # معالجة الرسائل الواردة
        for entry in data['entry']:
            for change in entry.get('changes', []):
                value = change.get('value', {})
                
                if 'messages' not in value:
                    continue
                
                for message_data in value['messages']:
                    # التأكد أن الرسالة نصية
                    if message_data.get('type') != 'text':
                        continue
                    
                    message_id = message_data.get('id', '')
                    phone_number = message_data.get('from', '')
                    user_message = message_data.get('text', {}).get('body', '').strip()
                    
                    # فحوص الأمان
                    if not phone_number or not user_message:
                        continue
                    
                    if whatsapp_handler.is_duplicate_message(message_id):
                        print(f"⚠️ رسالة مكررة تم تجاهلها: {message_id}")
                        continue
                    
                    if whatsapp_handler.check_rate_limit(phone_number):
                        print(f"⚠️ تم تجاهل رسالة لسرعة الإرسال: {phone_number}")
                        continue
                    
                    # معالجة الرسالة في thread منفصل
                    thread = threading.Thread(
                        target=process_user_message,
                        args=(phone_number, user_message)
                    )
                    thread.daemon = True
                    thread.start()
        
        return 'OK', 200

def process_user_message(phone_number: str, user_message: str):
    """معالجة رسالة المستخدم"""
    try:
        # التحقق من حالة المحادثة
        is_first = conversation_manager.is_first_message(phone_number)
        
        if is_first:
            conversation_manager.register_conversation(phone_number)
        else:
            conversation_manager.update_activity(phone_number)
        
        # توليد الرد
        if response_generator:
            bot_response = response_generator.generate_response(
                user_message, phone_number, is_first
            )
        else:
            bot_response = "أهلاً بك في مكتب الركائز البشرية! سيتواصل معك أحد موظفينا قريباً للمساعدة."
        
        # إرسال الرد
        success = whatsapp_handler.send_message(phone_number, bot_response)
        
        if success:
            print(f"✅ تمت معالجة رسالة من {phone_number}")
        
    except Exception as e:
        print(f"❌ خطأ في معالجة الرسالة: {e}")
        # رسالة احتياطية
        whatsapp_handler.send_message(
            phone_number, 
            "عذراً، حدث خطأ تقني. سيتواصل معك أحد الموظفين قريباً."
        )

@app.route('/')
def status():
    """صفحة حالة النظام"""
    status_html = """
    <html><head><title>نظام البوت المحسن</title></head><body>
    <h1>🤖 مكتب الركائز البشرية - نظام البوت الذكي</h1>
    <h2>📊 حالة النظام:</h2>
    <ul>
    """
    
    status_html += f"<li>{'✅' if openai_client else '❌'} OpenAI API</li>"
    status_html += f"<li>{'✅' if enhanced_retriever else '❌'} نظام البحث المحسن</li>"
    status_html += f"<li>{'✅' if response_generator else '❌'} مولد الردود الذكي</li>"
    
    if enhanced_retriever and enhanced_retriever.collection:
        count = enhanced_retriever.collection.count()
        status_html += f"<li>✅ قاعدة البيانات: {count} مستند</li>"
    
    status_html += f"<li>🔄 المحادثات النشطة: {len(conversation_manager.conversations)}</li>"
    status_html += """
    </ul>
    <p><strong>النظام جاهز لاستقبال الرسائل! 🚀</strong></p>
    </body></html>
    """
    
    return status_html

# --- 🧹 تنظيف دوري ---
def cleanup_scheduler():
    """مجدول التنظيف"""
    while True:
        time.sleep(3600)  # كل ساعة
        conversation_manager.cleanup_old_conversations()
        
        # تنظيف رسائل المعالجة
        if len(whatsapp_handler.processing_messages) > 1000:
            whatsapp_handler.processing_messages.clear()

# تشغيل مجدول التنظيف
cleanup_thread = threading.Thread(target=cleanup_scheduler)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    print("🚀 تشغيل نظام البوت المحسن...")
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))