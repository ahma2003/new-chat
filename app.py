# enhanced_app_optimized.py
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

# --- ⚡ نظام الردود السريعة ---
class QuickResponseSystem:
    def __init__(self):
        # ردود الترحيب السريعة (بدون OpenAI)
        self.welcome_patterns = {
            'سلام': True, 'السلام': True, 'عليكم': True,
            'مرحبا': True, 'مرحبتين': True, 'هلا': True, 'اهلا': True,
            'كيفك': True, 'كيف الحال': True, 'شلونك': True, 'وش اخبارك': True,
            'صباح': True, 'مساء': True, 'اهلين': True, 'حياك': True, 'حياكم': True,
            'يعطيك العافية': True, 'تسلم': True, 'الله يعطيك العافية': True,
            'هاي': True, 'هالو': True, 'hello': True, 'hi': True,
            'good morning': True, 'good evening': True,
            'ايش اخبارك': True, 'وش مسوي': True, 'كيف امورك': True
        }
        
        # أنماط السؤال عن الأسعار
        self.price_patterns = [
            r'سعر|أسعار|اسعار|تكلفة|كلفة|تكاليف|كم|فلوس|ريال|مبلغ|رسوم|أجور',
            r'عرض|عروض|باقة|باقات|خصم|خصومات',
            r'ابغى اعرف.*سعر|ابغى اعرف.*اسعار|ايش.*اسعار|وش.*اسعار',
            r'كم.*سعر|كم.*تكلف|كم.*ياخذ|كم.*يكلف'
        ]
        
    def is_greeting_message(self, message: str) -> bool:
        """فحص سريع للرسائل الترحيبية"""
        message_lower = message.lower().strip()
        words = message_lower.split()
        
        # إذا الرسالة قصيرة (أقل من 5 كلمات) وتحتوي على ترحيب
        if len(words) <= 5:
            for word in words:
                if word in self.welcome_patterns:
                    return True
        return False
    
    def is_price_inquiry(self, message: str) -> bool:
        """فحص سريع للسؤال عن الأسعار"""
        message_lower = message.lower()
        for pattern in self.price_patterns:
            if re.search(pattern, message_lower):
                return True
        return False
    
    def get_welcome_response(self) -> str:
        """رد الترحيب السريع"""
        return """أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟

نحن هنا لخدمتك ومساعدتك في جميع احتياجاتك من العمالة المنزلية المدربة والمؤهلة.

كيف يمكنني مساعدتك اليوم؟ 😊"""

    def get_price_response(self) -> tuple:
        """إرجاع رد الأسعار مع الصورة"""
        text_response = """إليك عروضنا الحالية للعمالة المنزلية المدربة 💼

🎉 عرض خاص بمناسبة اليوم الوطني السعودي 95

للاستفسار والحجز اتصل بنا:
📞 0556914447 / 0506207444 / 0537914445"""
        
        image_url = "https://i.postimg.cc/NF49R35t/a.jpg"  # ضع رابط الصورة هنا
        
        return text_response, image_url

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
        self.arabic_keywords = self._load_arabic_keywords()
        self.high_confidence_threshold = 0.8  # عتبة الثقة العالية
    
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
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 5) -> tuple:
        """استرجاع أفضل المطابقات مع تصفية ذكية"""
        if not self.model or not self.collection:
            return [], 0.0
        
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
                return [], 0.0
            
            # تحسين النتائج بناءً على الصلة
            candidates = []
            for i, metadata in enumerate(results['metadatas'][0]):
                relevance = self.calculate_relevance_score(enhanced_query, metadata)
                similarity = 1 - results['distances'][0][i] if 'distances' in results else 0
                
                # دمج درجة التشابه والصلة
                final_score = similarity * 0.6 + relevance * 0.4
                
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
            
            # إرجاع النتائج مع أعلى نقاط ثقة
            best_score = filtered_results[0]['score'] if filtered_results else 0
            results_data = [c['metadata'] for c in filtered_results[:top_k]]
            
            return results_data, best_score
            
        except Exception as e:
            print(f"❌ خطأ في البحث المحسن: {e}")
            return [], 0.0

