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

# --- 🆕 نظام إدارة العملاء الجديد ---
class CustomerManager:
    def __init__(self, data_file="customers_data.json"):
        self.data_file = data_file
        self.customers_data: Dict[str, Dict] = {} # تخزين البيانات برقم الجوال كمفتاح
        self._load_customers_data()
        self.data_lock = threading.Lock() # لتجنب مشاكل الوصول المتزامن

    def _load_customers_data(self):
        """تحميل بيانات العملاء من ملف JSON."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                    for customer in raw_data:
                        # WhatsApp phone numbers often come with country code but no '+'
                        # Ensure consistency by storing/accessing without '+' if it's not in your data
                        phone_number_clean = customer['phone_number'].replace('+', '')
                        self.customers_data[phone_number_clean] = customer
                print(f"✅ تم تحميل بيانات {len(self.customers_data)} عميل.")
            except Exception as e:
                print(f"❌ خطأ في تحميل بيانات العملاء: {e}")
                self.customers_data = {}
        else:
            print(f"⚠️ ملف بيانات العملاء '{self.data_file}' غير موجود. يرجى التأكد من إنشائه.")
            self.customers_data = {}

    def get_customer_info(self, phone_number: str) -> Optional[Dict]:
        """الحصول على معلومات عميل محدد."""
        # Clean phone number for lookup (remove + if present)
        clean_phone_number = phone_number.replace('+', '')
        with self.data_lock:
            return self.customers_data.get(clean_phone_number)

    def update_customer_info(self, phone_number: str, new_info: Dict):
        """تحديث معلومات عميل وحفظها في الملف (للتوسع المستقبلي)."""
        clean_phone_number = phone_number.replace('+', '')
        with self.data_lock:
            if clean_phone_number in self.customers_data:
                self.customers_data[clean_phone_number].update(new_info)
                self._save_customers_data()
            else:
                print(f"⚠️ لا يمكن تحديث العميل: {phone_number} غير موجود في قاعدة البيانات.")

    def _save_customers_data(self):
        """حفظ بيانات العملاء إلى ملف JSON (للتوسع المستقبلي)."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.customers_data.values()), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ خطأ في حفظ بيانات العملاء: {e}")


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
        if not message or len(message.strip()) == 0: return False
        message_clean = message.lower().strip()
        words = message_clean.split()
        if len(words) <= 6:
            for word in words:
                clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
                if clean_word in self.welcome_patterns: return True
        return False
    
    def is_thanks_message(self, message: str) -> bool:
        if not message or len(message.strip()) == 0: return False
        message_clean = message.lower().strip()
        for phrase in self.thanks_phrases:
            if phrase in message_clean: return True
        words = message_clean.split()
        thanks_word_count = 0
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            if clean_word in self.thanks_patterns: thanks_word_count += 1
        return thanks_word_count >= 1
    
    def is_price_inquiry(self, message: str) -> bool:
        if not message or len(message.strip()) == 0: return False
        message_clean = message.lower().strip()
        for phrase in self.price_phrases:
            if phrase in message_clean: return True
        words = message_clean.split()
        price_word_count = 0
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum() or c in 'أابتثجحخدذرزسشصضطظعغفقكلمنهويىءآإ')
            if clean_word in self.price_keywords: price_word_count += 1
        return price_word_count >= 1
    
    def get_welcome_response(self) -> str:
        return "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام 🌟\n\nنحن هنا لخدمتك ومساعدتك في جميع احتياجاتك من العمالة المنزلية المدربة والمؤهلة.\n\nكيف يمكنني مساعدتك اليوم؟ 😊"

    def get_thanks_response(self) -> str:
        responses = [
            "العفو عميلنا العزيز 🌟\n\nالله يعطيك العافية.. نحن في خدمتك دائماً في مكتب الركائز البشرية\n\nهل تحتاج أي مساعدة أخرى؟ 😊",
            "أهلاً وسهلاً.. هذا واجبنا 🤝\n\nنحن سعداء بخدمتك في مكتب الركائز البشرية للاستقدام\n\nالله يوفقك.. ولا تتردد في التواصل معنا متى شئت! 💙",
            "حياك الله.. ما سوينا إلا الواجب 🌟\n\nخدمتك شرف لنا في مكتب الركائز البشرية\n\nتواصل معنا في أي وقت.. نحن هنا لخدمتك! 📞"
        ]
        import random
        return random.choice(responses)

    def get_price_response(self) -> tuple:
        text_response = "إليك عروضنا الحالية للعمالة المنزلية المدربة 💼\n\n🎉 عرض خاص بمناسبة اليوم الوطني السعودي 95\n\nللاستفسار والحجز اتصل بنا:\n📞 0556914447 / 0506207444 / 0537914445"
        image_url = "https://i.imghippo.com/files/La2232xjc.jpg" # استبدل برابط صورتك
        return text_response, image_url

