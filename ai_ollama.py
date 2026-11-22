import os
import streamlit as st
from google import genai

OLLAMA_URL = "Cloud Gemini API"
MODEL_MAC_DINH = "gemini-2.5-flash"

def lay_client():
    # Lấy API Key từ Secrets của Streamlit Cloud hoặc biến môi trường
    api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def danh_sach_model(url=None):
    # Trả về các model Gemini miễn phí và nhanh nhất hiện nay
    return ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]

def lam_nong_model(model, url=None):
    # API đám mây luôn sẵn sàng trên server Google nên không cần nạp trước vào RAM
    pass

def nhan_xet_cv(prompt, model="gemini-2.5-flash", url=None):
    client = lay_client()
    if not client:
        return "⚠️ Lỗi: Chưa cấu hình GEMINI_API_KEY trong phần Secrets của Streamlit."
    
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"⚠️ Lỗi khi gọi Gemini API: {str(e)}"