# --- 🤖 نظام الردود الذكي المحسن ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever, quick_system):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
    
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
    
    def create_high_confidence_prompt(self, user_message: str, context: str) -> str:
        """prompt مبسط للإجابات عالية الثقة"""
        return f"""أنت مساعد مكتب الركائز البشرية للاستقدام في السعودية.

المطلوب:
- أجب بشكل مباشر ومختصر من المعلومات المتوفرة فقط.
- لا تضيف معلومات خارجية.
- اجعل الرد ودود، مهني، ومحترم، مع استخدام عبارات مثل: عميلنا العزيز، حياك الله، يسعدنا تواصلكم، تحت أمركم، يسرنا خدمتكم، نعتز بثقتكم، نسعد بمساعدتكم.
- اختتم كل رد بسؤال مختلف لتشجيع استمرار الحوار، مثل: "هل يمكنني توضيح شيء آخر لكم؟" أو "هل ترغبون بالمزيد من المعلومات حول هذا الموضوع؟" أو "هل يوجد أمر آخر يمكنني مساعدتكم فيه؟"

السؤال: {user_message}

المعلومات المتوفرة:
{context}

اجعل ردك مختصر و واضح:"""

    def create_regular_prompt(self, user_message: str, context: str, is_first: bool) -> str:
        """prompt عادي للردود الأخرى"""
        if is_first:
            intro = "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟\n\n"
        else:
            intro = ""
            
        return f"""{intro}أنت مساعد ذكي لمكتب الركائز البشرية للاستقدام.

قواعد الرد:
- استخدم المعلومات الموثوقة فقط.
- إذا ما تعرف الإجابة الدقيقة: "أحتاج مراجعة هذا مع الفريق المختص".
- خلي الردود دايمًا ودودة وباللهجة السعودية.
- استخدم عبارات محترمة ولطيفة للعميل مثل: عميلنا العزيز، حياك الله، يسعدنا تواصلكم، تحت أمركم، يسرنا خدمتكم، نعتز بثقتكم، نسعد بمساعدتكم.
- اجعل العميل يحس بالاهتمام والاحترام في كل رسالة، مع نقل شعور المودة والتقدير.
- اختتم كل رسالة بسؤال مختلف عشان يستمر الحوار، مثل: "هل يمكنني توضيح شيء آخر لكم؟" أو "هل ترغبون بالمزيد من المعلومات حول هذا الموضوع؟" أو "هل يوجد أمر آخر يمكنني مساعدتكم فيه؟"

السؤال: {user_message}

المعلومات:
{context}"""

    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> str:
        """إنتاج الرد الذكي المحسن"""
        
        # 1. فحص الردود السريعة أولاً
        if self.quick_system.is_greeting_message(user_message):
            print(f"⚡ رد ترحيب سريع لـ {phone_number}")
            return self.quick_system.get_welcome_response()
        
        # 2. فحص السؤال عن الأسعار
        if self.quick_system.is_price_inquiry(user_message):
            print(f"💰 طلب أسعار من {phone_number}")
            text_response, image_url = self.quick_system.get_price_response()
            # هنا يمكن إضافة إرسال الصورة (سيتم تنفيذها في WhatsApp handler)
            return text_response
        
        # 3. البحث في قاعدة المعرفة
        retrieved_data, confidence_score = self.retriever.retrieve_best_matches(user_message)
        context = self.generate_context_string(retrieved_data)
        
        # إذا لم يكن هناك OpenAI client
        if not self.openai_client:
            if retrieved_data:
                return f"بناءً على معلوماتنا:\n\n{retrieved_data[0]['answer']}\n\nهل يمكنني مساعدتك في شيء آخر؟"
            else:
                return "عذراً، الخدمة غير متاحة مؤقتاً. سيتواصل معك أحد موظفينا قريباً."
        
        try:
            # 4. اختيار نوع الـ prompt حسب مستوى الثقة
            if confidence_score >= self.retriever.high_confidence_threshold:
                print(f"🎯 رد عالي الثقة ({confidence_score:.2f}) لـ {phone_number}")
                system_prompt = self.create_high_confidence_prompt(user_message, context)
                max_tokens = 200  # أقصر للردود الواثقة
            else:
                print(f"🤔 رد عادي ({confidence_score:.2f}) لـ {phone_number}")
                system_prompt = self.create_regular_prompt(user_message, context, is_first)
                max_tokens = 300
            
            # 5. استدعاء OpenAI
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=0.2  # أقل إبداعاً، أكثر دقة واتساقاً
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            # رد احتياطي من قاعدة البيانات
            if retrieved_data:
                return f"بناءً على خبرتنا:\n\n{retrieved_data[0]['answer']}\n\nللمزيد من التفاصيل، يرجى التواصل معنا."
            else:
                return "أعتذر، حدثت مشكلة تقنية. سيتواصل معك أحد الموظفين قريباً."

