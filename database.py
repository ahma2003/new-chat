# database.py
import psycopg2
from psycopg2.extras import DictCursor
from config import DATABASE_URL

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

def get_customer_details_from_db(phone_number: str) -> dict:
    """
    جلب بيانات العميل كاملة (الأساسية، الخدمات السابقة، الطلبات الحالية)
    من قاعدة البيانات وتحويلها إلى نفس شكل ملف JSON السابق.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # 1. جلب البيانات الأساسية للعميل
            cur.execute("SELECT * FROM customers WHERE phone_number = %s;", (phone_number,))
            customer_record = cur.fetchone()

            if not customer_record:
                return None

            customer_data = dict(customer_record)
            
            # 2. جلب الخدمات السابقة
            cur.execute("SELECT * FROM past_services WHERE phone_number = %s ORDER BY contract_date DESC;", (phone_number,))
            past_services = [dict(record) for record in cur.fetchall()]
            for service in past_services:
                if service.get('contract_date'):
                    service['contract_date'] = service['contract_date'].isoformat()
            customer_data['past_services'] = past_services

            # 3. جلب الطلبات الحالية
            cur.execute("SELECT * FROM current_requests WHERE phone_number = %s;", (phone_number,))
            current_requests = [dict(record) for record in cur.fetchall()]
            for request in current_requests:
                if request.get('estimated_delivery'):
                    request['estimated_delivery'] = request['estimated_delivery'].isoformat()
            customer_data['current_requests'] = current_requests

            return customer_data
            
    except Exception as e:
        print(f"❌ خطأ في جلب بيانات العميل من قاعدة البيانات: {e}")
        return None
    finally:
        if conn:
            conn.close()

def add_new_customer(phone, name, gender, nationality, preferences):
    """إضافة عميل جديد لقاعدة البيانات."""
    conn = get_db_connection()
    if not conn:
        return False, "فشل الاتصال بقاعدة البيانات"
        
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customers (phone_number, name, gender, preferred_nationality, preferences)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    name = EXCLUDED.name,
                    gender = EXCLUDED.gender,
                    preferred_nationality = EXCLUDED.preferred_nationality,
                    preferences = EXCLUDED.preferences;
                """,
                (phone, name, gender, nationality, preferences)
            )
            conn.commit()
        return True, "تم إضافة/تحديث العميل بنجاح"
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في إضافة العميل: {e}")
        return False, f"خطأ: {e}"
    finally:
        if conn:
            conn.close()