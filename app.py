# enhanced_app_optimized_v3_with_memory.py
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
CUSTOMERS_JSON_PATH = 'customers_data.json' # --- تعديل: إضافة مسار ملف العملاء

app = Flask(__name__)

# --- تعديل: وظيفة تحميل بيانات العملاء ---
def load_customers_data(file_path: str) -> Dict[str, Dict]:
    """تحميل بيانات العملاء من ملف JSON وتحويلها إلى قاموس للوصول السريع."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            customers_list = json.load(f)
        
        # تحويل القائمة إلى قاموس باستخدام رقم الهاتف كمفتاح
        customers_dict = {customer['phone_number']: customer for customer in customers_list}
        print(f"✅ تم تحميل بيانات {len(customers_dict)} عميل بنجاح.")
        return customers_dict
    except FileNotFoundError:
        print(f"⚠️ تحذير: ملف بيانات العملاء '{file_path}' غير موجود. سيعمل البوت بدون ذاكرة العملاء.")
        return {}
    except Exception as e:
        print(f"❌ خطأ في تحميل بيانات العملاء: {e}")
        return {}

# --- 🚀 نظام ذاكرة محادثات مطور جداً ---
class ConversationManager:
    def __init__(self, customers_data: Dict[str, Dict]):
        self.conversations: Dict[str, Dict] = {}
        self.customers_data = customers_data # --- تعديل: تخزين بيانات العملاء
        self.lock = threading.Lock()
        
    def get_or_create_conversation(self, phone_number: str) -> Dict:
        """الحصول على محادثة حالية أو إنشاء واحدة جديدة مع بيانات العميل."""
        with self.lock:
            if phone_number not in self.conversations:
                # إنشاء محادثة جديدة
                self.conversations[phone_number] = {
                    'first_message_time': datetime.now(),
                    'last_activity': datetime.now(),
                    'history': [], # --- تعديل: لتخزين سجل المحادثة
                    'customer_data': self.customers_data.get(phone_number) # --- تعديل: جلب بيانات العميل
                }
                if self.conversations[phone_number]['customer_data']:
                    print(f"👤 تم التعرف على العميل: {self.conversations[phone_number]['customer_data'].get('name', phone_number)}")
            
            self.conversations[phone_number]['last_activity'] = datetime.now()
            return self.conversations[phone_number]

    def add_message_to_history(self, phone_number: str, role: str, content: str):
        """إضافة رسالة إلى سجل المحادثة."""
        with self.lock:
            conversation = self.get_or_create_conversation(phone_number)
            conversation['history'].append({'role': role, 'content': content})
            # --- تعديل: الحفاظ على السجل بحجم معقول (آخر 10 رسائل)
            conversation['history'] = conversation['history'][-10:]

    def is_first_message(self, phone_number: str) -> bool:
        """للترحيب الأولي فقط"""
        with self.lock:
            return phone_number not in self.conversations or not self.conversations[phone_number]['history']

# --- (بقية الكلاسات مثل QuickResponseSystem و EnhancedRetriever و WhatsAppHandler تبقى كما هي بدون تغيير) ---
class QuickResponseSystem:
    def __init__(self):
        # ردود الترحيب السريعة
        self.welcome_patterns = {
            'سلام': True, 'السلام': True, 'عليكم': True,
            'مرحبا': True, 'مرحبتين': True, 'هلا': True, 'اهلا': True,
            'كيفك': True, 'كيف الحال': True, 'شلونك': True, 'وش اخبارك': True,
            'صباح': True, 'مساء': True, 'اهلين': True, 'حياك': True, 'حياكم': True,
            'يعطيك العافية': True, 'تسلم': True, 'الله يعطيك العافية': True,
            'هاي': True, 'هالو': True, 'hello': True, 'hi': True,
            'good morning': True, 'good evening': True,
            'ايش اخبارك': True, 'وش مسوي': True, 'كيف اموركم': True
        }
        
        # 🙏 كلمات وعبارات الشكر باللهجة السعودية - جديد!
        self.thanks_patterns = {
            'شكرا': True, 'شكراً': True, 'شكر': True, 'مشكور': True, 'مشكوره': True,
            'تسلم': True, 'تسلمي': True, 'تسلمين': True, 'تسلمون': True,
            'يعطيك': True, 'يعطيكم': True, 'الله يعطيك': True, 'الله يعطيكم': True,
            'العافية': True, 'يعطيك العافية': True, 'الله يعطيك العافية': True,
            'جزاك': True, 'جزاكم': True, 'جزاك الله': True, 'جزاكم الله': True,
            'خيراً': True, 'خير': True, 'جزاك الله خير': True, 'جزاك الله خيرا': True,
            'ماقصرت': True, 'ماقصرتوا': True, 'ما قصرت': True, 'ما قصرتوا': True,
            'مشكورين': True, 'مشكورات': True, 'thank': True, 'thanks': True,
            'appreciate': True, 'بارك': True, 'بارك الله': True, 'الله يبارك': True,
            'وفقك': True, 'وفقكم': True, 'الله يوفقك': True, 'الله يوفقكم': True,
            'كثر خيرك': True, 'كثر خيركم': True, 'الله يكثر خيرك': True, 
            'خلاص': True, 'كفايه': True, 'كافي': True, 'بس كذا': True,
            'تمام': True, 'زين': True, 'ممتاز': True, 'perfect': True
        }
        
        # جمل كاملة للشكر باللهجة السعودية
        self.thanks_phrases = [
            'شكرا لك', 'شكرا ليك', 'شكراً لك', 'شكراً ليك',
            'الله يعطيك العافية', 'يعطيك العافية', 'الله يعطيكم العافية',
            'تسلم إيدك', 'تسلم ايدك', 'تسلمي إيدك', 'تسلمي ايدك',
            'جزاك الله خير', 'جزاك الله خيرا', 'جزاك الله خيراً',
            'الله يجزاك خير', 'الله يجزيك خير', 'الله يجزيكم خير',
            'ما قصرت', 'ماقصرت', 'ما قصرتوا', 'ماقصرتوا',
            'كثر خيرك', 'الله يكثر خيرك', 'كثر خيركم',
            'الله يوفقك', 'الله يوفقكم', 'وفقك الله', 'وفقكم الله',
            'بارك الله فيك', 'بارك الله فيكم', 'الله يبارك فيك',
            'شكرا على المساعدة', 'شكرا على المساعده', 'شكراً على المساعدة',
            'thanks a lot', 'thank you', 'thank u', 'appreciate it',
            'مشكورين والله', 'مشكور والله', 'تسلم والله'
        ]
        
        # كلمات دلالية للأسعار - محسّنة
        self.price_keywords = [
            'سعر', 'اسعار', 'أسعار', 'تكلفة', 'كلفة', 'تكاليف','اسعاركم',
            'فلوس', 'ريال', 'مبلغ', 'رسوم','عروضكم',
            'عرض', 'عروض', 'باقة', 'باقات', 'خصم', 'خصومات','خصوماتكم',
            'ثمن', 'مصاريف', 'مصروف', 'دفع', 'يكلف', 'تكلف', 'بكام'
        ]
        
        # جمل كاملة للأسعار
        self.price_phrases = [
            'كم السعر', 'ايش السعر', 'وش السعر', 'كم التكلفة','ايش اسعاركم','ايش اسعاركم',
            'وش التكلفة', 'كم الكلفة', 'ايش الكلفة', 'وش الكلفة',
            'كم التكاليف', 'ايش التكاليف', 'وش التكاليف',   
        
            'كم الثمن', 'ابغى اعرف السعر',
            'عايز اعرف السعر', 'ايه الاسعار', 'وش الاسعار',
            'رسوم الاستقدام', 'اسعار الاستقدام', 'تكلفة الاستقدام',
            
        ]
    
    def is_greeting_message(self, message: str) -> bool:
        """فحص سريع للرسائل الترحيبية"""
        if not message or len(message.strip()) == 0:
            return False
            
        message_clean = message.lower().strip()
        words = message_clean.split()
        
        # إذا الرسالة قصيرة وتحتوي على ترحيب
        if len(words) <= 6:
            for word in words:
                clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
                if clean_word in self.welcome_patterns:
                    return True
                    
        return False
    
    def is_thanks_message(self, message: str) -> bool:
        """🙏 فحص سريع ودقيق لرسائل الشكر باللهجة السعودية - جديد!"""
        if not message or len(message.strip()) == 0:
            return False
            
        message_clean = message.lower().strip()
        
        # فحص الجمل الكاملة أولاً
        for phrase in self.thanks_phrases:
            if phrase in message_clean:
                print(f"🙏 مطابقة جملة شكر كاملة: {phrase}")
                return True
        
        # فحص الكلمات المفردة
        words = message_clean.split()
        thanks_word_count = 0
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            
            if clean_word in self.thanks_patterns:
                thanks_word_count += 1
                print(f"🙏 كلمة شكر: {clean_word}")
        
        # إذا وجد كلمة واحدة أو أكثر تدل على الشكر
        return thanks_word_count >= 1
    
    def is_price_inquiry(self, message: str) -> bool:
        """فحص سريع ودقيق للسؤال عن الأسعار"""
        if not message or len(message.strip()) == 0:
            return False
            
        message_clean = message.lower().strip()
        
        # فحص الجمل الكاملة أولاً
        for phrase in self.price_phrases:
            if phrase in message_clean:
                print(f"🎯 مطابقة جملة كاملة: {phrase}")
                return True
        
        # فحص الكلمات المفردة
        words = message_clean.split()
        price_word_count = 0
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            
            if clean_word in self.price_keywords:
                price_word_count += 1
                print(f"🎯 كلمة سعر: {clean_word}")
        
        # إذا وجد كلمة واحدة أو أكثر تدل على السعر
        return price_word_count >= 1
    
    def get_welcome_response(self) -> str:
        """رد الترحيب السريع"""
        return """أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟

