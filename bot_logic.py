# bot_logic.py
import threading
import random
from datetime import datetime, timedelta
from database import get_customer_details_from_db

# --- 🧠 نظام Memory العملاء الذكي (يعتمد الآن على قاعدة البيانات) ---
class CustomerMemoryManager:
    def __init__(self):
        self.customer_cache = {}  # Cache للعملاء النشطين لتقليل الضغط على الداتابيز
        self.conversation_history = {}
        self.memory_lock = threading.Lock()

    def get_customer_info(self, phone_number: str):
        with self.memory_lock:
            # 1. البحث في الـ cache أولاً للسرعة
            if phone_number in self.customer_cache:
                print(f"🎯 العميل موجود في الذاكرة (Cache): {phone_number}")
                return self.customer_cache[phone_number]
            
            # 2. إذا لم يكن في الكاش، ابحث في قاعدة البيانات
            print(f"🔍 البحث عن العميل في قاعدة البيانات: {phone_number}")
            customer_data = get_customer_details_from_db(phone_number)
            
            if customer_data:
                # إضافة العميل للـ cache لتسريع الطلبات المستقبلية
                self.customer_cache[phone_number] = customer_data
                print(f"✅ تم تحميل العميل للذاكرة: {customer_data.get('name', 'غير معروف')}")
                return customer_data
            
            print(f"🆕 عميل جديد (غير موجود في قاعدة البيانات): {phone_number}")
            return None

    def add_conversation_message(self, phone_number: str, user_message: str, bot_response: str):
        """إضافة رسالة للتاريخ المحادثة"""
        with self.memory_lock:
            if phone_number not in self.conversation_history:
                self.conversation_history[phone_number] = []
            
            self.conversation_history[phone_number].append({
                'timestamp': datetime.now().isoformat(),
                'user_message': user_message,
                'bot_response': bot_response
            })
            
            # الاحتفاظ بآخر 10 رسائل فقط لكل عميل
            if len(self.conversation_history[phone_number]) > 10:
                self.conversation_history[phone_number] = self.conversation_history[phone_number][-10:]
    
    def get_conversation_context(self, phone_number: str) -> str:
        """جلب سياق المحادثة السابقة"""
        with self.memory_lock:
            if phone_number not in self.conversation_history:
                return ""
            
            recent_messages = self.conversation_history[phone_number][-3:]  # آخر 3 رسائل
            context = ""
            for msg in recent_messages:
                context += f"العميل: {msg['user_message']}\n"
                context += f"البوت: {msg['bot_response'][:100]}...\n"
            return context
    
    def create_customer_summary(self, customer_data: dict) -> str:
        """إنشاء ملخص مختصر وذكي للعميل"""
        if not customer_data:
            return "عميل جديد غير مسجل."
        
        name = customer_data.get('name', 'عميل كريم')
        gender = customer_data.get('gender', '')
        preferred_nationality = customer_data.get('preferred_nationality', '')
        past_services = customer_data.get('past_services', [])
        current_requests = customer_data.get('current_requests', [])
        
        summary = f"العميل: {name}"
        if gender == 'ذكر':
            summary += " (أخونا الكريم)"
        elif gender == 'أنثى':
            summary += " (أختنا الكريمة)"
        
        if past_services:
            summary += f"\n- له تعاملات سابقة معنا (عدد {len(past_services)} خدمة)."
            latest_service = past_services[0]
            summary += f"\n- آخر خدمة: {latest_service.get('job_title', '')} - {latest_service.get('worker_name', '')} ({latest_service.get('nationality', '')})."
        
        if current_requests:
            current_req = current_requests[0]
            summary += f"\n- طلب حالي: {current_req.get('type', '')} - الحالة: {current_req.get('status', '')}."
        
        if preferred_nationality:
            summary += f"\n- يفضل الجنسية: {preferred_nationality}."
        
        return summary

    def cleanup_old_cache(self):
        """تنظيف الذاكرة من العملاء القدامى"""
        with self.memory_lock:
            if len(self.customer_cache) > 50:
                keys_to_remove = list(self.customer_cache.keys())[:25]
                for key in keys_to_remove:
                    del self.customer_cache[key]
                print("🧹 تم تنظيف ذاكرة العملاء المؤقتة (Cache)")

