from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from datetime import datetime
import os
from typing import Dict, List
from pricing import needs_certification

FONT_PATH = "fonts/ipaexg.ttf"
FONT_NAME = "IPAexGothic"

def register_font():
    if os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return True
        except:
            return False
    return False

COMPANY_INFO = {
    "name": "一般社団法人ひよこルーム こぐまハウス",
    "postal_code": "〒152-0002",
    "address": "東京都目黒区目黒本町 6-21-10",
    "phone": "03-6451-2771",
    "representative": "由良 清湖",
}

def generate_receipt_pdf(
    reservation: Dict,
    output_path: str = None
) -> str:
    if not register_font():
        raise Exception("日本語フォントの読み込みに失敗しました")
    
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        child_name = reservation.get('child_name', 'unknown').replace(' ', '_')
        output_path = f"receipts/{timestamp}_{child_name}.pdf"
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else "receipts", exist_ok=True)
    
    c = canvas.Canvas(output_path, pagesize=A4)
    
    c.setTitle("領収証 兼 要件証明書")
    c.setAuthor(COMPANY_INFO['name'])
    c.setSubject("ベビーシッター利用支援事業 領収証")
    c.setCreator("こぐまハウス業務支援システム")
    c.setProducer("ReportLab PDF Library")
    
    width, height = A4
    
    y = height - 30*mm
    
    c.setFont(FONT_NAME, 12)
    c.drawString(20*mm, y, "領収証 兼 ベビーシッター利用支援事業（一時預かり利用支援）補助事業ベビーシッター要件証明書")
    
    y -= 15*mm
    c.setFont(FONT_NAME, 10)
    
    c.drawString(140*mm, y, f"発行日　　{datetime.now().strftime('%Y年%m月%d日')}")
    y -= 7*mm
    c.drawString(140*mm, y, f"会社名　　{COMPANY_INFO['name']}")
    y -= 7*mm
    c.drawString(140*mm, y, f"所在地　　{COMPANY_INFO['postal_code']}")
    y -= 5*mm
    c.drawString(155*mm, y, f"{COMPANY_INFO['address']}")
    y -= 7*mm
    c.drawString(140*mm, y, f"電話番号　{COMPANY_INFO['phone']}")
    y -= 7*mm
    c.drawString(140*mm, y, f"代表者　　{COMPANY_INFO['representative']}")
    
    y = height - 55*mm
    address = reservation.get('address', '')
    c.drawString(20*mm, y, address)
    
    y -= 10*mm
    guardian_name = reservation.get('guardian_name', '')
    if not guardian_name or str(guardian_name).lower() == 'nan':
        guardian_name = reservation.get('child_name', '')
    c.setFont(FONT_NAME, 14)
    c.drawString(20*mm, y, f"{guardian_name}　様")
    
    y -= 10*mm
    c.setFont(FONT_NAME, 10)
    c.drawString(20*mm, y, "名前")
    c.drawString(60*mm, y, "かな")
    
    y -= 8*mm
    child_name = reservation.get('child_name', '')
    child_name_kana = reservation.get('child_name_kana', '')
    c.setFont(FONT_NAME, 12)
    c.drawString(20*mm, y, child_name)
    c.drawString(60*mm, y, child_name_kana)
    
    y -= 20*mm
    c.setFont(FONT_NAME, 8)
    
    headers = ["利用日時", "担当", "要件証明日", "要件", "施設利用料", "保育料", "交通費", "割引①", "割引②", "追加", "合計"]
    x_positions = [15, 50, 70, 90, 115, 130, 145, 158, 170, 182, 192]
    
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(15*mm, y + 5*mm, 200*mm, y + 5*mm)
    
    for i, header in enumerate(headers):
        c.drawString(x_positions[i]*mm, y, header)
    
    c.line(15*mm, y - 3*mm, 200*mm, y - 3*mm)
    
    y -= 12*mm
    c.setFont(FONT_NAME, 8)
    
    service_category = reservation.get('service_category', '')
    show_certification = needs_certification(service_category)
    
    datetime_str = reservation.get('reservation_datetime', '')
    start_time = reservation.get('start_time', '')
    end_time = reservation.get('end_time', '')
    date_part = reservation.get('reservation_date', '')
    
    if start_time and end_time:
        usage_time = f"{date_part} {start_time} - {end_time}"
    else:
        usage_time = datetime_str.replace('\n', ' ')
    
    cert_date = reservation.get('certification_date', '') or ''
    cert_type = reservation.get('certification_type', '') or ''
    
    # 担当者に紐づく要件証明情報の自動補完（予約データにない場合）
    if show_certification and staff_name:
        from database import get_staff_list
        staff_list = get_staff_list(reservation.get('facility_id', 'house'))
        for s in staff_list:
            if s['name'] == staff_name:
                if not cert_date:
                    cert_date = s.get('certification_date', '')
                if not cert_type:
                    cert_type = s.get('certification_type', '')
                break

    row_data = [
        usage_time[:20],
        staff_name[:6] if staff_name else '',
        cert_date[:12] if cert_date else '',
        cert_type[:12] if cert_type else '',
        f"¥{facility_fee:,}" if facility_fee else '',
        f"¥{base_price:,}",
        f"¥{transport_fee:,}" if transport_fee else '',
        discount1[:6] if discount1 else '',
        discount2[:6] if discount2 else '',
        f"¥{additional_fee:,}" if additional_fee else '',
        f"¥{total_amount:,}",
    ]
    
    for i, data in enumerate(row_data):
        c.drawString(x_positions[i]*mm, y, str(data))
    
    y -= 15*mm
    c.line(15*mm, y, 200*mm, y)
    
    y -= 20*mm
    c.setFont(FONT_NAME, 12)
    c.drawString(140*mm, y, f"合計")
    c.drawString(170*mm, y, f"¥{total_amount:,}")
    
    c.save()
    return output_path


def generate_bulk_receipts(reservations: List[Dict]) -> List[str]:
    generated_files = []
    for res in reservations:
        try:
            path = generate_receipt_pdf(res)
            generated_files.append(path)
        except Exception as e:
            print(f"Error generating PDF for {res.get('child_name', 'unknown')}: {e}")
    return generated_files
