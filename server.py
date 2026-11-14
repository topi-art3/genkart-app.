import subprocess
import sys
import os

# --- АВАРИЙНАЯ УСТАНОВКА БИБЛИОТЕК ---
# Этот блок заставит Render установить всё необходимое, даже если он проигнорирует requirements.txt
try:
    import fastapi
    import uvicorn
    import fpdf
    import sqlalchemy
    import num2words
    import xhtml2pdf
    import requests
except ImportError:
    print("Установка недостающих библиотек...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "fpdf2", "python-multipart", "sqlalchemy", "num2words", "xhtml2pdf", "requests"])
    print("Библиотеки установлены!")

# --- ОСНОВНОЙ КОД ---
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import io
import json
from datetime import datetime
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

# Берем токен из переменной окружения Render (Environment), 
# если её нет, используем токен по умолчанию (тот, что ты скинула)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8888816541:AAHr3KYdyGi3au_9xQQ83p7NVvI9A1Yp_xE")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def decline_fio(fio):
    if not fio: return ""
    words = fio.split()
    res = []
    for word in words:
        if word.endswith("."): res.append(word)
        elif word.endswith("а"): res.append(word[:-1] + "ы")
        elif word.endswith("я"): res.append(word[:-1] + "и")
        elif word.endswith("на") or word.endswith("ва"): res.append(word + "ой")
        else: res.append(word + "а")
    return " ".join(res)

def get_signature_fio(fio):
    parts = fio.split()
    if len(parts) >= 2: return f"{parts[1]} {parts[0]}"
    return fio

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

CSS_STYLES = """
@page { size: a4; margin: 20mm 15mm 20mm 30mm; }
@font-face { font-family: "PTSans"; src: url("https://github.com/google/fonts/raw/main/ofl/ptsans/PT_Sans-Web-Regular.ttf"); }
body { font-family: "PTSans", sans-serif; font-size: 11pt; line-height: 1.35; text-align: justify; color: #000; text-indent: 1.25cm; }
h1.title { text-align: center; font-size: 14pt; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; text-indent: 0; }
.meta { width: 100%; margin-bottom: 20px; text-indent: 0; }
.meta td { border: none; padding: 0; }
.section-title { font-weight: bold; margin-top: 15px; margin-bottom: 10px; text-indent: 0; }
table { width: 100%; border-collapse: collapse; margin-top: 15px; text-indent: 0; }
th, td { border: 1px solid #000; padding: 6px; text-align: left; }
.header-info { margin-bottom: 20px; font-size: 10pt; text-align: left; text-indent: 0; }
.signature-block { margin-top: 30px; text-indent: 0; }
.list-item { text-indent: 0; margin-bottom: 5px; }
"""

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

# --- ЭНДПОИНТЫ API ---
@app.get("/")
def read_root(): return {"status": "ok"}

@app.get("/get-profile")
async def get_profile(chat_id: str):
    db = SessionLocal()
    profile = db.query(Profile).filter(Profile.chat_id == chat_id).first()
    db.close()
    if profile:
        return {"status": "ok", "company": profile.company, "inn": profile.inn, "kpp": profile.kpp, "address": profile.address, "contacts": profile.contacts, "tax_mode": profile.tax_mode, "director": profile.director, "director_pos": profile.director_pos, "director_pos_nom": profile.director_pos_nom, "bank_name": profile.bank_name, "bik": profile.bik, "rs": profile.rs, "ks": profile.ks, "logo": profile.logo}
    return {"status": "not_found"}

@app.post("/save-profile")
async def save_profile(
    chat_id: str = Form(...), company: str = Form(...), inn: str = Form(...), kpp: str = Form(""), address: str = Form(...), 
    contacts: str = Form(...), tax_mode: str = Form("usn"), director: str = Form(...), director_pos: str = Form(...), director_pos_nom: str = Form(...),
    bank_name: str = Form(None), bik: str = Form(None), rs: str = Form(None), ks: str = Form(None), logo: str = Form(None)
):
    db = SessionLocal()
    try:
        profile = db.query(Profile).filter(Profile.chat_id == chat_id).first()
        if profile:
            profile.company, profile.inn, profile.kpp, profile.address, profile.contacts = company, inn, kpp, address, contacts
            profile.tax_mode = tax_mode
            profile.director, profile.director_pos, profile.director_pos_nom = director, director_pos, director_pos_nom
            if bank_name: profile.bank_name = bank_name
            if bik: profile.bik = bik
            if rs: profile.rs = rs
            if ks: profile.ks = ks
            if logo: profile.logo = logo
        else:
            db.add(Profile(chat_id=chat_id, company=company, inn=inn, kpp=kpp, address=address, contacts=contacts, tax_mode=tax_mode, director=director, director_pos=director_pos, director_pos_nom=director_pos_nom, bank_name=bank_name, bik=bik, rs=rs, ks=ks, logo=logo))
        db.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}
    finally: db.close()