نحن هنا لخدمتك ومساعدتك في جميع احتياجاتك من العمالة المنزلية المدربة والمؤهلة.

كيف يمكنني مساعدتك اليوم؟ 😊"""

    def get_thanks_response(self) -> str:
        """🙏 رد الشكر السريع باللهجة السعودية - جديد!"""
        responses = [
            """العفو عميلنا العزيز 🌟

الله يعطيك العافية.. نحن في خدمتك دائماً في مكتب الركائز البشرية

هل تحتاج أي مساعدة أخرى؟ 😊""",
            
            """أهلاً وسهلاً.. هذا واجبنا 🤝

نحن سعداء بخدمتك في مكتب الركائز البشرية للاستقدام

الله يوفقك.. ولا تتردد في التواصل معنا متى شئت! 💙""",
            
            """حياك الله.. ما قصرنا شي 🌟

خدمتك شرف لنا في مكتب الركائز البشرية

تواصل معنا في أي وقت.. نحن هنا لخدمتك! 📞"""
        ]
        
        import random
        return random.choice(responses)

    def get_price_response(self) -> tuple:
        """رد الأسعار المختصر مع الصورة"""
        text_response = """إليك عروضنا الحالية للعمالة المنزلية المدربة 💼

🎉 عرض خاص بمناسبة اليوم الوطني السعودي 95

