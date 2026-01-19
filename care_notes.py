from datetime import datetime
from typing import List, Dict

RECORD_TYPES = {
    "temperature": "体温",
    "temperature_1": "体温①",
    "temperature_2": "体温②",
    "lunch": "昼食",
    "snack": "おやつ",
    "dinner": "夕食",
    "milk": "ミルク",
    "milk_1": "ミルク①",
    "milk_2": "ミルク②",
    "milk_3": "ミルク③",
    "stool": "排便",
    "stool_1": "排便①",
    "stool_2": "排便②",
    "stool_3": "排便③",
    "nap": "お昼寝",
    "nap_1": "お昼寝①",
    "nap_2": "お昼寝②",
    "nap_3": "お昼寝③",
    "diaper_wet": "おしっこ",
    "other": "その他",
    "meal_start": "食事開始",
    "meal_end": "食事終了",
    "sleep_start": "お昼寝開始",
    "sleep_end": "お昼寝終了",
    "diaper_solid": "排泄（うんち）",
}

def format_time(iso_time: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_time)
        return dt.strftime("%H:%M")
    except:
        return ""

def generate_care_summary(care_records: List[Dict], child_name: str) -> str:
    if not care_records:
        return f"{child_name}ちゃんは本日も元気に過ごされました。"
    
    temperatures = []
    meals = []
    milks = []
    stools = []
    naps = []
    diapers = []
    others = []
    
    for record in sorted(care_records, key=lambda x: x.get('record_time', '')):
        record_type = record.get('record_type', '')
        record_time = format_time(record.get('record_time', ''))
        details = record.get('details', '') or ''
        
        if record_type.startswith('temperature'):
            temperatures.append(details)
        elif record_type in ['lunch', 'dinner']:
            meals.append(details)
        elif record_type == 'snack':
            meals.append(details)
        elif record_type == 'milk' or record_type.startswith('milk_'):
            milks.append(details)
        elif record_type.startswith('stool'):
            stools.append(details)
        elif record_type == 'nap' or record_type.startswith('nap_'):
            naps.append(details)
        elif record_type == 'diaper_wet':
            diapers.append(details or record_time)
        elif record_type == 'other':
            others.append(details)
    
    parts = []
    
    suffix = "ちゃん" if child_name else ""
    parts.append(f"【本日のご様子】{child_name}{suffix}")
    parts.append("")
    
    if temperatures:
        parts.append(f"🌡️ 体温: {', '.join(temperatures)}")
    
    if meals:
        parts.append(f"🍚 食事: {', '.join(meals)}")
    
    if milks:
        parts.append(f"🍼 ミルク: {', '.join(milks)}")
    
    if naps:
        parts.append(f"😴 お昼寝: {', '.join(naps)}")
    
    if stools:
        parts.append(f"💩 排便: {', '.join(stools)}")
    
    if diapers:
        parts.append(f"💧 おしっこ: {len(diapers)}回")
    
    if others:
        parts.append(f"📝 その他: {', '.join(others)}")
    
    parts.append("")
    parts.append("本日もありがとうございました。")
    
    return "\n".join(parts)

def get_record_type_label(record_type: str) -> str:
    return RECORD_TYPES.get(record_type, record_type)
