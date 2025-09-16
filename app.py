# enhanced_app_with_memory.py
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

# --- 🧠 نظام Memory العملاء الذكي - جديد! ---
class CustomerMemoryManager:
    def __init__(self):
        self.customer_cache = {}  # Cache للعملاء النشطين
        self.conversation_history = {}  # تاريخ المحادثات
        self.memory_lock = threading.Lock()
        self.customers_data = self.load_customers_data()
        print(f"📊 تم تحميل {len(self.customers_data)} عميل من قاعدة البيانات")
    
    def load_customers_data(self) -> dict:
        """تحميل بيانات العملاء من الملف"""
        try:
            with open('customers_data.json', 'r', encoding='utf-8') as file:
                customers_list = json.load(file)
                # تحويل القائمة إلى dict باستخدام رقم الهاتف كمفتاح
                customers_dict = {}
                for customer in customers_list:
                    phone = customer.get('phone_number', '')
                    if phone:
                        customers_dict[phone] = customer
                return customers_dict
        except FileNotFoundError:
            print("⚠️ ملف بيانات العملاء غير موجود")
            return {}
        except Exception as e:
            print(f"❌ خطأ في تحميل بيانات العملاء: {e}")
            return {}
    
    def get_customer_info(self, phone_number: str) -> Optional[dict]:
        """جلب معلومات العميل من الذاكرة أو قاعدة البيانات"""
        with self.memory_lock:
            # البحث في الـ cache أولاً
            if phone_number in self.customer_cache:
                print(f"🎯 العميل موجود في الذاكرة: {phone_number}")
                return self.customer_cache[phone_number]
            
            # البحث في قاعدة البيانات
            if phone_number in self.customers_data:
                customer_data = self.customers_data[phone_number].copy()
                # إضافة العميل للـ cache
                self.customer_cache[phone_number] = customer_data
                print(f"✅ تم تحميل العميل للذاكرة: {customer_data.get('name', 'غير معروف')}")
                return customer_data
            
            print(f"🆕 عميل جديد: {phone_number}")
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
            
            # الاحتفاظ بآخر 10 رسائل فقط لكل عميل (توفير الذاكرة)
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
            return ""
        
        name = customer_data.get('name', 'عميل كريم')
        gender = customer_data.get('gender', '')
        preferred_nationality = customer_data.get('preferred_nationality', '')
        past_services = customer_data.get('past_services', [])
        current_requests = customer_data.get('current_requests', [])
        preferences = customer_data.get('preferences', '')
        
        summary = f"العميل: {name}"
        
        if gender == 'ذكر':
            summary += " (أخونا الكريم)"
        elif gender == 'أنثى':
            summary += " (أختنا الكريمة)"
        
        # الخدمات السابقة
        if past_services:
            summary += f"\n🏆 له تعامل سابق معنا - عدد {len(past_services)} خدمة"
            latest_service = past_services[-1]  # آخر خدمة
            summary += f"\n📝 آخر خدمة: {latest_service.get('job_title', '')} - {latest_service.get('worker_name', '')} ({latest_service.get('nationality', '')})"
        
        # الطلبات الحالية
        if current_requests:
            current_req = current_requests[0]  # أول طلب حالي
            summary += f"\n⏳ طلب حالي: {current_req.get('type', '')} - {current_req.get('status', '')}"
            if current_req.get('estimated_delivery'):
                summary += f" - متوقع: {current_req.get('estimated_delivery', '')}"
        
        # التفضيلات
        if preferred_nationality:
            summary += f"\n🌍 يفضل: {preferred_nationality}"
        
        if preferences:
            summary += f"\n💡 ملاحظات: {preferences[:100]}..."
        
        return summary
    
    def cleanup_old_cache(self):
        """تنظيف الذاكرة من العملاء القدامى"""
        # هنحتفظ بـ 50 عميل فقط في الـ cache
        if len(self.customer_cache) > 50:
            # نحذف النصف الأول (oldest)
            keys_to_remove = list(self.customer_cache.keys())[:25]
            for key in keys_to_remove:
                del self.customer_cache[key]
            print("🧹 تنظيف ذاكرة العملاء")