@app.post("/generate-doc")
async def generate_doc(
    template: str = Form("kp"), company: str = Form("ООО Ваша компания"), inn: str = Form("0000000000"), kpp: str = Form(""), 
    address: str = Form("г. Москва"), contacts: str = Form("+7 (999) 999-99-99"), tax_mode: str = Form("usn"),
    director: str = Form("Иванов И.И."), director_pos: str = Form("Генерального директора"), director_pos_nom: str = Form("Генеральный директор"),
    services_json: str = Form("[]"), term: str = Form("30"), dogovor_number: str = Form("Б/Н"), dogovor_date: str = Form(""), 
    customer_name: str = Form("ООО Заказчик"), customer_inn: str = Form("1111111111"), customer_kpp: str = Form(""), customer_address: str = Form("г. Москва"), 
    customer_director: str = Form("Петров П.П."), customer_pos: str = Form("Генерального директора"), customer_pos_nom: str = Form("Генеральный директор"), customer_pos_dat: str = Form("Генеральному директору"),
    smeta_date: str = Form(""), smeta_appendix: str = Form("1"), chat_id: str = Form(None), logo: str = Form(None),
    bank_name: str = Form(None), bik: str = Form(None), rs: str = Form(None), ks: str = Form(None)
):
    try:
        services = json.loads(services_json)
        total_price = sum(float(s['price']) * int(s['qty']) for s in services)
        current_date = datetime.now().strftime("%d.%m.%Y")
        date_to_use = dogovor_date if dogovor_date else current_date
        smeta_date_to_use = smeta_date if smeta_date else current_date
        
        nds_text = "НДС не облагается на основании п. 2 ст. 346.11 НК РФ (УСН)"
        if tax_mode == "osno":
            nds_text = "В том числе НДС 22%"

        rows_html = ""
        for i, s in enumerate(services, 1):
            sum_s = float(s['price']) * int(s['qty'])
            rows_html += f"<tr><td align='center'>{i}</td><td>{s['name']}</td><td align='center'>{s.get('unit', 'шт')}</td><td align='center'>{s['qty']}</td><td align='right'>{format_money(float(s['price']))}</td><td align='right'>{format_money(sum_s)}</td></tr>"

        header = get_header_html(company, inn, kpp, address, contacts, logo)
        
        html_content = ""

        if template == "kp":
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            {header}
            <div style="text-align: right; margin-bottom: 10px;">Исх. № {dogovor_number} от {date_to_use} г.</div>
            <h1 class="title">Коммерческое предложение<br>на оказание услуг</h1>
            <p style="text-indent: 0;">Уважаемый клиент! {company} предлагает вам следующие услуги:</p>
            <table>
                <tr><th>№</th><th>Наименование услуги</th><th>Ед.</th><th>Срок</th><th>Стоимость</th></tr>
                {''.join([f"<tr><td align='center'>{i}</td><td>{s['name']}</td><td align='center'>{s.get('unit', 'усл.')}</td><td align='center'>{term} дн.</td><td align='right'>{format_money(float(s['price']) * int(s['qty']))} руб.</td></tr>" for i, s in enumerate(services, 1)])}
                <tr><td colspan="4" align="right"><b>Итого:</b></td><td align="right"><b>{format_money(total_price)} руб.</b></td></tr>
            </table>
            <p style="text-indent: 0; text-align: right;">({nds_text})</p>
            <div class="list-item">1. КП действительно 14 дней.</div>
            <div class="list-item">2. Оплата 100% постоплата.</div>
            <div class="list-item">3. Не является офертой (ст. 435 ГК РФ).</div>
            <div class="signature-block">
                <p>С уважением,</p>
                <p>{director_pos_nom}<br>{company}</p>
                <br><br>
                <table style="width: 100%; border: none;"><tr>
                    <td style="border: none; width: 50%;">__________________ / {director} /</td>
                </tr></table>
            </div>
            </body></html>
            """

        elif template == "smeta":
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            <p style="text-align: right; text-indent: 0;">Приложение № {smeta_appendix} к Договору № {dogovor_number} от {date_to_use}</p>
            <h1 class="title">Смета № {smeta_appendix}</h1>
            <table>
                <tr><th>№</th><th>Наименование</th><th>Ед.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
                {rows_html}
                <tr><td colspan="5" align="right"><b>Всего:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
            </table>
            <p>Всего наименований {len(services)}, на сумму {format_money(total_price)} руб. {nds_text}.</p>
            <div class="signature-block">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="border: none; width: 50%;">Исполнитель:<br><b>{company}</b><br><br>__________________ / {director} /<br>М.П.</td>
                        <td style="border: none; width: 50%;">Заказчик:<br><b>{customer_name}</b><br><br>__________________ / {customer_director} /<br>М.П.</td>
                    </tr>
                </table>
            </div>
            </body></html>
            """

        elif template == "schet":
            bank_info = ""
            if bank_name:
                bank_info = f"""
                <div style="margin-top: 20px; text-indent: 0; font-size: 10pt;">
                    <b>Банковские реквизиты для оплаты:</b><br>
                    Банк: {bank_name}<br>
                    БИК: {bik}<br>
                    Расчётный счет: {rs}<br>
                    Корр. счет: {ks}
                </div>
                """
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            {header}
            <h1 class="title">Счет на оплату № {dogovor_number} от {date_to_use} г.</h1>
            <p style="text-indent: 0;">
                <b>Поставщик (Исполнитель):</b><br>{company}, ИНН {inn}, {address}<br><br>
                <b>Покупатель (Заказчик):</b><br>{customer_name}, ИНН {customer_inn}, {customer_address}
            </p>
            <table>
                <tr><th>№</th><th>Наименование</th><th>Ед.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
                {rows_html}
                <tr><td colspan="5" align="right"><b>Итого:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
                <tr><td colspan="5" align="right">{nds_text}</td><td align="right">0,00</td></tr>
                <tr><td colspan="5" align="right"><b>Всего к оплате:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
            </table>
            <p>Всего наименований {len(services)}, на сумму {format_money(total_price)} руб.<br>
            Сумма прописью: {num2words_rub(total_price)}.</p>
            {bank_info}
            <div class="signature-block">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="border: none; width: 50%;">Руководитель:<br><br>__________________ / {director} /</td>
                        <td style="border: none; width: 50%;">Главный бухгалтер:<br><br>__________________ / {director} /</td>
                    </tr>
                </table>
                <p>М.П.</p>
            </div>
            </body></html>
            """

        elif template == "akt":
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            <h1 class="title">Акт сдачи-приемки оказанных услуг № {smeta_appendix}</h1>
            <table class="meta"><tr><td>г. Москва</td><td align="right">{date_to_use} г.</td></tr></table>
            <p>Мы, нижеподписавшиеся, представитель Исполнителя <b>{company}</b> в лице {director_pos} <b>{director}</b>, с одной стороны, и представитель Заказчика <b>{customer_name}</b> в лице {customer_pos} <b>{customer_director}</b>, с другой стороны, составили настоящий Акт о том, что Услуги по Договору № {dogovor_number} от {date_to_use} выполнены в полном объеме и в срок.</p>
            <table>
                <tr><th>№</th><th>Наименование услуги</th><th>Ед.</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
                {rows_html}
                <tr><td colspan="5" align="right"><b>Всего к оплате:</b></td><td align="right"><b>{format_money(total_price)}</b></td></tr>
            </table>
            <p>Всего наименований {len(services)}, на сумму {format_money(total_price)} руб. {nds_text}.</p>
            <p>Претензий по объему, качеству и срокам оказания Услуг Заказчик не имеет.</p>
            <div class="signature-block">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="border: none; width: 50%;">Исполнитель:<br><b>{company}</b><br>ИНН: {inn}<br>Адрес: {address}<br><br>{director_pos_nom}<br><br>__________________ / {director} /<br>М.П.</td>
                        <td style="border: none; width: 50%;">Заказчик:<br><b>{customer_name}</b><br>ИНН: {customer_inn}<br>Адрес: {customer_address}<br><br>{customer_pos_nom}<br><br>__________________ / {customer_director} /<br>М.П.</td>
                    </tr>
                </table>
            </div>
            </body></html>
            """

        elif template == "dogovor":
            html_content = f"""
            <html><head><style>{CSS_STYLES}</style></head><body>
            <h1 class="title">Договор оказания услуг № {dogovor_number}</h1>
            <table class="meta"><tr><td>г. Москва</td><td align="right">{date_to_use} г.</td></tr></table>
            <p><b>{company}</b>, в лице {director_pos} <b>{director}</b>, действующего на основании Устава, именуемое в дальнейшем «Исполнитель», с одной стороны, и <b>{customer_name}</b> (ИНН: {customer_inn}, адрес: {customer_address}), именуемое в дальнейшем «Заказчик», в лице {customer_pos} <b>{customer_director}</b>, с другой стороны, заключили настоящий Договор о нижеследующем:</p>
            
            <div class="section-title">1. ПРЕДМЕТ ДОГОВОРА</div>
            <p>1.1. Исполнитель обязуется по заданию Заказчика оказать услуги (далее — «Услуги»), а Заказчик обязуется принять и оплатить эти Услуги.</p>
            <p>1.2. Перечень, объем и стоимость Услуг определяются в Смете (Приложение № 1), являющейся неотъемлемой частью настоящего Договора.</p>
            
            <div class="section-title">2. СТОИМОСТЬ УСЛУГ И ПОРЯДОК РАСЧЕТОВ</div>
            <p>2.1. Общая стоимость Услуг по настоящему Договору составляет {format_money(total_price)} руб., {nds_text}.</p>
            <p>2.2. Оплата производится Заказчиком путем перечисления 100% стоимости Услуг на расчетный счет Исполнителя в течение 3 (трех) банковских дней с даты подписания Сторонами Акта сдачи-приемки оказанных услуг и выставления счета.</p>
            
            <div class="section-title">3. ОТВЕТСТВЕННОСТЬ СТОРОН</div>
            <p>3.1. За неисполнение или ненадлежащее исполнение обязательств по настоящему Договору Стороны несут ответственность в соответствии с действующим законодательством РФ.</p>
            
            <div class="section-title">4. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ</div>
            <p>4.1. Настоящий Договор вступает в силу с момента его подписания и действует до полного исполнения Сторонами своих обязательств.</p>
            <p>4.2. Договор составлен в двух экземплярах, имеющих одинаковую юридическую силу, по одному для каждой из Сторон.</p>
            
            <div class="section-title">5. АДРЕСА, РЕКВИЗИТЫ И ПОДПИСИ СТОРОН</div>
            <div class="signature-block">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="border: none; width: 50%;">Исполнитель:<br><b>{company}</b><br>ИНН: {inn}<br>Адрес: {address}<br><br>{director_pos_nom}<br><br>__________________ / {director} /</td>
                        <td style="border: none; width: 50%;">Заказчик:<br><b>{customer_name}</b><br>ИНН: {customer_inn}<br>Адрес: {customer_address}<br><br>{customer_pos_nom}<br><br>__________________ / {customer_director} /</td>
                    </tr>
                </table>
            </div>
            </body></html>
            """

        pdf_buffer = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
        pdf_buffer.seek(0)

        if chat_id:
            file_name = f"{template}_{current_date.replace('.', '_')}.pdf"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            files = {'document': (file_name, pdf_buffer, 'application/pdf')}
            data = {'chat_id': chat_id, 'caption': f'Ваш документ ({template.upper()}) готов! 📄'}
            
            response = requests.post(url, files=files, data=data)
            if response.status_code != 200:
                print(f"Ошибка отправки в ТГ: {response.text}")
                
            return {"status": "ok", "message": "Отправлено в Telegram"}

        return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=document.pdf"})

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
