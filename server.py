import io
import json
import os
import requests
from datetime import datetime
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from xhtml2pdf import pisa
from num2words import num2words

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Токен
BOT_TOKEN = os.getenv("BOT_TOKEN", "8888816541:AAHr3KYdyGi3au_9xQQ83p7NVvI9A1Yp_xE")

# --- БАЗА ДАННЫХ ---
DATABASE_URL = "sqlite:///./profiles_final.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True)
    company = Column(String, default="ООО Ваша компания")
    inn = Column(String, default="0000000000")
    kpp = Column(String, default="")
    address = Column(String, default="г. Москва")
    contacts = Column(String, default="+7 (999) 999-99-99")
    tax_mode = Column(String, default="usn")
    director = Column(String, default="Иванов И.И.")
    director_pos = Column(String, default="Генерального директора")
    director_pos_nom = Column(String, default="Генеральный директор")
    bank_name = Column(String, default="")
    bik = Column(String, default="")
    rs = Column(String, default="")
    ks = Column(String, default="")
    logo = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def format_money(val):
    return f"{val:,.2f}".replace(',', ' ').replace('.', ',')

def num2words_rub(num):
    try:
        rub = int(num)
        kop = int(round((num - rub) * 100))
        rub_str = num2words(rub, lang='ru').capitalize()
        return f"{rub_str} рублей {kop:02d} копеек"
    except:
        return f"{format_money(num)} рублей"

def get_header_html(company, inn, kpp, address, contacts, logo_base64=None):
    logo_html = f'<img src="{logo_base64}" style="max-height: 50px; margin-bottom: 10px;"><br>' if logo_base64 else ''
    kpp_str = f"/{kpp}" if kpp else ""
    return f"""
    <div class="header-info">
        {logo_html}
        <strong>{company}</strong><br>ИНН/КПП: {inn}{kpp_str}<br>Адрес: {address}<br>Тел: {contacts}
    </div>
    """

CSS_STYLES = """
@page { size: a4; margin: 20mm 15mm 20mm 30mm; }
body { font-family: "Helvetica", sans-serif; font-size: 11pt; line-height: 1.35; text-align: justify; color: #000; }
h1.title { text-align: center; font-size: 14pt; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; }
.meta { width: 100%; margin-bottom: 20px; }
.meta td { border: none; padding: 0; }
.section-title { font-weight: bold; margin-top: 15px; margin-bottom: 10px; }
table { width: 100%; border-collapse: collapse; margin-top: 15px; }
th, td { border: 1px solid #000; padding: 6px; text-align: left; }
.header-info { margin-bottom: 20px; font-size: 10pt; text-align: left; }
.signature-block { margin-top: 30px; }
"""

# --- ЭНДПОИНТЫ API ---
@app.get("/")
def read_root(): 
    return {"status": "ok"}