للاستفسار والحجز اتصل بنا:
📞 0556914447 / 0506207444 / 0537914445"""
        

        
        # ضع رابط صورتك هنا بعد رفعها
        image_url = "https://i.imghippo.com/files/La2232xjc.jpg"  # استبدل برابط صورتك
        
        return text_response, image_url
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
        self.high_confidence_threshold = 0.75  # خفضت العتبة للاستجابة الأسرع
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 3) -> tuple:
        """استرجاع سريع للمطابقات"""
        if not self.model or not self.collection:
            return [], 0.0
        
        try:
            # بحث سريع
            query_embedding = self.model.encode([f"query: {user_query}"], normalize_embeddings=True)
            results = self.collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=min(top_k, 5)  # أقل عدد للسرعة
            )
            
            if not results.get('metadatas') or not results['metadatas'][0]:
                return [], 0.0
            
            # حساب الثقة
            best_score = 1 - results['distances'][0][0] if 'distances' in results else 0
            results_data = results['metadatas'][0]
            
            return results_data, best_score
            
        except Exception as e:
            print(f"❌ خطأ في البحث: {e}")
            return [], 0.0
class WhatsAppHandler:
    def __init__(self, quick_system):
        self.processing_messages = set()
        self.rate_limit = {}
        self.quick_system = quick_system
    
    def is_duplicate_message(self, message_id: str) -> bool:
        """فحص الرسائل المكررة"""
        if message_id in self.processing_messages:
            return True
        self.processing_messages.add(message_id)
        
        # إزالة المعالجة بعد 30 ثانية
        threading.Timer(30.0, lambda: self.processing_messages.discard(message_id)).start()
        return False
    
    def check_rate_limit(self, phone_number: str) -> bool:
        """فحص معدل سريع - رسالة كل 0.5 ثانية"""
        now = time.time()
        if phone_number in self.rate_limit:
            if now - self.rate_limit[phone_number] < 0.5:  # نصف ثانية فقط
                return True
        self.rate_limit[phone_number] = now
        return False
    
    def send_message(self, to_number: str, message: str) -> bool:
        """إرسال رسالة سريع"""
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            print("❌ معلومات WhatsApp غير مكتملة")
            return False
            
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        message = message.strip()
        if len(message) > 900:  # حد أقل للسرعة
            message = message[:850] + "...\n\nللمزيد: 📞 0556914447"
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "text": {"body": message}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=5)  # timeout أقل
            response.raise_for_status()
            print(f"✅ تم الإرسال إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ WhatsApp: {e}")
            return False
    
    def send_image_with_text(self, to_number: str, message: str, image_url: str) -> bool:
        """إرسال صورة مع رسالة"""
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            return False
            
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # رسالة مختصرة للـ caption
        if len(message) > 800:
            message = message[:750] + "...\n📞 للمزيد: 0556914447"
        
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
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=8)
            response.raise_for_status()
            print(f"✅ تم إرسال الصورة إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في الصورة: {e}")
            # رد احتياطي بالنص فقط
            return self.send_message(to_number, f"{message}\n\n📞 اتصل للحصول على صورة الأسعار: 0556914447")


# --- 🤖 نظام الردود الذكي المطور (مع ذاكرة) ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever, quick_system):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
    
    # --- تعديل: تم تحديث الدالة لتقبل بيانات المحادثة الكاملة ---
    def generate_response(self, user_message: str, conversation_data: Dict) -> tuple:
        """
        إنتاج الرد السريع مع الأخذ في الاعتبار ذاكرة العميل وسياق المحادثة.
        """
        phone_number = conversation_data.get('customer_data', {}).get('phone_number', 'غير معروف')
        is_first = not conversation_data['history'] # هل السجل فارغ؟
        
        print(f"🔍 معالجة: '{user_message}' من {phone_number}")
        
        # 1. الردود السريعة (ترحيب، شكر، أسعار) لها الأولوية
        if is_first and self.quick_system.is_greeting_message(user_message):
            return self.quick_system.get_welcome_response(), False, None
        if self.quick_system.is_thanks_message(user_message):
            return self.quick_system.get_thanks_response(), False, None
        if self.quick_system.is_price_inquiry(user_message):
            text, url = self.quick_system.get_price_response()
            return text, True, url
        
        # 2. البحث في قاعدة المعرفة العامة
        retrieved_data, confidence_score = self.retriever.retrieve_best_matches(user_message) if self.retriever else ([], 0)
        
        # 3. استخدام OpenAI مع الذاكرة والسياق
        if not self.openai_client:
            # رد احتياطي بدون OpenAI
            return "أهلاً بك عميلنا العزيز في مكتب الركائز البشرية! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة.", False, None

        try:
            customer_info = self.format_customer_data(conversation_data.get('customer_data'))
            conversation_history = conversation_data.get('history', [])
            general_context = self.generate_context_string(retrieved_data)

            # --- تعديل: هذا هو الـ Prompt الذكي الجديد ---
            system_prompt = f"""أنت مساعد شخصي ذكي لمكتب "الركائز البشرية للاستقدام". مهمتك هي خدمة العملاء بشكل احترافي وودي.

