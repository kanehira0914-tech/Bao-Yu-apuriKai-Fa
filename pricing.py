from datetime import datetime, timedelta
from typing import Dict, Tuple

HOURLY_RATES = {
    "一時預かり保育": 3000,
    "ベビーシッター（施設型）": 3000,
    "ベビーシッター（自宅派遣型）": 3600,
    "レンタルルーム": 3000,
    "その他": 3000,
}

EXTENSION_RATE_PER_30MIN = 1500
FACILITY_FEE = 550
CANCEL_FEE_RATE = 0.5

def parse_time(time_str: str) -> datetime:
    time_str = time_str.replace('：', ':').strip()
    try:
        return datetime.strptime(time_str, "%H:%M")
    except:
        try:
            return datetime.strptime(time_str, "%H%M")
        except:
            return datetime.now()

def calculate_duration_hours(start_time: str, end_time: str) -> float:
    start = parse_time(start_time)
    end = parse_time(end_time)
    
    if end < start:
        end = end + timedelta(days=1)
    
    duration = (end - start).total_seconds() / 3600
    return round(duration, 2)

def calculate_extension_fee(
    scheduled_end: str,
    actual_end: str
) -> Tuple[int, int]:
    if not actual_end:
        return 0, 0
    
    scheduled = parse_time(scheduled_end)
    actual = parse_time(actual_end)
    
    if actual <= scheduled:
        return 0, 0
    
    extension_minutes = int((actual - scheduled).total_seconds() / 60)
    
    units = (extension_minutes + 29) // 30
    extension_fee = units * EXTENSION_RATE_PER_30MIN
    
    return extension_minutes, extension_fee

def calculate_total_price(
    service_category: str,
    base_price: int,
    facility_fee: int,
    option_price: int,
    extension_fee: int = 0,
    transport_fee: int = 0,
    discount1_amount: int = 0,
    discount2_amount: int = 0,
    additional_fee: int = 0,
    is_cancelled: bool = False,
    include_facility_fee: bool = False
) -> Dict:
    result = {
        "base_price": base_price,
        "facility_fee": 0,
        "option_price": option_price,
        "extension_fee": extension_fee,
        "transport_fee": transport_fee,
        "discount1_amount": discount1_amount,
        "discount2_amount": discount2_amount,
        "additional_fee": additional_fee,
        "total": 0,
    }
    
    if is_cancelled:
        result["base_price"] = int(base_price * CANCEL_FEE_RATE)
        result["option_price"] = 0
        result["extension_fee"] = 0
        result["transport_fee"] = 0
        result["total"] = result["base_price"]
        return result
    
    if service_category == "一時預かり保育":
        if include_facility_fee:
            result["facility_fee"] = FACILITY_FEE
        result["transport_fee"] = 0
    
    elif service_category == "ベビーシッター（施設型）":
        result["facility_fee"] = 0
        result["transport_fee"] = 0
    
    elif service_category == "ベビーシッター（自宅派遣型）":
        result["facility_fee"] = 0
    
    result["total"] = (
        result["base_price"] +
        result["facility_fee"] +
        result["option_price"] +
        result["extension_fee"] +
        result["transport_fee"] +
        result["additional_fee"] -
        result["discount1_amount"] -
        result["discount2_amount"]
    )
    
    return result

def needs_certification(service_category: str) -> bool:
    return service_category in [
        "ベビーシッター（施設型）",
        "ベビーシッター（自宅派遣型）"
    ]

def get_hourly_rate(service_category: str) -> int:
    return HOURLY_RATES.get(service_category, 3000)
