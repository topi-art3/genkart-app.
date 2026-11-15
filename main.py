from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import io
import json
import requests
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from xhtml2pdf import pisa

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- ТОКЕН НОВОГО БОТА ---
BOT_TOKEN = "9065574882:AAEiC0Ls-YC1ADejERPNLcZSdEJS7qCZe_I" 

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
    logo = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

CSS_STYLES = """
@page { size: a4; margin: 20mm 15mm 20mm 30mm; }
body { font-family: "Helvetica", sans-serif; font-size: 11pt; line-height: 1.35; text-align: justify; color: #000; }
h1.title { text-align: center; font-size: 14pt; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; }
.meta { width: 100%; margin-bottom: 20px; }
.meta td { border: none; padding: 0; }
.section-title { font-weight: bold; margin-top: 15px; margin-bottom: 10px; }
table { width: 100%; margin-top: 15px; }
th, td { border: 1px solid #000; padding: 6px; text-align: left; }
.header-info { margin-bottom: 20px; font-size: 10pt; text-align: left; }
.signature-block { margin-top: 30px; }
"""

def format_money(val):
    return f"{val:,.2f}".replace(',', ' ').replace('.', ',')

def get_header_html(company, inn, kpp, address, contacts, logo_base64=None):
    logo_html = f'<img src="{logo_base64}" style="max-height: 50px; margin-bottom: 10px;"><br>' if logo_base64 else ''
    kpp_str = f"/{kpp}" if kpp else ""
    return f"""
    <div class="header-info">
        {logo_html}
        <strong>{company}</strong><br>ИНН/КПП: {inn}{kpp_str}<br>Адрес: {address}<br>Тел: {contacts}
    </div>
    """