**قواعد صارمة:**
1.  استخدم اللهجة السعودية في كل ردودك (مثال: "حياك الله"، "أبشر"، "وش أقدر أخدمك فيه؟").
2.  خاطب العميل باسمه إذا كان معروفاً (مثال: "أهلاً أستاذ أحمد").
3.  استفد من "معلومات العميل" و "سجل المحادثة" لفهم طلباته السابقة وسياق الحوار الحالي.
4.  إذا سأل العميل سؤالاً عاماً، استخدم "المعلومات من قاعدة المعرفة" للإجابة.
5.  كن مختصراً ومباشراً. لا تخترع معلومات غير موجودة.
6.  اختتم دائماً بسؤال مفتوح مثل "هل فيه شي ثاني أقدر أساعدك فيه؟" أو "تحت أمرك في أي وقت".

---
**معلومات العميل الحالية:**
{customer_info}
---
**سجل المحادثة (آخر 5 رسائل):**
{conversation_history}
---
**معلومات إضافية من قاعدة المعرفة قد تكون مفيدة:**
{general_context}
---
"""
            messages_for_api = [
                {"role": "system", "content": system_prompt},
            ]
            # إضافة سجل المحادثة السابق
            messages_for_api.extend(conversation_history)
            # إضافة رسالة المستخدم الجديدة
            messages_for_api.append({"role": "user", "content": user_message})

            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages_for_api,
                max_tokens=500,
                temperature=0.2
            )
            
            return response.choices[0].message.content.strip(), False, None

        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            return "عفواً، حدث خطأ تقني. فريقنا يعمل على إصلاحه. للمساعدة العاجلة، الرجاء الاتصال على 0556914447", False, None

    def format_customer_data(self, customer_data: Optional[Dict]) -> str:
        """تنسيق بيانات العميل بشكل نصي للـ prompt."""
        if not customer_data:
            return "عميل جديد أو غير مسجل."
        
        info = [
            f"- الاسم: {customer_data.get('name', 'غير محدد')}",
            f"- الجنس: {customer_data.get('gender', 'غير محدد')}",
            f"- الجنسية المفضلة: {customer_data.get('preferred_nationality', 'غير محدد')}"
        ]
        
        if customer_data.get('past_services'):
            info.append("- خدمات سابقة: نعم، لديه تاريخ معنا.")
        if customer_data.get('current_requests'):
            info.append("- طلبات حالية: نعم، لديه طلبات قيد التنفيذ.")
            
        return "\n".join(info)

    def generate_context_string(self, retrieved_data):
        if not retrieved_data:
            return "لا توجد معلومات محددة من قاعدة المعرفة."
        item = retrieved_data[0]
        return f"سؤال مشابه: {item['question']}\nإجابة مقترحة: {item['answer']}"


# --- 🎯 تهيئة النظام ---

# --- تعديل: تحميل بيانات العملاء عند البدء ---
customers_database = load_customers_data(CUSTOMERS_JSON_PATH)
conversation_manager = ConversationManager(customers_database)
quick_system = QuickResponseSystem()
whatsapp_handler = WhatsAppHandler(quick_system)

# ... (بقية تهيئة النظام تبقى كما هي)
# تحميل مكونات الذكاء الاصطناعي
openai_client = None
enhanced_retriever = None
response_generator = None

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI جاهز")

# تحميل ChromaDB (اختياري - للسرعة)
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


# --- تعديل: تحديث وظيفة المعالجة الرئيسية ---
def process_user_message_fast(phone_number: str, user_message: str):
    """معالجة رسائل المستخدم مع الذاكرة والسياق."""
    start_time = time.time()
    
    try:
        # 1. إدارة المحادثة (جلب بيانات العميل والسجل)
        conversation = conversation_manager.get_or_create_conversation(phone_number)
        
        # 2. إضافة رسالة المستخدم الحالية إلى السجل
        conversation_manager.add_message_to_history(phone_number, 'user', user_message)

        # 3. توليد الرد الذكي
        if response_generator:
            bot_response, should_send_image, image_url = response_generator.generate_response(
                user_message, conversation
            )
        else:
            # رد احتياطي بسيط
            bot_response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك متخصص قريباً."
            should_send_image, image_url = False, None
        
        # 4. إرسال الرد
        if should_send_image and image_url:
            whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
        else:
            whatsapp_handler.send_message(phone_number, bot_response)

        # 5. إضافة رد البوت إلى السجل للمحادثات المستقبلية
        conversation_manager.add_message_to_history(phone_number, 'assistant', bot_response)

        response_time = time.time() - start_time
        print(f"✅ استجابة في {response_time:.2f}s لـ {phone_number} (مع ذاكرة)")

    except Exception as e:
        print(f"❌ خطأ فادح في المعالجة: {e}")
        whatsapp_handler.send_message(phone_number, "عذراً، حدث خطأ تقني. 📞 0556914447")

# --- 🚀 المسارات الرئيسية (تبقى كما هي) ---
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
        
        if not data or 'entry' not in data:
            return 'OK', 200
        
        # معالجة سريعة للرسائل
        for entry in data['entry']:
            for change in entry.get('changes', []):
                value = change.get('value', {})
                
                if 'messages' not in value:
                    continue
                
                for message_data in value['messages']:
                    if message_data.get('type') != 'text':
                        continue
                    
                    message_id = message_data.get('id', '')
                    phone_number = message_data.get('from', '')
                    user_message = message_data.get('text', {}).get('body', '').strip()
                    
                    if not phone_number or not user_message:
                        continue
                    
                    if whatsapp_handler.is_duplicate_message(message_id):
                        print(f"⚠️ رسالة مكررة: {message_id}")
                        continue
                    
                    if whatsapp_handler.check_rate_limit(phone_number):
                        print(f"⚠️ سرعة عالية من: {phone_number}")
                        continue
                    
                    # معالجة فورية في thread منفصل
                    thread = threading.Thread(
                        target=process_user_message_fast,
                        args=(phone_number, user_message),
                        daemon=True
                    )
                    thread.start()
        
        return 'OK', 200

# ... (بقية المسارات مثل status و test-quick تبقى كما هي) ...
@app.route('/')
def status():
    """صفحة حالة سريعة"""
    active_conversations = len(conversation_manager.conversations)
    
    return f"""
    <html><head><title>بوت الركائز - سريع مع الشكر</title>
    <style>body{{font-family:Arial;margin:40px;background:#f0f8ff;}}
    .box{{background:white;padding:20px;border-radius:10px;margin:10px 0;}}
    .green{{color:#28a745;}} .red{{color:#dc3545;}} .blue{{color:#007bff;}}
    </style></head><body>
    
    <div class="box">
    <h1>🚀 مكتب الركائز - بوت سريع مع ردود الشكر</h1>
    </div>
    
    <div class="box">
    <h2>📊 الحالة:</h2>
    <p class="{'green' if openai_client else 'red'}">{'✅' if openai_client else '❌'} OpenAI API</p>
    <p class="{'green' if enhanced_retriever else 'red'}">{'✅' if enhanced_retriever else '❌'} قاعدة البيانات</p>
    <p class="green">⚡ الردود السريعة - نشط</p>
    <p class="blue">🙏 <strong>جديد!</strong> ردود الشكر السريعة - نشط</p>
    <p class="green">📱 المحادثات النشطة: {active_conversations}</p>
    </div>
    
    <div class="box">
    <h2>⚡ المميزات:</h2>
    <ul>
    <li>✅ ردود ترحيب فورية (< 0.1s)</li>
    <li class="blue">✅ <strong>جديد!</strong> ردود شكر فورية باللهجة السعودية</li>
    <li>✅ كشف أسعار تلقائي مع صورة</li>
    <li>✅ معدل استجابة 0.5 ثانية</li>
    <li>✅ ردود احتياطية ذكية</li>
    </ul>
    </div>
    
    <div class="box">
    <h2>🙏 أمثلة رسائل الشكر المدعومة:</h2>
    <ul>
    <li><strong>شكراً ليك</strong> - شكرا لك - الله يعطيك العافية</li>
    <li><strong>تسلم إيدك</strong> - ما قصرت - جزاك الله خير</li>
    <li><strong>مشكور</strong> - الله يوفقك - كثر خيرك</li>
    <li><strong>Thank you</strong> - Thanks - Appreciate it</li>
    <li><strong>يعطيك العافية</strong> - بارك الله فيك</li>
    </ul>
    </div>
    
    <div class="box">
    <h2>🔗 مواقع رفع الصور المجانية:</h2>
    <ul>
    <li><strong>imgur.com</strong> - الأفضل والأسرع</li>
    <li><strong>postimg.cc</strong> - سريع وموثوق</li>
    <li><strong>imgbb.com</strong> - جودة عالية</li>
    <li><strong>i.ibb.co</strong> - بسيط وسهل</li>
    </ul>
    <p><strong>ملاحظة:</strong> بعد رفع الصورة، استبدل الرابط في الكود</p>
    </div>
    
    <p class="green"><strong>النظام يعمل بأقصى سرعة مع ردود الشكر الذكية! 🚀🙏</strong></p>
    </body></html>"""

@app.route('/test-quick/<message>')
def test_quick_response(message):
    """اختبار سريع للردود"""
    start_time = time.time()
    
    is_greeting = quick_system.is_greeting_message(message)
    is_thanks = quick_system.is_thanks_message(message)  # 🙏 اختبار الشكر - جديد!
    is_price = quick_system.is_price_inquiry(message)
    
    processing_time = time.time() - start_time
    
    result = {
        "الرسالة": message,
        "ترحيب؟": is_greeting,
        "شكر؟": is_thanks,  # 🙏 جديد!
        "سؤال أسعار؟": is_price,
        "وقت المعالجة": f"{processing_time:.4f} ثانية",
        "نوع الرد": "سريع" if (is_greeting or is_thanks or is_price) else "عادي"
    }
    
    if is_greeting:
        result["الرد"] = quick_system.get_welcome_response()
    elif is_thanks:  # 🙏 رد الشكر - جديد!
        result["الرد"] = quick_system.get_thanks_response()
    elif is_price:
        text, image = quick_system.get_price_response()
        result["الرد"] = text
        result["صورة"] = image
    
    return jsonify(result, ensure_ascii=False)

# مسار جديد لاختبار ردود الشكر فقط 🙏
@app.route('/test-thanks/<message>')
def test_thanks_only(message):
    """اختبار خاص لردود الشكر فقط"""
    start_time = time.time()
    
    is_thanks = quick_system.is_thanks_message(message)
    processing_time = time.time() - start_time
    
    result = {
        "الرسالة": message,
        "هل هي رسالة شكر؟": is_thanks,
        "وقت المعالجة": f"{processing_time:.4f} ثانية"
    }
    
    if is_thanks:
        result["الرد"] = quick_system.get_thanks_response()
        result["نوع الرد"] = "شكر فوري 🙏"
    else:
        result["نوع الرد"] = "ليست رسالة شكر"
    
    return jsonify(result, ensure_ascii=False)

if __name__ == '__main__':
    print("🚀 تشغيل بوت الركائز المطور (مع ذاكرة وسياق)...")
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))