@app.post("/generate-doc")
async def generate_doc(
    template: str = Form("kp"), company: str = Form("ООО Ваша компания"), inn: str = Form("0000000000"), kpp: str = Form(""), 
    address: str = Form("г. Москва"), contacts: str = Form("+7 (999) 999-99-99"), tax_mode: str = Form("usn"),
    director: str = Form("Иванов И.И."), director_pos: str = Form("Генерального директора"), director_pos_nom: str = Form("Генеральный директор"),
    services_json: str = Form("[]"), term: str = Form("30"), dogovor_number: str = Form("Б/Н"), dogovor_date: str = Form(""), 
    customer_name: str = Form("ООО Заказчик"), customer_inn: str = Form("1111111111"), customer_address: str = Form("г. Москва"), 
    customer_director: str = Form("Петров П.П."), customer_pos_nom: str = Form("Генеральный директор"),
    chat_id: str = Form(None), logo: str = Form(None),
    bank_name: str = Form(None), bik: str = Form(None), rs: str = Form(None), ks: str = Form(None)
):
    try:
        services = json.loads(services_json)
        total_price = sum(float(s['price']) * int(s['qty']) for s in services)
        current_date = datetime.now().strftime("%d.%m.%Y")
        date_to_use = dogovor_date if dogovor_date else current_date
        
        nds_text = "НДС не облагается на основании п. 2 ст. 346.11 НК РФ (УСН)"
        if tax_mode == "osno":
            nds_text = "В том числе НДС 22%"

        rows_html = ""
        for i, s in enumerate(services, 1):
            sum_s = float(s['price']) * int(s['qty'])
            rows_html += f"<tr><td align='center'>{i}</td><td>{s['name']}</td><td align='center'>{s.get('unit', 'шт')}</td><td align='center'>{s['qty']}</td><td align='right'>{format_money(float(s['price']))}</td><td align='right'>{format_money(sum_s)}</td></tr>"

        header = get_header_html(company, inn, kpp, address, contacts, logo)
        html_content = ""

        # --- ЛОГИКА ШАБЛОНОВ ---
        if template == "kp":
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            {header}
            <div style="text-align: right; margin-bottom: 10px;">Исх. № {dogovor_number} от {date_to_use} г.</div>
            <h1 class="title">Коммерческое предложение<br>на оказание услуг</h1>
            <p>Уважаемый клиент! {company} предлагает вам следующие услуги:</p>
            <table>
                <tr><th>№</th><th>Наименование услуги</th><th>Ед.</th><th>Срок</th><th>Стоимость</th></tr>
                {''.join([f"<tr><td align='center'>{i}</td><td>{s['name']}</td><td align='center'>{s.get('unit', 'усл.')}</td><td align='center'>{term} дн.</td><td align='right'>{format_money(float(s['price']) * int(s['qty']))} руб.</td></tr>" for i, s in enumerate(services, 1)])}
                <tr><td colspan="4" align="right"><b>Итого:</b></td><td align="right"><b>{format_money(total_price)} руб.</b></td></tr>
            </table>
            <p>({nds_text})</p>
            <div class="signature-block">
                <p>С уважением,<br>{director_pos_nom}<br>{company}</p>
                <br><br>
                <table style="width: 100%; border: none;"><tr>
                    <td style="border: none; width: 50%;">__________________ / {director} /</td>
                </tr></table>
            </div>
            </body></html>
            """
        elif template == "schet":
            bank_info = f"<p><b>Банк:</b> {bank_name}<br><b>БИК:</b> {bik}<br><b>Р/с:</b> {rs}<br><b>К/с:</b> {ks}</p>" if bank_name else ""
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            {header}
            <h1 class="title">Счет на оплату № {dogovor_number} от {date_to_use} г.</h1>
            <p><b>Поставщик:</b> {company}, ИНН {inn}, {address}<br><b>Покупатель:</b> {customer_name}, ИНН {customer_inn}, {customer_address}</p>
            <table>
                <tr><th>№</th><th>Наименование</th><th>Ед.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
                {rows_html}
                <tr><td colspan="5" align="right"><b>Итого:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
                <tr><td colspan="5" align="right">{nds_text}</td><td align="right">0,00</td></tr>
                <tr><td colspan="5" align="right"><b>Всего к оплате:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
            </table>
            <p>Сумма прописью: {num2words_rub(total_price)}.</p>
            {bank_info}
            <div class="signature-block">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="border: none; width: 50%;">Руководитель:<br><br>__________________ / {director} /</td>
                        <td style="border: none; width: 50%;">Главный бухгалтер:<br><br>__________________ / {director} /</td>
                    </tr>
                </table>
            </div>
            </body></html>
            """
        else:
            html_content = f"<html><body><h1>{template.upper()}</h1><p>Документ на сумму {total_price} руб.</p></body></html>"

        pdf_buffer = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
        pdf_buffer.seek(0)

        if chat_id:
            file_name = f"{template}_{current_date.replace('.', '_')}.pdf"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            files = {'document': (file_name, pdf_buffer, 'application/pdf')}
            data = {'chat_id': chat_id, 'caption': f'Ваш документ ({template.upper()}) готов! 📄'}
            requests.post(url, files=files, data=data)
            return {"status": "ok", "message": "Отправлено в Telegram"}

        return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=document.pdf"})

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
