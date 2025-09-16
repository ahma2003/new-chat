# whatsapp_handler.py
import requests
import json
import time
import threading
from config import ACCESS_TOKEN, PHONE_NUMBER_ID

class WhatsAppHandler:
    def __init__(self):
        self.processing_messages = set()
        self.rate_limit = {}

    def is_duplicate_message(self, message_id: str) -> bool:
        if message_id in self.processing_messages:
            return True
        self.processing_messages.add(message_id)
        threading.Timer(30.0, lambda: self.processing_messages.discard(message_id)).start()
        return False

    def check_rate_limit(self, phone_number: str) -> bool:
        now = time.time()
        if phone_number in self.rate_limit and now - self.rate_limit[phone_number] < 0.5:
            return True
        self.rate_limit[phone_number] = now
        return False

    def send_message(self, to_number: str, message: str) -> bool:
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            print("❌ معلومات WhatsApp غير مكتملة")
            return False
            
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        
        message = message.strip()
        if len(message) > 900:
            message = message[:850] + "...\n\nللمزيد: 📞 0556914447"
        
        data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": message}}
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
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
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        
        data = {
            "messaging_product": "whatsapp", "to": to_number, "type": "image",
            "image": {"link": image_url, "caption": message}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
            response.raise_for_status()
            print(f"✅ تم إرسال الصورة إلى {to_number}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ خطأ في الصورة: {e}")
            return self.send_message(to_number, f"{message}\n\n📞 اتصل للحصول على صورة الأسعار: 0556914447")