# --- 🚀 نظام ذاكرة محادثات محسّن ---
class ConversationManager:
    def __init__(self, customer_memory):
        self.conversations = {}
        self.message_lock = threading.Lock()
        self.cleanup_interval = 3600
        self.customer_memory = customer_memory
        
    def is_first_message(self, phone_number: str) -> bool:
        with self.message_lock:
            return phone_number not in self.conversations
    
    def register_conversation(self, phone_number: str):
        with self.message_lock:
            # جلب معلومات العميل عند بداية المحادثة
            customer_info = self.customer_memory.get_customer_info(phone_number)
            
            self.conversations[phone_number] = {
                'first_message_time': datetime.now(),
                'last_activity': datetime.now(),
                'message_count': 1,
                'is_existing_customer': customer_info is not None,
                'customer_name': customer_info.get('name', '') if customer_info else ''
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
        # ردود الترحيب السريعة
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
        
        # 🙏 كلمات وعبارات الشكر بالهجة السعودية
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
        
        # جمل كاملة للشكر بالهجة السعودية
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
        """🙏 فحص سريع ودقيق لرسائل الشكر بالهجة السعودية"""
        if not message or len(message.strip()) == 0:
            return False
            
        message_clean = message.lower().strip()
        
        # فحص الجمل الكاملة أولاً
        for phrase in self.thanks_phrases:
            if phrase in message_clean:
                return True
        
        # فحص الكلمات المفردة
        words = message_clean.split()
        thanks_word_count = 0
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            
            if clean_word in self.thanks_patterns:
                thanks_word_count += 1
        
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
                return True
        
        # فحص الكلمات المفردة
        words = message_clean.split()
        price_word_count = 0
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            
            if clean_word in self.price_keywords:
                price_word_count += 1
        
        # إذا وجد كلمة واحدة أو أكثر تدل على السعر
        return price_word_count >= 1
    
    def get_welcome_response(self, customer_name: str = None) -> str:
        """رد الترحيب السريع (مع التخصيص للعملاء المسجلين)"""
        if customer_name:
            return f"""أهلاً وسهلاً أخونا {customer_name} الكريم 🌟

حياك الله مرة ثانية في مكتب الركائز البشرية للاستقدام

كيف يمكنني مساعدتك اليوم؟ 😊"""
        
        return """أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟

نحن هنا لخدمتك ومساعدتك في جميع احتياجاتك من العمالة المنزلية المدربة والمؤهلة.

كيف يمكنني مساعدتك اليوم؟ 😊"""

    def get_thanks_response(self, customer_name: str = None) -> str:
        """🙏 رد الشكر السريع بالهجة السعودية (مع التخصيص)"""
        if customer_name:
            responses = [
                f"""العفو أخونا {customer_name} الكريم 🌟

الله يعطيك العافية.. نحن في خدمتك دائماً في مكتب الركائز البشرية

هل تحتاج أي مساعدة أخرى؟ 😊""",
                
                f"""أهلاً وسهلاً أخونا {customer_name}.. هذا واجبنا 🤝

نحن سعداء بخدمتك في مكتب الركائز البشرية للاستقدام

الله يوفقك.. ولا تتردد في التواصل معنا متى شئت! 💙""",
                
                f"""حياك الله أخونا {customer_name}.. ما قصرنا شي 🌟

خدمتك شرف لنا في مكتب الركائز البشرية

تواصل معنا في أي وقت.. نحن هنا لخدمتك! 📞"""
            ]
        else:
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

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
        self.high_confidence_threshold = 0.75
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 3) -> tuple:
        """استرجاع سريع للمطابقات"""
        if not self.model or not self.collection:
            return [], 0.0
        
        try:
            # بحث سريع
            query_embedding = self.model.encode([f"query: {user_query}"], normalize_embeddings=True)
            results = self.collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=min(top_k, 5)
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