# --- ИНТЕРФЕЙС (HTML) ---
@app.get("/")
def read_root(): 
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>GenDoc</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background: #1a1a1a; color: #fff; font-family: sans-serif; padding: 16px; margin: 0; }
            .card { background: #2a2a2a; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
            input, select { background: #111; border: 1px solid #3f3f3f; color: #fff; padding: 10px; border-radius: 8px; width: 100%; box-sizing: border-box; margin-bottom: 8px; }
            .row { display: flex; gap: 8px; }
            .btn { background: #e83e8c; color: white; border: none; padding: 16px; border-radius: 12px; font-size: 16px; font-weight: bold; width: 100%; cursor: pointer; }
        </style>
    </head>
    <body>
        <h3>Создание документа</h3>
        
        <div class="card">
            <select id="template">
                <option value="kp">Коммерческое предложение (КП)</option>
                <option value="smeta">Смета</option>
                <option value="dogovor">Договор</option>
                <option value="act">Акт</option>
                <option value="invoice">Счет</option>
            </select>
            
            <input type="text" id="company" placeholder="Ваша компания" value="ООО Ваша компания">
            <input type="text" id="inn" placeholder="ИНН" value="0000000000">
            <input type="text" id="address" placeholder="Адрес" value="г. Москва">
            <input type="text" id="director" placeholder="ФИО Директора" value="Иванов И.И.">
            
            <hr style="border-color: #3f3f3f; margin: 15px 0;">
            
            <input type="text" id="customer_name" placeholder="Заказчик (Компания)" value="ООО Заказчик">
            <input type="text" id="customer_inn" placeholder="ИНН Заказчика" value="1111111111">
            <input type="text" id="customer_director" placeholder="ФИО Директора Заказчика" value="Петров П.П.">
            
            <hr style="border-color: #3f3f3f; margin: 15px 0;">
            
            <p style="margin-top:0;">Услуга:</p>
            <input type="text" id="service_name" placeholder="Название услуги" value="Транспортировка">
            <div class="row">
                <input type="text" id="unit" placeholder="Ед." value="рейс" style="width: 30%;">
                <input type="number" id="qty" placeholder="Кол-во" value="1" style="width: 30%;">
                <input type="number" id="price" placeholder="Цена" value="10000" style="width: 40%;">
            </div>
        </div>

        <button class="btn" onclick="createDoc()">Создать PDF 📄</button>

        <script>
            const tg = window.Telegram.WebApp;
            tg.expand();

            async function createDoc() {
                const data = new FormData();
                data.append("template", document.getElementById('template').value);
                data.append("company", document.getElementById('company').value);
                data.append("inn", document.getElementById('inn').value);
                data.append("address", document.getElementById('address').value);
                data.append("director", document.getElementById('director').value);
                
                data.append("customer_name", document.getElementById('customer_name').value);
                data.append("customer_inn", document.getElementById('customer_inn').value);
                data.append("customer_director", document.getElementById('customer_director').value);
                
                data.append("services_json", JSON.stringify([{
                    name: document.getElementById('service_name').value,
                    unit: document.getElementById('unit').value,
                    qty: document.getElementById('qty').value,
                    price: document.getElementById('price').value
                }]));
                
                data.append("chat_id", tg.initDataUnsafe?.user?.id || "");

                tg.MainButton.showProgress();
                try {
                    const response = await fetch('/generate-doc', { method: 'POST', body: data });
                    if (response.ok) {
                        tg.showAlert("Документ отправлен в чат!");
                    } else {
                        tg.showAlert("Ошибка при создании");
                    }
                } catch (e) {
                    tg.showAlert("Ошибка сети");
                } finally {
                    tg.MainButton.hideProgress();
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# --- ГЕНЕРАЦИЯ ДОКУМЕНТОВ (Твой код) ---
@app.post("/generate-doc")
async def generate_doc(
    template: str = Form("kp"), company: str = Form("ООО Ваша компания"), inn: str = Form("0000000000"), kpp: str = Form(""), 
    address: str = Form("г. Москва"), contacts: str = Form("+7 (999) 999-99-99"), tax_mode: str = Form("usn"),
    director: str = Form("Иванов И.И."), director_pos: str = Form("Генерального директора"), director_pos_nom: str = Form("Генеральный директор"),
    services_json: str = Form("[]"), term: str = Form("30"), dogovor_number: str = Form("Б/Н"), dogovor_date: str = Form(""), 
    customer_name: str = Form("ООО Заказчик"), customer_inn: str = Form("1111111111"), customer_kpp: str = Form(""), customer_address: str = Form("г. Москва"), 
    customer_director: str = Form("Петров П.П."), customer_pos: str = Form("Генерального директора"), customer_pos_nom: str = Form("Генеральный директор"),
    smeta_date: str = Form(""), smeta_appendix: str = Form("1"), chat_id: str = Form(None), logo: str = Form(None),
    bank_name: str = Form(None), bik: str = Form(None), rs: str = Form(None), ks: str = Form(None)
):
    try:
        services = json.loads(services_json)
        total_price = sum(float(s['price']) * int(s['qty']) for s in services)
        current_date = datetime.now().strftime("%d.%m.%Y")
        date_to_use = dogovor_date if dogovor_date else current_date
        smeta_date_to_use = smeta_date if smeta_date else current_date
        buffer = io.BytesIO()
        
        if tax_mode == "osno":
            nds_text = "В том числе НДС 22%"
        else:
            nds_text = "НДС не облагается на основании п. 2 ст. 346.11 НК РФ (УСН)"
            
        header_html = get_header_html(company, inn, kpp, address, contacts, logo)

        # --- КП ---
        if template == "kp":
            rows = "".join([f"<tr><td style='text-align:center;'>{i+1}</td><td>{s['name']}</td><td style='text-align:center;'>{term}</td><td style='text-align:right;'>{format_money(float(s['price'])*int(s['qty']))} руб.</td></tr>" for i, s in enumerate(services)])
            html = f"""<html><head><meta charset="utf-8"><style>{CSS_STYLES}</style></head><body>
            {header_html}
            <table class="meta"><tr><td style="text-align:right;">Исх. № {dogovor_number} от {date_to_use} г.</td></tr></table>
            <h1 class="title">Коммерческое предложение<br>на оказание услуг</h1>
            <p>Уважаемый клиент! {company} предлагает вам следующие услуги:</p>
            <table><tr><th style="text-align:center; width: 5%;">№</th><th style="width: 50%;">Наименование услуги</th><th style="text-align:center; width: 15%;">Срок</th><th style="text-align:right; width: 20%;">Стоимость</th></tr>{rows}</table>
            <p style="text-align:right; margin-top: 10px; text-indent: 0;"><strong>Итого: {format_money(total_price)} руб.</strong><br>({nds_text})</p>
            <div class="signature-block"><strong>С уважением,</strong><br><br>{director_pos_nom}<br>{company}<br><br><br>_______________ / {director} /<br>М.П.</div>
            </body></html>"""
            pisa.CreatePDF(html, dest=buffer)

        # --- СМЕТА ---
        elif template == "smeta":
            rows = "".join([f"<tr><td style='text-align:center;'>{i+1}</td><td>{s['name']}</td><td style='text-align:center;'>{s.get('unit', 'усл.')}</td><td style='text-align:center;'>{s['qty']}</td><td style='text-align:right;'>{format_money(float(s['price']))}</td><td style='text-align:right;'>{format_money(float(s['price'])*int(s['qty']))}</td></tr>" for i, s in enumerate(services)])
            html = f"""<html><head><meta charset="utf-8"><style>{CSS_STYLES}</style></head><body>
            <table class="meta"><tr><td style="text-align:right;">Приложение № {smeta_appendix} к Договору № {dogovor_number} от {smeta_date_to_use}</td></tr></table>
            <h1 class="title">Смета № {smeta_appendix}</h1>
            <table><tr><th style="text-align:center; width: 5%;">№</th><th style="width: 40%;">Наименование</th><th style="text-align:center; width: 10%;">Ед.</th><th style="text-align:center; width: 10%;">Кол-во</th><th style="text-align:right; width: 15%;">Цена</th><th style="text-align:right; width: 15%;">Сумма</th></tr>{rows}<tr><td colspan="5" style="text-align:right;font-weight:bold;">Всего:</td><td style="text-align:right;font-weight:bold;">{format_money(total_price)}</td></tr></table>
            <p><strong>Всего наименований {len(services)}, на сумму {format_money(total_price)} руб.</strong> {nds_text}.</p>
            <table style="width: 100%; border: none; margin-top: 30px; text-indent: 0;"><tr><td style="border: none; width: 50%;"><strong>Исполнитель:</strong><br>{company}<br><br><br>{director_pos_nom}<br>_______________ / {director} /<br>М.П.</td><td style="border: none; width: 50%;"><strong>Заказчик:</strong><br>{customer_name}<br><br><br>{customer_pos_nom}<br>_______________ / {customer_director} /<br>М.П.</td></tr></table>
            </body></html>"""
            pisa.CreatePDF(html, dest=buffer)

        # --- ДОГОВОР ---
        elif template == "dogovor":
            first_service = services[0]['name'] if services else "Услуги"
            kpp_str = f", КПП: {kpp}" if kpp else ""
            cust_kpp_str = f", КПП: {customer_kpp}" if customer_kpp else ""
            html = f"""<html><head><meta charset="utf-8"><style>{CSS_STYLES}</style></head><body>
            <h1 class="title">ДОГОВОР ОКАЗАНИЯ УСЛУГ № {dogovor_number}</h1>
            <table class="meta"><tr><td style="text-align: left;">г. Москва</td><td style="text-align: right;">{date_to_use} г.</td></tr></table>
            <p>{company}, в лице {director_pos} {director}, с одной стороны, и {customer_name} (ИНН: {customer_inn}{cust_kpp_str}, адрес: {customer_address}), в лице {customer_pos} {customer_director}, с другой стороны, заключили Договор:</p>
            <div class="section-title">1. ПРЕДМЕТ ДОГОВОРА</div>
            <p>1.1. Исполнитель обязуется оказать следующие услуги: <strong>{first_service}</strong> (далее — «Услуги»).</p>
            <p>1.2. Перечень и стоимость Услуг определяются в Смете (Приложение № {smeta_appendix}).</p>
            <div class="section-title">2. СТОИМОСТЬ И ПОРЯДОК РАСЧЕТОВ</div>
            <p>2.1. Общая стоимость Услуг составляет <strong>{format_money(total_price)} руб.</strong>, {nds_text}.</p>
            <p>2.2. Оплата 100% в течение 3 банковских дней с момента подписания Акта.</p>
            <div class="section-title">5. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН</div>
            <table style="width: 100%; border: none; margin-top: 20px; text-indent: 0;">
                <tr>
                    <td style="border: none; width: 50%; vertical-align: top; padding-right: 10px;">
                        <strong>Исполнитель:</strong><br>{company}<br>ИНН: {inn}{kpp_str}<br>Адрес: {address}<br><br>{director_pos_nom}<br><br>_______________ / {director} /<br>М.П.
                    </td>
                    <td style="border: none; width: 50%; vertical-align: top; padding-left: 10px;">
                        <strong>Заказчик:</strong><br>{customer_name}<br>ИНН: {customer_inn}{cust_kpp_str}<br>Адрес: {customer_address}<br><br>{customer_pos_nom}<br><br>_______________ / {customer_director} /<br>М.П.
                    </td>
                </tr>
            </table>
            </body></html>"""
            pisa.CreatePDF(html, dest=buffer)

        # --- АКТ ---
        elif template == "act":
            rows = "".join([f"<tr><td style='text-align:center;'>{i+1}</td><td>{s['name']}</td><td style='text-align:center;'>{s.get('unit', 'усл.')}</td><td style='text-align:center;'>{s['qty']}</td><td style='text-align:right;'>{format_money(float(s['price']))}</td><td style='text-align:right;'>{format_money(float(s['price'])*int(s['qty']))}</td></tr>" for i, s in enumerate(services)])
            kpp_str = f", КПП: {kpp}" if kpp else ""
            cust_kpp_str = f", КПП: {customer_kpp}" if customer_kpp else ""
            html = f"""<html><head><meta charset="utf-8"><style>{CSS_STYLES}</style></head><body>
            <h1 class="title">АКТ СДАЧИ-ПРИЕМКИ ОКАЗАННЫХ УСЛУГ № {smeta_appendix}</h1>
            <table class="meta"><tr><td style="text-align: left;">г. Москва</td><td style="text-align: right;">{smeta_date_to_use} г.</td></tr></table>
            <p>Мы, нижеподписавшиеся, представитель Исполнителя <strong>{company}</strong> в лице {director_pos} {director}, с одной стороны, и представитель Заказчика <strong>{customer_name}</strong> в лице {customer_pos} {customer_director}, с другой стороны, составили настоящий Акт о том, что Услуги по Договору № {dogovor_number} от {date_to_use} выполнены в полном объеме и в срок.</p>
            <table><tr><th style="text-align:center; width: 5%;">№</th><th style="width: 40%;">Наименование услуги</th><th style="text-align:center; width: 10%;">Ед.</th><th style="text-align:center; width: 10%;">Кол-во</th><th style="text-align:right; width: 15%;">Цена</th><th style="text-align:right; width: 15%;">Сумма</th></tr>{rows}<tr><td colspan="5" style="text-align:right;font-weight:bold;">Всего к оплате:</td><td style="text-align:right;font-weight:bold;">{format_money(total_price)}</td></tr></table>
            <p><strong>Всего наименований {len(services)}, на сумму {format_money(total_price)} руб.</strong> {nds_text}.</p>
            <p>Претензий по объему, качеству и срокам оказания Услуг Заказчик не имеет.</p>
            <table style="width: 100%; border: none; margin-top: 40px; text-indent: 0;">
                <tr>
                    <td style="border: none; width: 50%; vertical-align: top; padding-right: 10px;"><strong>Исполнитель:</strong><br>{company}<br>ИНН: {inn}{kpp_str}<br>Адрес: {address}<br><br>{director_pos_nom}<br><br>_______________ / {director} /<br>М.П.</td>
                    <td style="border: none; width: 50%; vertical-align: top; padding-left: 10px;"><strong>Заказчик:</strong><br>{customer_name}<br>ИНН: {customer_inn}{cust_kpp_str}<br>Адрес: {customer_address}<br><br>{customer_pos_nom}<br><br>_______________ / {customer_director} /<br>М.П.</td>
                </tr>
            </table>
            </body></html>"""
            pisa.CreatePDF(html, dest=buffer)

        # --- СЧЕТ ---
        elif template == "invoice":
            rows = "".join([f"<tr><td style='text-align:center;'>{i+1}</td><td>{s['name']}</td><td style='text-align:center;'>{s.get('unit', 'усл.')}</td><td style='text-align:center;'>{s['qty']}</td><td style='text-align:right;'>{format_money(float(s['price']))}</td><td style='text-align:right;'>{format_money(float(s['price'])*int(s['qty']))}</td></tr>" for i, s in enumerate(services)])
            kpp_str = f", КПП: {kpp}" if kpp else ""
            cust_kpp_str = f", КПП: {customer_kpp}" if customer_kpp else ""
            
            bank_table = f"""
            <table style="width: 100%; text-indent: 0; font-size: 10pt; margin-bottom: 20px;">
                <tr><td style="border: 1px solid #000; padding: 5px; width: 15%;">Банк получателя:</td><td style="border: 1px solid #000; padding: 5px;" colspan="3">{bank_name or "____________________"}</td></tr>
                <tr><td style="border: 1px solid #000; padding: 5px;">БИК:</td><td style="border: 1px solid #000; padding: 5px; width: 35%;">{bik or "__________"}</td><td style="border: 1px solid #000; padding: 5px; width: 15%;">Сч. №:</td><td style="border: 1px solid #000; padding: 5px;">{ks or "____________________"}</td></tr>
                <tr><td style="border: 1px solid #000; padding: 5px;">Получатель:</td><td style="border: 1px solid #000; padding: 5px;" colspan="3">{company}<br>ИНН {inn}{kpp_str}</td></tr>
                <tr><td style="border: 1px solid #000; padding: 5px;">Р/с:</td><td style="border: 1px solid #000; padding: 5px;" colspan="3">{rs or "____________________"}</td></tr>
            </table>
            """
            html = f"""<html><head><meta charset="utf-8"><style>{CSS_STYLES}</style></head><body>
            {header_html}
            {bank_table}
            <h1 class="title">Счет на оплату № {dogovor_number} от {smeta_date_to_use} г.</h1>
            <table class="meta" style="margin-bottom: 15px;">
                <tr><td style="text-align: left;"><strong>Поставщик (Исполнитель):</strong><br>{company}, ИНН {inn}{kpp_str}, {address}</td></tr>
                <tr><td style="text-align: left; padding-top: 5px;"><strong>Покупатель (Заказчик):</strong><br>{customer_name}, ИНН {customer_inn}{cust_kpp_str}, {customer_address}</td></tr>
                <tr><td style="text-align: left; padding-top: 5px;"><strong>Основание:</strong> Договор № {dogovor_number} от {date_to_use} г.</td></tr>
            </table>
            <table>
                <tr><th style="text-align:center; width: 5%;">№</th><th style="width: 45%;">Наименование</th><th style="text-align:center; width: 10%;">Ед.</th><th style="text-align:center; width: 10%;">Кол-во</th><th style="text-align:right; width: 15%;">Цена</th><th style="text-align:right; width: 15%;">Сумма</th></tr>
                {rows}
                <tr><td colspan="5" style="text-align:right;font-weight:bold;">Итого:</td><td style="text-align:right;font-weight:bold;">{format_money(total_price)}</td></tr>
                <tr><td colspan="5" style="text-align:right;font-weight:bold;">Всего к оплате:</td><td style="text-align:right;font-weight:bold;">{format_money(total_price)}</td></tr>
            </table>
            <table style="width: 100%; border: none; margin-top: 40px; text-indent: 0;">
                <tr>
                    <td style="border: none; width: 50%; vertical-align: top; padding-right: 10px;"><strong>Руководитель:</strong><br><br><br>_______________ / {director} /<br><br>М.П.</td>
                    <td style="border: none; width: 50%; vertical-align: top; padding-left: 10px;"><strong>Главный бухгалтер:</strong><br><br><br>_______________ / {director} /</td>
                </tr>
            </table>
            </body></html>"""
            pisa.CreatePDF(html, dest=buffer)

        buffer.seek(0)

        if chat_id:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            files = {'document': ('document.pdf', buffer.getvalue(), 'application/pdf')}
            data = {'chat_id': chat_id, 'caption': 'Ваш документ готов!'}
            try:
                response = requests.post(url, files=files, data=data)
                if response.status_code == 200:
                    return {"status": "ok", "message": "Отправлено в ТГ"}
                else:
                    return JSONResponse(status_code=500, content={"status": "error", "message": f"Ошибка ТГ: {response.text}"})
            except Exception as e:
                return JSONResponse(status_code=500, content={"status": "error", "message": f"Ошибка ТГ: {str(e)}"})
        else:
            return {"status": "error", "message": "Нет chat_id"}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
