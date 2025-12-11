from datetime import datetime
from typing import List, Dict

RECORD_TYPES = {
    "meal_start": "食事開始",
    "meal_end": "食事終了",
    "sleep_start": "お昼寝開始",
    "sleep_end": "お昼寝終了",
    "diaper_wet": "排泄（おしっこ）",
    "diaper_solid": "排泄（うんち）",
    "milk": "ミルク",
    "snack": "おやつ",
    "play": "遊び",
    "other": "その他",
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
    
    meals = []
    sleeps = []
    diapers = []
    others = []
    
    sleep_start = None
    meal_start = None
    
    for record in sorted(care_records, key=lambda x: x.get('record_time', '')):
        record_type = record.get('record_type', '')
        record_time = format_time(record.get('record_time', ''))
        details = record.get('details', '')
        
        if record_type == 'meal_start':
            meal_start = record_time
        elif record_type == 'meal_end':
            if meal_start:
                meals.append(f"{meal_start}〜{record_time}")
            else:
                meals.append(record_time)
            meal_start = None
        elif record_type == 'sleep_start':
            sleep_start = record_time
        elif record_type == 'sleep_end':
            if sleep_start:
                sleeps.append(f"{sleep_start}〜{record_time}")
            else:
                sleeps.append(record_time)
            sleep_start = None
        elif record_type in ['diaper_wet', 'diaper_solid']:
            diapers.append((record_time, RECORD_TYPES.get(record_type, record_type)))
        elif record_type == 'milk':
            others.append(f"ミルク({record_time}){details}")
        elif record_type == 'snack':
            others.append(f"おやつ({record_time}){details}")
        else:
            if details:
                others.append(f"{details}({record_time})")
    
    parts = []
    
    suffix = "ちゃん" if child_name else ""
    parts.append(f"【本日のご様子】{child_name}{suffix}")
    parts.append("")
    
    if meals:
        parts.append(f"🍚 食事: {', '.join(meals)}")
        parts.append("　しっかり食べられました。")
    
    if sleeps:
        parts.append(f"😴 お昼寝: {', '.join(sleeps)}")
        parts.append("　ぐっすり眠れました。")
    
    if diapers:
        diaper_summary = []
        wet_count = sum(1 for _, t in diapers if 'おしっこ' in t)
        solid_count = sum(1 for _, t in diapers if 'うんち' in t)
        if wet_count:
            diaper_summary.append(f"おしっこ{wet_count}回")
        if solid_count:
            diaper_summary.append(f"うんち{solid_count}回")
        parts.append(f"🚽 排泄: {', '.join(diaper_summary)}")
    
    if others:
        parts.append(f"📝 その他: {', '.join(others)}")
    
    parts.append("")
    parts.append("本日もありがとうございました。")
    
    return "\n".join(parts)

def get_record_type_label(record_type: str) -> str:
    return RECORD_TYPES.get(record_type, record_type)