# --- 🤖 نظام الردود الذكي مع الذاكرة الشخصية ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever, quick_system, customer_memory):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
        self.customer_memory = customer_memory
    
    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> tuple:
        """إنتاج الرد الذكي مع الذاكرة الشخصية"""
        
        print(f"🔍 معالجة: '{user_message}' من {phone_number}")
        
        # جلب معلومات العميل من الذاكرة
        customer_info = self.customer_memory.get_customer_info(phone_number)
        customer_name = customer_info.get('name', '') if customer_info else None
        
        # 1. أولوية عليا للترحيب (مع التخصيص)
        if self.quick_system.is_greeting_message(user_message):
            print(f"⚡ رد ترحيب فوري مخصص")
            response = self.quick_system.get_welcome_response(customer_name)
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        # 2. أولوية عليا للشكر (مع التخصيص) 🙏
        if self.quick_system.is_thanks_message(user_message):
            print(f"🙏 رد شكر فوري مخصص")
            response = self.quick_system.get_thanks_response(customer_name)
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        # 3. أولوية عليا للأسعار
        if self.quick_system.is_price_inquiry(user_message):
            print(f"💰 طلب أسعار مكتشف")
            text_response, image_url = self.quick_system.get_price_response()
            self.customer_memory.add_conversation_message(phone_number, user_message, text_response)
            return text_response, True, image_url
        
        # 4. الردود العادية (ذكية مع الذاكرة)
        print(f"🤔 معالجة عادية مع ذاكرة شخصية")
        
        # بحث سريع في قاعدة البيانات
        retrieved_data, confidence_score = self.retriever.retrieve_best_matches(user_message) if self.retriever else ([], 0)
        
        # إذا لم يكن هناك OpenAI
        if not self.openai_client:
            if retrieved_data:
                response = f"بناءً على معلوماتنا:\n\n{retrieved_data[0]['answer']}\n\nهل يمكنني مساعدتك في شيء آخر؟"
            else:
                if customer_name:
                    response = f"أهلاً بك مرة ثانية أخونا {customer_name} في مكتب الركائز البشرية! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة.\n\nهل تريد معرفة أسعارنا الحالية؟"
                else:
                    response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة.\n\nهل تريد معرفة أسعارنا الحالية؟"
            
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
        
        try:
            # إنشاء رد ذكي مع الذاكرة الشخصية
            context = self.generate_context_string(retrieved_data)
            conversation_context = self.customer_memory.get_conversation_context(phone_number)
            customer_summary = self.customer_memory.create_customer_summary(customer_info)
            
            # تحديد نوع الترحيب حسب العميل
            if is_first and customer_name:
                greeting = f"أهلاً وسهلاً أخونا {customer_name} الكريم مرة ثانية في مكتب الركائز البشرية للاستقدام! 🌟\n\n"
            elif is_first:
                greeting = "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام! 🌟\n\n"
            else:
                greeting = ""
                
            system_prompt = f"""{greeting}أنت مساعد ذكي لمكتب الركائز البشرية للاستقدام.

معلومات العميل:
{customer_summary}

آخر محادثات:
{conversation_context}

أجب بشكل مختصر وودود من المعلومات المتوفرة فقط.
استخدم عبارات: عميلنا الكريم، حياك الله، يسعدنا خدمتك.
إذا كان العميل له تعامل سابق، أشر إليه بلطف.
اختتم بسؤال لتشجيع الحوار.

السؤال: {user_message}
المعلومات: {context}"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=700,
                temperature=0.1
            )
            
            bot_response = response.choices[0].message.content.strip()
            
            # إضافة المحادثة للذاكرة
            self.customer_memory.add_conversation_message(phone_number, user_message, bot_response)
            
            return bot_response, False, None
            
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            # رد احتياطي سريع مع التخصيص
            if retrieved_data:
                if customer_name:
                    response = f"عميلنا الكريم أخونا {customer_name}، بناءً على خبرتنا:\n\n{retrieved_data[0]['answer']}\n\nللمزيد من المساعدة، اتصل بنا: 📞 0556914447"
                else:
                    response = f"عميلنا العزيز، بناءً على خبرتنا:\n\n{retrieved_data[0]['answer']}\n\nللمزيد من المساعدة، اتصل بنا: 📞 0556914447"
            else:
                if customer_name:
                    response = f"أهلاً أخونا {customer_name}! 🌟 سيتواصل معك أحد متخصصينا قريباً.\n\nهل تريد معرفة عروضنا الحالية؟"
                else:
                    response = "أهلاً بك! 🌟 سيتواصل معك أحد متخصصينا قريباً.\n\nهل تريد معرفة عروضنا الحالية؟"
            
            self.customer_memory.add_conversation_message(phone_number, user_message, response)
            return response, False, None
    
    def generate_context_string(self, retrieved_data):
        """إنشاء سياق مختصر"""
        if not retrieved_data:
            return "لا توجد معلومات محددة."
        
        # أول نتيجة فقط للسرعة
        item = retrieved_data[0]
        return f"السؤال: {item['question']}\nالإجابة: {item['answer']}"

# --- 📱 نظام WhatsApp السريع ---
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
            if now - self.rate_limit[phone_number] < 0.5:
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
        if len(message) > 900:
            message = message[:850] + "...\n\nللمزيد: 📞 0556914447"
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "text": {"body": message}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=5)
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

# --- 🎯 تهيئة النظام الذكي مع الذاكرة ---
customer_memory = CustomerMemoryManager()
conversation_manager = ConversationManager(customer_memory)
quick_system = QuickResponseSystem()
whatsapp_handler = WhatsAppHandler(quick_system)

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
    response_generator = SmartResponseGenerator(openai_client, enhanced_retriever, quick_system, customer_memory)
    
    print(f"✅ النظام جاهز مع الذاكرة الذكية! قاعدة البيانات: {collection.count()} مستند")

except Exception as e:
    print(f"❌ فشل تحميل AI: {e}")
    print("💡 سيعمل بالردود السريعة والذاكرة فقط")
    response_generator = SmartResponseGenerator(openai_client, None, quick_system, customer_memory)

# --- 🚀 المسارات الرئيسية ---
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
                        target=process_user_message_with_memory,
                        args=(phone_number, user_message),
                        daemon=True
                    )
                    thread.start()
        
        return 'OK', 200

def process_user_message_with_memory(phone_number: str, user_message: str):
    """معالجة سريعة للرسائل مع الذاكرة الشخصية"""
    start_time = time.time()
    
    try:
        # إدارة المحادثة مع الذاكرة
        is_first = conversation_manager.is_first_message(phone_number)
        
        if is_first:
            conversation_manager.register_conversation(phone_number)
            print(f"🆕 محادثة جديدة: {phone_number}")
        else:
            conversation_manager.update_activity(phone_number)
        
        # جلب معلومات العميل من الذاكرة
        customer_info = customer_memory.get_customer_info(phone_number)
        if customer_info:
            print(f"👤 عميل مسجل: {customer_info.get('name', 'غير معروف')}")
        
        # توليد الرد الذكي مع الذاكرة
        if response_generator:
            bot_response, should_send_image, image_url = response_generator.generate_response(
                user_message, phone_number, is_first
            )
            
            # إرسال الرد
            if should_send_image and image_url:
                success = whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
            else:
                success = whatsapp_handler.send_message(phone_number, bot_response)
        else:
            # نظام احتياطي أساسي مع الذاكرة
            customer_name = customer_info.get('name', '') if customer_info else None
            
            if quick_system.is_greeting_message(user_message):
                bot_response = quick_system.get_welcome_response(customer_name)
                success = whatsapp_handler.send_message(phone_number, bot_response)
            elif quick_system.is_thanks_message(user_message):
                bot_response = quick_system.get_thanks_response(customer_name)
                success = whatsapp_handler.send_message(phone_number, bot_response)
            elif quick_system.is_price_inquiry(user_message):
                bot_response, image_url = quick_system.get_price_response()
                success = whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
            else:
                if customer_name:
                    bot_response = f"أهلاً أخونا {customer_name} الكريم في مكتب الركائز البشرية! 🌟\nسيتواصل معك متخصص قريباً.\n📞 0556914447"
                else:
                    bot_response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك متخصص قريباً.\n📞 0556914447"
                success = whatsapp_handler.send_message(phone_number, bot_response)
            
            # إضافة للذاكرة حتى في النظام الاحتياطي
            customer_memory.add_conversation_message(phone_number, user_message, bot_response)
        
        # إحصائيات سريعة
        response_time = time.time() - start_time
        customer_status = "عميل مسجل" if customer_info else "عميل جديد"
        print(f"✅ استجابة في {response_time:.2f}s لـ {phone_number} ({customer_status})")
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        whatsapp_handler.send_message(phone_number, "عذراً، حدث خطأ تقني. 📞 0556914447")

@app.route('/')
def status():
    """صفحة حالة سريعة مع إحصائيات الذاكرة"""
    active_conversations = len(conversation_manager.conversations)
    cached_customers = len(customer_memory.customer_cache)
    total_customers = len(customer_memory.customers_data)
    
    return f"""
    <html><head><title>بوت الركائز - نظام الذاكرة الذكي</title>
    <style>body{{font-family:Arial;margin:40px;background:#f0f8ff;}}
    .box{{background:white;padding:20px;border-radius:10px;margin:10px 0;box-shadow:0 4px 8px rgba(0,0,0,0.1);}}
    .green{{color:#28a745;}} .red{{color:#dc3545;}} .blue{{color:#007bff;}} .purple{{color:#6f42c1;}}
    .stat{{background:#e3f2fd;padding:15px;margin:10px 0;border-radius:8px;border-left:4px solid #2196f3;}}
    h1{{color:#1976d2;text-align:center;}}
    </style></head><body>
    
    <div class="box">
    <h1>🧠 مكتب الركائز - بوت ذكي مع نظام الذاكرة الشخصية</h1>
    </div>
    
    <div class="box">
    <h2>📊 الحالة العامة:</h2>
    <p class="{'green' if openai_client else 'red'}">{'✅' if openai_client else '❌'} OpenAI API</p>
    <p class="{'green' if enhanced_retriever else 'red'}">{'✅' if enhanced_retriever else '❌'} قاعدة البيانات</p>
    <p class="green">⚡ الردود السريعة - نشط</p>
    <p class="blue">🙏 ردود الشكر السريعة - نشط</p>
    <p class="purple">🧠 <strong>جديد!</strong> نظام الذاكرة الشخصية - نشط</p>
    </div>
    
    <div class="stat">
    <h2>🧠 إحصائيات الذاكرة الذكية:</h2>
    <ul>
    <li><strong>إجمالي العملاء المسجلين:</strong> {total_customers} عميل</li>
    <li><strong>العملاء النشطين في الذاكرة:</strong> {cached_customers} عميل</li>
    <li><strong>المحادثات النشطة:</strong> {active_conversations} محادثة</li>
    </ul>
    </div>
    
    <div class="box">
    <h2>⚡ المميزات الجديدة:</h2>
    <ul>
    <li>✅ <strong>ذاكرة شخصية للعملاء:</strong> البوت يتذكر اسم العميل وتاريخه</li>
    <li>✅ <strong>ترحيب مخصص:</strong> "أهلاً أخونا أحمد الكريم مرة ثانية"</li>
    <li>✅ <strong>تتبع الخدمات السابقة:</strong> يعرف العمالة السابقة والطلبات الحالية</li>
    <li>✅ <strong>سياق المحادثة:</strong> يتذكر آخر 3 رسائل من كل عميل</li>
    <li>✅ <strong>ردود ذكية مخصصة:</strong> حسب تفضيلات كل عميل</li>
    <li>✅ <strong>كاش ذكي:</strong> سرعة عالية مع توفير الذاكرة</li>
    </ul>
    </div>
    
    <div class="box">
    <h2>👥 أمثلة العملاء المسجلين:</h2>
    <ul>
    <li><strong>أحمد المحمد (966501234567):</strong> له خدمة سابقة - عاملة فلبينية</li>
    <li><strong>فاطمة السالم (966501963427):</strong> عميلة نشطة - لديها طلب حالي</li>
    <li><strong>خالد العتيبي (966531122334):</strong> طلب سائق هندي قيد التجهيز</li>
    <li><strong>ليلى الشهري (966590001111):</strong> عميلة جديدة - تفضل العمالة الإثيوبية</li>
    </ul>
    </div>
    
    <div class="box">
    <h2>🔬 اختبار النظام:</h2>
    <p><strong>جرب الروابط التالية لاختبار الذاكرة:</strong></p>
    <ul>
    <li><a href="/test-customer/966501234567/مرحبا" target="_blank">اختبار ترحيب أحمد المحمد</a></li>
    <li><a href="/test-customer/966501963427/شكرا لك" target="_blank">اختبار شكر فاطمة السالم</a></li>
    <li><a href="/test-customer/966999999999/السلام عليكم" target="_blank">اختبار عميل جديد</a></li>
    </ul>
    </div>
    
    <p class="green"><strong>النظام يعمل بأقصى ذكاء مع ذاكرة شخصية لكل عميل! 🧠🚀</strong></p>
    </body></html>"""

@app.route('/test-customer/<phone_number>/<message>')
def test_customer_memory(phone_number, message):
    """اختبار نظام الذاكرة للعملاء"""
    start_time = time.time()
    
    # جلب معلومات العميل
    customer_info = customer_memory.get_customer_info(phone_number)
    
    # اختبار الردود السريعة
    is_greeting = quick_system.is_greeting_message(message)
    is_thanks = quick_system.is_thanks_message(message)
    is_price = quick_system.is_price_inquiry(message)
    
    processing_time = time.time() - start_time
    
    result = {
        "رقم_الهاتف": phone_number,
        "الرسالة": message,
        "عميل_مسجل": customer_info is not None,
        "اسم_العميل": customer_info.get('name', 'غير مسجل') if customer_info else 'غير مسجل',
        "نوع_الرسالة": {
            "ترحيب": is_greeting,
            "شكر": is_thanks,
            "سؤال_أسعار": is_price
        },
        "وقت_المعالجة": f"{processing_time:.4f} ثانية"
    }
    
    # إضافة الرد المناسب
    if customer_info:
        customer_name = customer_info.get('name', '')
        
        if is_greeting:
            result["الرد"] = quick_system.get_welcome_response(customer_name)
            result["نوع_الرد"] = "ترحيب مخصص"
        elif is_thanks:
            result["الرد"] = quick_system.get_thanks_response(customer_name)
            result["نوع_الرد"] = "شكر مخصص"
        elif is_price:
            text, image = quick_system.get_price_response()
            result["الرد"] = text
            result["صورة"] = image
            result["نوع_الرد"] = "أسعار مع صورة"
        else:
            result["الرد"] = f"أهلاً أخونا {customer_name} الكريم في مكتب الركائز البشرية! 🌟"
            result["نوع_الرد"] = "رد عادي مخصص"
        
        # إضافة ملخص العميل
        result["ملخص_العميل"] = customer_memory.create_customer_summary(customer_info)
    else:
        if is_greeting:
            result["الرد"] = quick_system.get_welcome_response()
            result["نوع_الرد"] = "ترحيب عام"
        elif is_thanks:
            result["الرد"] = quick_system.get_thanks_response()
            result["نوع_الرد"] = "شكر عام"
        elif is_price:
            text, image = quick_system.get_price_response()
            result["الرد"] = text
            result["صورة"] = image
            result["نوع_الرد"] = "أسعار مع صورة"
        else:
            result["الرد"] = "أهلاً بك في مكتب الركائز البشرية! 🌟"
            result["نوع_الرد"] = "رد عادي عام"
        
        result["ملخص_العميل"] = "عميل جديد - غير مسجل في قاعدة البيانات"
    
    return jsonify(result, ensure_ascii=False)

@app.route('/customers-stats')
def customers_stats():
    """إحصائيات مفصلة عن العملاء"""
    stats = {
        "إجمالي_العملاء_المسجلين": len(customer_memory.customers_data),
        "العملاء_النشطين_في_الذاكرة": len(customer_memory.customer_cache),
        "المحادثات_النشطة": len(conversation_manager.conversations),
        "العملاء_المسجلون": []
    }
    
    # إضافة تفاصيل العملاء المسجلين (أول 10 فقط)
    for phone, customer in list(customer_memory.customers_data.items())[:10]:
        stats["العملاء_المسجلون"].append({
            "رقم_الهاتف": phone,
            "الاسم": customer.get('name', 'غير معروف'),
            "الجنس": customer.get('gender', 'غير محدد'),
            "عدد_الخدمات_السابقة": len(customer.get('past_services', [])),
            "عدد_الطلبات_الحالية": len(customer.get('current_requests', [])),
            "الجنسية_المفضلة": customer.get('preferred_nationality', 'غير محدد')
        })
    
    return jsonify(stats, ensure_ascii=False)

# --- 🧹 تنظيف ذكي مع الذاكرة ---
def smart_cleanup_with_memory():
    """تنظيف دوري ذكي مع إدارة الذاكرة"""
    while True:
        time.sleep(900)  # كل 15 دقيقة
        
        conversation_manager.cleanup_old_conversations()
        customer_memory.cleanup_old_cache()
        
        # تنظيف الذاكرة
        if len(whatsapp_handler.processing_messages) > 500:
            whatsapp_handler.processing_messages.clear()
            print("🧹 تنظيف ذاكرة الرسائل")
        
        # تنظيف rate limiting
        current_time = time.time()
        expired_numbers = [
            number for number, last_time in whatsapp_handler.rate_limit.items() 
            if current_time - last_time > 1800  # 30 دقيقة
        ]
        for number in expired_numbers:
            del whatsapp_handler.rate_limit[number]
        
        print(f"🧠 إحصائيات الذاكرة: {len(customer_memory.customer_cache)} عميل نشط")

# تشغيل التنظيف الذكي
cleanup_thread = threading.Thread(target=smart_cleanup_with_memory, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("🧠 تشغيل بوت الركائز الذكي مع نظام الذاكرة الشخصية...")
    print("⚡ المميزات:")
    print("   - ردود فورية للترحيب والأسعار")
    print("   - 🙏 ردود شكر فورية بالهجة السعودية")
    print("   - 🧠 ذاكرة شخصية لكل عميل")
    print("   - 👤 ترحيب مخصص بأسماء العملاء")
    print("   - 📊 تتبع الخدمات السابقة والطلبات الحالية")
    print("   - 💬 سياق المحادثة الذكي")
    print("   - 🎯 ردود مخصصة حسب تفضيلات العميل")
    print("   - ⚡ كاش ذكي للسرعة العالية")
    print("=" * 60)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))