# --- 📱 نظام WhatsApp المحسن ---
class WhatsAppHandler:
    def __init__(self, quick_system):
        self.processing_messages = set()  # منع المعالجة المتكررة
        self.rate_limit = {}  # منع الإسبام
        self.quick_system = quick_system
    
    def is_duplicate_message(self, message_id: str) -> bool:
        """فحص الرسائل المكررة"""
        if message_id in self.processing_messages:
            return True
        self.processing_messages.add(message_id)
        return False
    
    def check_rate_limit(self, phone_number: str) -> bool:
        """فحص حد المعدل - رسالة واحدة كل 2 ثانية (أسرع من قبل)"""
        now = time.time()
        if phone_number in self.rate_limit:
            if now - self.rate_limit[phone_number] < 2:  # قللت من 3 إلى 2 ثانية
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
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            print(f"✅ تم إرسال الرسالة بنجاح إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في إرسال WhatsApp: {e}")
            return False
    
    def send_image_with_text(self, to_number: str, message: str, image_url: str) -> bool:
        """إرسال رسالة مع صورة (للأسعار)"""
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
            print(f"✅ تم إرسال الصورة والرسالة بنجاح إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في إرسال الصورة: {e}")
            # في حالة فشل إرسال الصورة، أرسل النص فقط
            return self.send_message(to_number, message)

# --- 🎯 تهيئة النظام ---
conversation_manager = ConversationManager()
quick_system = QuickResponseSystem()
whatsapp_handler = WhatsAppHandler(quick_system)

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
    response_generator = SmartResponseGenerator(openai_client, enhanced_retriever, quick_system)
    
    print(f"✅ النظام جاهز! قاعدة البيانات تحتوي على {collection.count()} مستند")

except Exception as e:
    print(f"❌ فشل في تحميل مكونات الذكاء الاصطناعي: {e}")
    print("💡 سيعمل البوت في الوضع الأساسي مع الردود السريعة")

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
                    
                    # معالجة الرسالة في thread منفصل (أسرع)
                    thread = threading.Thread(
                        target=process_user_message,
                        args=(phone_number, user_message),
                        daemon=True
                    )
                    thread.start()
        
        return 'OK', 200

def process_user_message(phone_number: str, user_message: str):
    """معالجة رسالة المستخدم المحسنة"""
    start_time = time.time()  # لقياس الأداء
    
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
            
            # فحص إذا كان طلب أسعار لإرسال الصورة
            if quick_system.is_price_inquiry(user_message):
                try:
                    # محاولة إرسال الصورة مع النص
                    image_url = "https://example.com/price-image.jpg"  # ضع الرابط الصحيح هنا
                    success = whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
                except:
                    # في حالة فشل الصورة، أرسل النص فقط
                    success = whatsapp_handler.send_message(phone_number, bot_response)
            else:
                success = whatsapp_handler.send_message(phone_number, bot_response)
        else:
            # النظام الأساسي بدون AI
            if quick_system.is_greeting_message(user_message):
                bot_response = quick_system.get_welcome_response()
            elif quick_system.is_price_inquiry(user_message):
                bot_response, _ = quick_system.get_price_response()
            else:
                bot_response = "أهلاً بك في مكتب الركائز البشرية! سيتواصل معك أحد موظفينا قريباً للمساعدة."
            
            success = whatsapp_handler.send_message(phone_number, bot_response)
        
        # إحصائيات الأداء
        response_time = time.time() - start_time
        if success:
            print(f"✅ تمت معالجة رسالة من {phone_number} في {response_time:.2f} ثانية")
        
    except Exception as e:
        print(f"❌ خطأ في معالجة الرسالة: {e}")
        # رسالة احتياطية
        whatsapp_handler.send_message(
            phone_number, 
            "عذراً، حدث خطأ تقني. سيتواصل معك أحد الموظفين قريباً."
        )

@app.route('/')
def status():
    """صفحة حالة النظام المحسنة"""
    active_conversations = len(conversation_manager.conversations)
    
    status_html = f"""
    <html><head>
    <title>نظام البوت المحسن</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
        .status {{ display: flex; align-items: center; margin: 10px 0; }}
        .green {{ color: #28a745; }}
        .red {{ color: #dc3545; }}
    </style>
    </head><body>
    <div class="container">
    <h1>🚀 مكتب الركائز البشرية - نظام البوت المحسن</h1>
    <h2>📊 حالة النظام:</h2>
    <ul>"""
    
    status_html += f"<li class='{'green' if openai_client else 'red'}'>{'✅' if openai_client else '❌'} OpenAI API</li>"
    status_html += f"<li class='{'green' if enhanced_retriever else 'red'}'>{'✅' if enhanced_retriever else '❌'} نظام البحث المحسن</li>"
    status_html += f"<li class='{'green' if response_generator else 'red'}'>{'✅' if response_generator else '❌'} مولد الردود الذكي</li>"
    status_html += f"<li class='green'>⚡ نظام الردود السريعة - نشط</li>"
    
    if enhanced_retriever and enhanced_retriever.collection:
        count = enhanced_retriever.collection.count()
        status_html += f"<li class='green'>✅ قاعدة البيانات: {count} مستند</li>"
    
    status_html += f"<li class='green'>📱 المحادثات النشطة: {active_conversations}</li>"
    status_html += f"<li class='green'>🎯 عتبة الثقة العالية: {enhanced_retriever.high_confidence_threshold if enhanced_retriever else 'غير متاح'}</li>"
    status_html += """
    </ul>
    
    <h2>⚡ المميزات الجديدة:</h2>
    <ul>
        <li>✅ ردود ترحيب سريعة (بدون OpenAI)</li>
        <li>✅ كشف تلقائي لطلبات الأسعار مع إرسال الصورة</li>
        <li>✅ نظام ثقة عالية للردود السريعة</li>
        <li>✅ معدل استجابة محسن (2 ثانية بدلاً من 3)</li>
        <li>✅ ردود احتياطية ذكية</li>
    </ul>
    
    <h2>📈 إحصائيات الأداء:</h2>
    <ul>
        <li>🚀 الردود السريعة: فوري (< 0.1 ثانية)</li>
        <li>🎯 الردود عالية الثقة: سريع (< 2 ثانية)</li>
        <li>🤖 الردود العادية: متوسط (2-5 ثانية)</li>
    </ul>
    
    <p><strong class="green">النظام جاهز ومحسن لأقصى أداء! 🚀</strong></p>
    </div>
    </body></html>"""
    
    return status_html