# --- 🚀 نظام ذاكرة محادثات محسّن ---
class ConversationManager:
    # ... هذا الكلاس صحيح، لا حاجة لتعديله
    def __init__(self, customer_memory):
        self.conversations = {}
        self.message_lock = threading.Lock()
        self.customer_memory = customer_memory
        
    def is_first_message(self, phone_number: str) -> bool:
        with self.message_lock:
            return phone_number not in self.conversations
    
    def register_conversation(self, phone_number: str):
        with self.message_lock:
            customer_info = self.customer_memory.get_customer_info(phone_number)
            self.conversations[phone_number] = {
                'last_activity': datetime.now(),
                'is_existing_customer': customer_info is not None,
                'customer_name': customer_info.get('name', '') if customer_info else ''
            }
    
    def update_activity(self, phone_number: str):
        with self.message_lock:
            if phone_number in self.conversations:
                self.conversations[phone_number]['last_activity'] = datetime.now()
    
    def cleanup_old_conversations(self):
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
    # ... هذا الكلاس صحيح، لا حاجة لتعديله
    def __init__(self):
        self.welcome_patterns = {
            'سلام', 'السلام', 'عليكم', 'مرحبا', 'مرحبتين', 'هلا', 'اهلا',
            'كيفك', 'كيف الحال', 'شلونك', 'وش اخبارك', 'صباح', 'مساء',
            'اهلين', 'حياك', 'حياكم', 'يعطيك العافية', 'تسلم',
            'الله يعطيك العافية', 'هاي', 'هالو', 'hello', 'hi',
            'good morning', 'good evening'
        }
        self.thanks_patterns = {
             'شكرا', 'شكراً', 'شكر', 'مشكور', 'مشكوره', 'تسلم', 'تسلمي',
             'تسلمين', 'تسلمون', 'يعطيك', 'يعطيكم', 'الله يعطيك', 'الله يعطيكم',
             'العافية', 'يعطيك العافية', 'الله يعطيك العافية', 'جزاك', 'جزاكم',
             'جزاك الله', 'جزاكم الله', 'خيراً', 'خير', 'جزاك الله خير',
             'ماقصرت', 'ماقصرتوا', 'مشكورين', 'thank', 'thanks', 'appreciate',
             'بارك', 'بارك الله', 'الله يبارك', 'تمام', 'زين', 'ممتاز', 'perfect'
        }
        self.price_keywords = {
            'سعر', 'اسعار', 'أسعار', 'تكلفة', 'كلفة', 'تكاليف', 'اسعاركم',
            'فلوس', 'ريال', 'مبلغ', 'رسوم', 'عروضكم', 'عرض', 'عروض',
            'باقة', 'باقات', 'خصم', 'خصومات', 'بكم'
        }

    def is_greeting_message(self, message: str) -> bool:
        message_clean = message.lower().strip()
        words = message_clean.split()
        if len(words) <= 5:
            return any(word in self.welcome_patterns for word in words)
        return False

    def is_thanks_message(self, message: str) -> bool:
        message_clean = message.lower().strip()
        return any(word in message_clean for word in self.thanks_patterns)

    def is_price_inquiry(self, message: str) -> bool:
        message_clean = message.lower().strip()
        return any(keyword in message_clean for keyword in self.price_keywords)

    def get_welcome_response(self, customer_name: str = None) -> str:
        if customer_name:
            return f"أهلاً وسهلاً أخونا {customer_name} الكريم 🌟\n\nحياك الله مرة ثانية في مكتب الركائز البشرية للاستقدام.\n\nكيف يمكنني مساعدتك اليوم؟ 😊"
        return "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟\n\nكيف يمكنني مساعدتك اليوم؟ 😊"

    def get_thanks_response(self, customer_name: str = None) -> str:
        base_responses = [
            "العفو {name} 🌟\n\nالله يعطيك العافية.. نحن في خدمتك دائماً.",
            "أهلاً وسهلاً {name}.. هذا واجبنا 🤝\n\nنحن سعداء بخدمتك.",
            "حياك الله {name}.. ما سوينا إلا الواجب 🌟\n\nتواصل معنا في أي وقت!"
        ]
        name_str = f"أخونا {customer_name}" if customer_name else "عميلنا العزيز"
        return random.choice(base_responses).format(name=name_str)

    def get_price_response(self) -> tuple:
        text_response = "إليك عروضنا الحالية للعمالة المنزلية المدربة 💼\n\n🎉 عرض خاص بمناسبة اليوم الوطني السعودي 95\n\nللاستفسار والحجز اتصل بنا:\n📞 0556914447 / 0506207444 / 0537914445"
        image_url = "https://i.imghippo.com/files/La2232xjc.jpg"
        return text_response, image_url

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    # ... هذا الكلاس صحيح، لا حاجة لتعديله
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 3) -> tuple:
        if not self.model or not self.collection:
            return [], 0.0
        try:
            query_embedding = self.model.encode([f"query: {user_query}"], normalize_embeddings=True)
            results = self.collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=min(top_k, 5)
            )
            if not results.get('metadatas') or not results['metadatas'][0]:
                return [], 0.0
            
            results_data = results['metadatas'][0]
            return results_data, 0.0
        except Exception as e:
            print(f"❌ خطأ في البحث: {e}")
            return [], 0.0

