# config.py
import os

# --- WhatsApp Configuration ---
ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN')
PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')

# --- OpenAI Configuration ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# --- Database Configuration ---
# Railway سيقوم بتوفير هذا المتغير تلقائياً
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- AI Model Configuration (Optional) ---
MODEL_NAME = 'intfloat/multilingual-e5-large'
PERSIST_DIRECTORY = "my_chroma_db"
COLLECTION_NAME = "recruitment_qa"