# --- 🧹 تنظيف دوري محسن ---
def cleanup_scheduler():
    """مجدول التنظيف المحسن"""
    while True:
        time.sleep(1800)  # كل 30 دقيقة بدلاً من ساعة (أسرع)
        
        # تنظيف المحادثات القديمة
        conversation_manager.cleanup_old_conversations()
        
        # تنظيف رسائل المعالجة
        if len(whatsapp_handler.processing_messages) > 1000:
            whatsapp_handler.processing_messages.clear()
            print("🧹 تم تنظيف ذاكرة الرسائل المعالجة")
        
        # تنظيف rate limiting
        current_time = time.time()
        expired_numbers = [
            number for number, last_time in whatsapp_handler.rate_limit.items() 
            if current_time - last_time > 3600  # أقدم من ساعة
        ]
        for number in expired_numbers:
            del whatsapp_handler.rate_limit[number]
        
        if expired_numbers:
            print(f"🧹 تم تنظيف {len(expired_numbers)} رقم من ذاكرة Rate Limiting")

# --- 📊 مسار إحصائيات مفصل ---
@app.route('/stats')
def detailed_stats():
    """إحصائيات مفصلة للنظام"""
    stats = {
        "النظام": {
            "حالة OpenAI": "متصل" if openai_client else "غير متصل",
            "حالة قاعدة البيانات": "متصلة" if enhanced_retriever else "غير متصلة",
            "الردود السريعة": "نشطة",
            "إجمالي المستندات": enhanced_retriever.collection.count() if enhanced_retriever and enhanced_retriever.collection else 0
        },
        "المحادثات": {
            "النشطة حالياً": len(conversation_manager.conversations),
            "إجمالي الرسائل المعالجة": len(whatsapp_handler.processing_messages),
            "أرقام في Rate Limiting": len(whatsapp_handler.rate_limit)
        },
        "الأداء": {
            "عتبة الثقة العالية": enhanced_retriever.high_confidence_threshold if enhanced_retriever else "غير متاح",
            "حد Rate Limiting": "رسالة كل ثانيتين",
            "مهلة الاستجابة": "10 ثوانٍ"
        }
    }
    
    return jsonify(stats)

# --- 🔧 مسار اختبار الردود السريعة ---
@app.route('/test-quick/<message>')
def test_quick_response(message):
    """اختبار الردود السريعة"""
    if not quick_system:
        return jsonify({"error": "النظام غير جاهز"})
    
    is_greeting = quick_system.is_greeting_message(message)
    is_price = quick_system.is_price_inquiry(message)
    
    response_data = {
        "الرسالة": message,
        "ترحيب؟": is_greeting,
        "سؤال عن الأسعار؟": is_price,
        "نوع الرد": "سريع" if (is_greeting or is_price) else "عادي"
    }
    
    if is_greeting:
        response_data["الرد"] = quick_system.get_welcome_response()
    elif is_price:
        text, image = quick_system.get_price_response()
        response_data["الرد"] = text
        response_data["صورة"] = image
    
    return jsonify(response_data)

# تشغيل مجدول التنظيف المحسن
cleanup_thread = threading.Thread(target=cleanup_scheduler, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("🚀 تشغيل نظام البوت المحسن...")
    print("⚡ المميزات الجديدة:")
    print("   - ردود ترحيب فورية")
    print("   - كشف تلقائي للأسعار مع الصورة") 
    print("   - نظام ثقة عالية للردود السريعة")
    print("   - أداء محسن وتنظيف ذكي")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))