# --- 🤖 نظام الردود الذكي مع الذاكرة الشخصية ---
class SmartResponseGenerator:
    # ... تم تعديل هذا الكلاس وإصلاح الأخطاء
    def __init__(self, openai_client, retriever, quick_system, customer_memory):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
        self.customer_memory = customer_memory
    
    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> tuple:
        """إنتاج الرد الذكي مع الذاكرة الشخصية"""
        
        customer_info = self.customer_memory.get_customer_info(phone_number)
        customer_name = customer_info.get('name') if customer_info else None
        
        # 1. الردود الفورية
        if self.quick_system.is_greeting_message(user_message):
            response = self.quick_system.get_welcome_response(customer_name)
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        if self.quick_system.is_thanks_message(user_message):
            response = self.quick_system.get_thanks_response(customer_name)
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        if self.quick_system.is_price_inquiry(user_message):
            text_response, image_url = self.quick_system.get_price_response()
            self.customer_memory.add_conversation_message(phone_number, user_message, text_response)
            return text_response, True, image_url
        
        # 2. الردود المعتمدة على الذكاء الاصطناعي
        retrieved_data, _ = self.retriever.retrieve_best_matches(user_message) if self.retriever else ([], 0)
        
        if not self.openai_client:
            response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة."
            if customer_name:
                response = f"أهلاً بك مرة ثانية أخونا {customer_name}! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة."
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        try:
            context = self.generate_context_string(retrieved_data)
            conversation_context = self.customer_memory.get_conversation_context(phone_number)
            customer_summary = self.customer_memory.create_customer_summary(customer_info)
            
            system_prompt = f"""أنت مساعد ذكي لمكتب الركائز البشرية للاستقدام.
معلومات العميل: {customer_summary}
آخر محادثات: {conversation_context}
أجب بشكل مختصر وودود من المعلومات المتوفرة فقط. استخدم عبارات: عميلنا الكريم، حياك الله. إذا كان العميل له تعامل سابق، أشر إليه بلطف. اختتم بسؤال لتشجيع الحوار.
السؤال: {user_message}
المعلومات: {context}"""

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=500,
                temperature=0.1
            )
            bot_response = response.choices[0].message.content.strip()
            self.customer_memory.add_conversation_message(phone_number, user_message, bot_response)
            return bot_response, False, None
            
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            response = "عذراً، نواجه مشكلة تقنية بسيطة. سيتواصل معك أحد موظفينا الآن."
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
    
    def generate_context_string(self, retrieved_data):
        if not retrieved_data:
            return "لا توجد معلومات محددة."
        item = retrieved_data[0]
        return f"السؤال: {item.get('question', '')}\nالإجابة: {item.get('answer', '')}"