# --- 🔍 نظام البحث المحسن ---
class EnhancedRetriever:
    def __init__(self, model, collection):
        self.model = model
        self.collection = collection
    
    def retrieve_best_matches(self, user_query: str, top_k: int = 3) -> tuple:
        if not self.model or not self.collection: return [], 0.0
        try:
            query_embedding = self.model.encode([f"query: {user_query}"], normalize_embeddings=True)
            results = self.collection.query(query_embeddings=query_embedding.tolist(), n_results=min(top_k, 5))
            if not results.get('metadatas') or not results['metadatas'][0]: return [], 0.0
            best_score = 1 - results['distances'][0][0] if 'distances' in results else 0
            return results['metadatas'][0], best_score
        except Exception as e:
            print(f"❌ خطأ في البحث: {e}")
            return [], 0.0

# --- 🤖 نظام الردود الذكي السريع والمخصص ---
class SmartResponseGenerator:
    def __init__(self, openai_client, retriever, quick_system, customer_manager):
        self.openai_client = openai_client
        self.retriever = retriever
        self.quick_system = quick_system
        self.customer_manager = customer_manager
    
    def generate_response(self, user_message: str, phone_number: str, is_first: bool) -> tuple:
        customer_info = self.customer_manager.get_customer_info(phone_number)
        customer_name = customer_info['name'] if customer_info and 'name' in customer_info else "عميلنا العزيز"
        
        if self.quick_system.is_greeting_message(user_message):
            if customer_info:
                return f"أهلاً وسهلاً بك يا {customer_name} في مكتب الركائز البشرية للاستقدام 🌟\n\nيسعدنا تواصلك معنا دائماً.\nكيف يمكنني مساعدتك اليوم؟ 😊", False, None
            else:
                return self.quick_system.get_welcome_response(), False, None
        
        if self.quick_system.is_thanks_message(user_message):
            if customer_info:
                 return f"العفو يا {customer_name} 🌟\n\nالله يعطيك العافية.. نحن في خدمتك دائماً في مكتب الركائز البشرية.\nهل تحتاج أي مساعدة أخرى؟ 😊", False, None
            else:
                return self.quick_system.get_thanks_response(), False, None
        
        if self.quick_system.is_price_inquiry(user_message):
            text_response, image_url = self.quick_system.get_price_response()
            if customer_info:
                 text_response = f"حياك الله يا {customer_name} 🤝\n" + text_response
            return text_response, True, image_url
        
        retrieved_data, _ = self.retriever.retrieve_best_matches(user_message) if self.retriever else ([], 0)
        
        if not self.openai_client:
            return (f"بناءً على معلوماتنا:\n\n{retrieved_data[0]['answer']}" if retrieved_data else "أهلاً بك! 🌟\nسيتواصل معك أحد موظفينا قريباً للمساعدة.", False, None)
        
        try:
            context = self.generate_context_string(retrieved_data)
            customer_context = self.build_customer_context(customer_info)
            intro = self.build_intro(is_first, customer_info, customer_name)

            system_prompt = f"""{intro}أنت مساعد مكتب الركائز البشرية للاستقدام.
شخصيتك: ودودة جداً، مهتمة، مبادرة، تتكلم بلهجة سعودية خفيفة.
هدف رئيسي: إرضاء العميل وتقديم خدمة مميزة ومخصصة له.
استخدم معلومات العميل لتقديم ردود شخصية. إذا كان العميل معروفاً، ابدأ بتحيته باسمه.
اقتبس من خدماته السابقة أو طلباته الحالية إذا كانت ذات صلة بالسؤال.
قدم اقتراحات بناءً على تفضيلاته. اختتم بسؤال لتشجيع الحوار.

السؤال: {user_message}

{customer_context}
المعلومات العامة المتاحة: {context}"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                max_tokens=700, temperature=0.4
            )
            return response.choices[0].message.content.strip(), False, None
        except Exception as e:
            print(f"❌ خطأ في OpenAI: {e}")
            return (f"عميلنا العزيز، بناءً على خبرتنا:\n\n{retrieved_data[0]['answer']}" if retrieved_data else f"أهلاً بك يا {customer_name}! 🌟 سيتواصل معك أحد متخصصينا قريباً.", False, None)
    
    def generate_context_string(self, retrieved_data):
        if not retrieved_data: return "لا توجد معلومات محددة."
        item = retrieved_data[0]
        return f"السؤال: {item['question']}\nالإجابة: {item['answer']}"

    def build_intro(self, is_first, customer_info, customer_name):
        if is_first and not customer_info:
            return "أهلاً وسهلاً بك في مكتب الركائز البشرية للاستقدام! 🌟\n\n"
        elif is_first and customer_info:
            return f"أهلاً وسهلاً بك مجدداً يا {customer_name} في مكتب الركائز البشرية 🌟\n\nيسعدنا تواصلك معنا.\n"
        return ""

    def build_customer_context(self, customer_info):
        if not customer_info: return ""
        context_parts = [
            "معلومات العميل:",
            f"الاسم: {customer_info.get('name', 'غير معروف')}",
            f"الجنس: {customer_info.get('gender', 'غير معروف')}"
        ]
        if customer_info.get('past_services'):
            context_parts.append("خدمات سابقة (العاملات المستقدمة):")
            for service in customer_info['past_services']:
                context_parts.append(f"- {service.get('worker_name', '')} ({service.get('nationality', '')}) - {service.get('job_title', '')}، الحالة: {service.get('status', '')}")
        else:
            context_parts.append("- لم يسبق له استقدام عاملات.")
        
        if customer_info.get('current_requests'):
            context_parts.append("طلبات استقدام حالية:")
            for req in customer_info['current_requests']:
                context_parts.append(f"- {req.get('type', '')} ({req.get('nationality_preference', '')})، الحالة: {req.get('status', '')}، التوصيل المتوقع: {req.get('estimated_delivery', 'غير معروف')}")
        else:
            context_parts.append("- لا توجد لديه طلبات استقدام حالية.")
            
        context_parts.append(f"الجنسية المفضلة سابقاً: {customer_info.get('preferred_nationality', 'غير محدد')}")
        context_parts.append(f"تفضيلات العميل العامة: {customer_info.get('preferences', 'لا توجد تفضيلات محددة.')}")
        return "\n".join(context_parts) + "\n-------\n"
                is_first = conversation_manager.is_first_message(phone_number)
        
        if is_first:
            conversation_manager.register_conversation(phone_number)
        else:
            conversation_manager.update_activity(phone_number)
        
        # توليد الرد السريع
        if response_generator:
            bot_response, should_send_image, image_url = response_generator.generate_response(
                user_message, phone_number, is_first
            )
            
            # إرسال الرد
            if should_send_image and image_url:
                whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
            else:
                whatsapp_handler.send_message(phone_number, bot_response)
        else:
            # نظام احتياطي أساسي (في حال لم يتم تحميل response_generator)
            if quick_system.is_greeting_message(user_message):
                bot_response = quick_system.get_welcome_response()
                whatsapp_handler.send_message(phone_number, bot_response)
            elif quick_system.is_thanks_message(user_message):
                bot_response = quick_system.get_thanks_response()
                whatsapp_handler.send_message(phone_number, bot_response)
            elif quick_system.is_price_inquiry(user_message):
                bot_response, image_url = quick_system.get_price_response()
                whatsapp_handler.send_image_with_text(phone_number, bot_response, image_url)
            else:
                bot_response = "أهلاً بك في مكتب الركائز البشرية! 🌟\nسيتواصل معك متخصص قريباً.\n📞 0556914447"
                whatsapp_handler.send_message(phone_number, bot_response)
        
        # إحصائيات سريعة
        response_time = time.time() - start_time
        print(f"✅ استجابة في {response_time:.2f}s لـ {phone_number}")
        
    except Exception as e:
        print(f"❌ خطأ فادح في معالجة الرسالة: {e}")
        whatsapp_handler.send_message(phone_number, "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى أو التواصل معنا على الرقم: 📞 0556914447")

@app.route('/')
def status():
    """صفحة حالة سريعة"""
    active_conversations = len(conversation_manager.conversations)
    customers_loaded = len(customer_manager.customers_data)
    
    return f"""
    <html><head><title>بوت الركائز - شخصي وذكي</title>
    <style>body{{font-family:Arial, sans-serif;margin:40px;background:#f0f8ff;color:#333;}}
    .box{{background:white;padding:20px;border-radius:10px;margin:10px 0;box-shadow: 0 2px 4px rgba(0,0,0,0.1);}}
    h1, h2 {{color:#0056b3;}}
    .green{{color:#28a745;}} .red{{color:#dc3545;}} .blue{{color:#007bff;}} .orange{{color:#fd7e14;}}
    </style></head><body>
    
    <div class="box">
    <h1>🚀 مكتب الركائز - بوت شخصي وذكي</h1>
    </div>
    
    <div class="box">
    <h2>📊 الحالة:</h2>
    <p class="{'green' if openai_client else 'red'}">{'✅' if openai_client else '❌'} OpenAI API</p>
    <p class="{'green' if enhanced_retriever else 'red'}">{'✅' if enhanced_retriever else '❌'} قاعدة بيانات المعلومات (ChromaDB)</p>
    <p class="{'green' if customers_loaded > 0 else 'orange'}">{'✅' if customers_loaded > 0 else '⚠️'} قاعدة بيانات العملاء ({customers_loaded} عميل)</p>
    <p class="green">⚡ الردود السريعة - نشط</p>
    <p class="blue">🙏 ردود الشكر السريعة - نشط</p>
    <p class="green">📱 المحادثات النشطة: {active_conversations}</p>
    </div>
    
    <div class="box">
    <h2>⭐ المميزات الجديدة:</h2>
    <ul>
    <li>✅ <strong>تخصيص الردود:</strong> يتعرف على العميل بالاسم ويرحب به بشكل شخصي.</li>
    <li>✅ <strong>سياق المحادثة:</strong> يفهم طلبات العميل السابقة والحالية.</li>
    <li>✅ <strong>متابعة الطلبات:</strong> يمكنه الإجابة عن حالة طلبات الاستقدام الحالية.</li>
    <li>✅ <strong>اقتراحات ذكية:</strong> يقترح خدمات بناءً على تفضيلات العميل.</li>
    </ul>
    </div>
    
    </body></html>"""

@app.route('/test-quick/<message>')
def test_quick_response(message):
    """اختبار سريع للردود"""
    start_time = time.time()
    
    is_greeting = quick_system.is_greeting_message(message)
    is_thanks = quick_system.is_thanks_message(message)
    is_price = quick_system.is_price_inquiry(message)
    
    processing_time = time.time() - start_time
    
    result = {
        "الرسالة": message,
        "ترحيب؟": is_greeting,
        "شكر؟": is_thanks,
        "سؤال أسعار؟": is_price,
        "وقت المعالجة": f"{processing_time:.4f} ثانية",
        "نوع الرد": "سريع" if (is_greeting or is_thanks or is_price) else "عادي"
    }
    
    if is_greeting: result["الرد"] = quick_system.get_welcome_response()
    elif is_thanks: result["الرد"] = quick_system.get_thanks_response()
    elif is_price:
        text, image = quick_system.get_price_response()
        result["الرد"] = text
        result["صورة"] = image
    
    return jsonify(result, ensure_ascii=False)

# --- 🧹 تنظيف سريع ---
def quick_cleanup():
    """تنظيف دوري سريع"""
    while True:
        time.sleep(1800)  # كل 30 دقيقة
        
        print("🧹 بدء عملية التنظيف الدورية...")
        conversation_manager.cleanup_old_conversations()
        
        # تنظيف الذاكرة المؤقتة للرسائل المكررة
        if len(whatsapp_handler.processing_messages) > 1000:
            whatsapp_handler.processing_messages.clear()
            print("🧹 تنظيف ذاكرة الرسائل المكررة.")
        
        # تنظيف قائمة تحديد المعدل
        current_time = time.time()
        expired_numbers = [
            number for number, last_time in whatsapp_handler.rate_limit.items() 
            if current_time - last_time > 3600  # ساعة واحدة
        ]
        for number in expired_numbers:
            if number in whatsapp_handler.rate_limit:
                del whatsapp_handler.rate_limit[number]
        if expired_numbers:
            print(f"🧹 تم تنظيف سجلات تحديد المعدل لـ {len(expired_numbers)} رقم.")

# تشغيل التنظيف السريع
cleanup_thread = threading.Thread(target=quick_cleanup, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 تشغيل بوت الركائز الذكي والمخصص...")
    print("⭐ المميزات الجديدة:")
    print("   - ✅ يتعرف على العملاء ويرحب بهم بأسمائهم.")
    print("   - ✅ يفهم سياق طلبات العميل السابقة والحالية.")
    print("   - ✅ يقدم ردوداً شخصية ومخصصة لكل عميل.")
    print("=" * 50)
    # استخدم gunicorn أو waitress في الإنتاج بدلاً من app.run
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))