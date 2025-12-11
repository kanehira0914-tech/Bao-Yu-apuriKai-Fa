from datetime import datetime, timedelta, time, date
from typing import Dict, Tuple, List
import jpholiday

FACILITY_FEE = 550
FACILITY_FEE_SITTER = 2200
CANCEL_FEE_RATE = 0.5

TEMPORARY_CARE_RATES = {
    "weekday": {"normal": 2000, "overtime": 2800},
    "holiday": {"normal": 3200, "overtime": 4000},
}

FACILITY_SITTER_RATES = {
    "weekday": {"normal": 3200, "overtime": 4000},
    "holiday": {"normal": 4000, "overtime": 4500},
}

HOME_SITTER_RATES = {
    "weekday": {"normal": 3500, "overtime": 3800, "early_night": 4000},
    "holiday": {"normal": 3900, "overtime": 4200, "early_night": 4400},
}

SIBLING_DISCOUNT_TEMPORARY = 400
SIBLING_ADDITION_HOME = 1000
HOUSEWORK_OPTION = 1100
SNACK_PRICE = 150

def is_holiday(check_date: date) -> bool:
    if check_date.weekday() >= 5:
        return True
    try:
        if jpholiday.is_holiday(check_date):
            return True
    except:
        pass
    return False

def parse_time(time_str: str) -> datetime:
    time_str = time_str.replace('：', ':').strip()
    try:
        return datetime.strptime(time_str, "%H:%M")
    except:
        try:
            return datetime.strptime(time_str, "%H%M")
        except:
            return datetime.now()

def time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute

def minutes_to_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)

def calculate_duration_hours(start_time: str, end_time: str) -> float:
    start = parse_time(start_time)
    end = parse_time(end_time)
    
    if end < start:
        end = end + timedelta(days=1)
    
    duration = (end - start).total_seconds() / 3600
    return round(duration, 2)

def round_to_unit(minutes: int, unit: int = 30) -> int:
    return ((minutes + unit - 1) // unit) * unit

def calculate_time_segments(
    start_minutes: int,
    end_minutes: int,
    service_type: str
) -> Dict[str, int]:
    if service_type == "一時預かり保育":
        normal_start = 9 * 60
        normal_end = 17 * 60
        segments = {"normal": 0, "overtime": 0}
        
        current = start_minutes
        while current < end_minutes:
            if normal_start <= current < normal_end:
                segment_end = min(end_minutes, normal_end)
                segments["normal"] += segment_end - current
                current = segment_end
            else:
                if current < normal_start:
                    segment_end = min(end_minutes, normal_start)
                else:
                    segment_end = end_minutes
                segments["overtime"] += segment_end - current
                current = segment_end
        
        return segments
    
    elif service_type == "ベビーシッター（施設型）":
        normal_start = 9 * 60
        normal_end = 17 * 60
        segments = {"normal": 0, "overtime": 0}
        
        current = start_minutes
        while current < end_minutes:
            if normal_start <= current < normal_end:
                segment_end = min(end_minutes, normal_end)
                segments["normal"] += segment_end - current
                current = segment_end
            else:
                if current < normal_start:
                    segment_end = min(end_minutes, normal_start)
                else:
                    segment_end = end_minutes
                segments["overtime"] += segment_end - current
                current = segment_end
        
        return segments
    
    elif service_type == "ベビーシッター（自宅派遣型）":
        early_end = 7 * 60
        overtime_morning_end = 9 * 60
        normal_end = 17 * 60
        overtime_evening_end = 20 * 60
        
        segments = {"normal": 0, "overtime": 0, "early_night": 0}
        
        current = start_minutes
        while current < end_minutes:
            if current < early_end:
                segment_end = min(end_minutes, early_end)
                segments["early_night"] += segment_end - current
                current = segment_end
            elif current < overtime_morning_end:
                segment_end = min(end_minutes, overtime_morning_end)
                segments["overtime"] += segment_end - current
                current = segment_end
            elif current < normal_end:
                segment_end = min(end_minutes, normal_end)
                segments["normal"] += segment_end - current
                current = segment_end
            elif current < overtime_evening_end:
                segment_end = min(end_minutes, overtime_evening_end)
                segments["overtime"] += segment_end - current
                current = segment_end
            else:
                segments["early_night"] += end_minutes - current
                current = end_minutes
        
        return segments
    
    return {"normal": end_minutes - start_minutes}

def calculate_auto_fee(
    service_type: str,
    start_time: time,
    end_time: time,
    use_date: date = None,
    is_holiday_manual: bool = None,
    has_sibling: bool = False,
    snack: bool = False,
    lunch_price: int = 0,
    dinner_price: int = 0,
    housework_option: bool = False,
    transport_fee: int = 0
) -> Dict:
    if use_date:
        holiday = is_holiday(use_date)
    elif is_holiday_manual is not None:
        holiday = is_holiday_manual
    else:
        holiday = False
    
    day_type = "holiday" if holiday else "weekday"
    
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    
    total_minutes = end_minutes - start_minutes
    total_hours = total_minutes / 60
    
    segments = calculate_time_segments(start_minutes, end_minutes, service_type)
    
    breakdown = []
    base_fee = 0
    
    if service_type == "一時預かり保育":
        rates = TEMPORARY_CARE_RATES[day_type]
        
        if segments["normal"] > 0:
            normal_hours = segments["normal"] / 60
            normal_fee = int(normal_hours * rates["normal"])
            base_fee += normal_fee
            breakdown.append({
                "item": f"通常時間（9:00-17:00）{segments['normal']}分",
                "amount": normal_fee
            })
        
        if segments["overtime"] > 0:
            overtime_hours = segments["overtime"] / 60
            overtime_fee = int(overtime_hours * rates["overtime"])
            base_fee += overtime_fee
            breakdown.append({
                "item": f"時間外（7:00-9:00/17:00-22:00）{segments['overtime']}分",
                "amount": overtime_fee
            })
        
        facility_fee = FACILITY_FEE
        breakdown.append({"item": "施設利用料", "amount": facility_fee})
        
        sibling_discount = 0
        if has_sibling:
            sibling_discount = int(total_hours * SIBLING_DISCOUNT_TEMPORARY)
            breakdown.append({"item": f"兄弟割引（{total_hours:.1f}時間×△400円）", "amount": -sibling_discount})
    
    elif service_type == "ベビーシッター（施設型）":
        if total_hours < 2:
            breakdown.append({"item": "※最低利用時間は2時間です", "amount": 0})
        
        rates = FACILITY_SITTER_RATES[day_type]
        
        if segments["normal"] > 0:
            normal_hours = segments["normal"] / 60
            normal_fee = int(normal_hours * rates["normal"])
            base_fee += normal_fee
            breakdown.append({
                "item": f"通常時間（9:00-17:00）{segments['normal']}分",
                "amount": normal_fee
            })
        
        if segments["overtime"] > 0:
            overtime_hours = segments["overtime"] / 60
            overtime_fee = int(overtime_hours * rates["overtime"])
            base_fee += overtime_fee
            breakdown.append({
                "item": f"時間外（7:00-9:00/17:00-22:00）{segments['overtime']}分",
                "amount": overtime_fee
            })
        
        facility_fee = FACILITY_FEE_SITTER
        breakdown.append({"item": "施設利用料", "amount": facility_fee})
        sibling_discount = 0
    
    elif service_type == "ベビーシッター（自宅派遣型）":
        if total_hours < 3:
            breakdown.append({"item": "※最低利用時間は3時間です", "amount": 0})
        
        rates = HOME_SITTER_RATES[day_type]
        
        if segments.get("normal", 0) > 0:
            normal_hours = segments["normal"] / 60
            normal_fee = int(normal_hours * rates["normal"])
            base_fee += normal_fee
            breakdown.append({
                "item": f"通常時間（9:00-17:00）{segments['normal']}分",
                "amount": normal_fee
            })
        
        if segments.get("overtime", 0) > 0:
            overtime_hours = segments["overtime"] / 60
            overtime_fee = int(overtime_hours * rates["overtime"])
            base_fee += overtime_fee
            breakdown.append({
                "item": f"時間外（7:00-9:00/17:00-20:00）{segments['overtime']}分",
                "amount": overtime_fee
            })
        
        if segments.get("early_night", 0) > 0:
            early_night_hours = segments["early_night"] / 60
            early_night_fee = int(early_night_hours * rates["early_night"])
            base_fee += early_night_fee
            breakdown.append({
                "item": f"早朝・夜間（〜7:00/20:00〜）{segments['early_night']}分",
                "amount": early_night_fee
            })
        
        facility_fee = 0
        sibling_discount = 0
        
        if has_sibling:
            sibling_addition = int(total_hours * SIBLING_ADDITION_HOME)
            base_fee += sibling_addition
            breakdown.append({"item": f"兄弟加算（{total_hours:.1f}時間×+1,000円）", "amount": sibling_addition})
        
        if housework_option:
            breakdown.append({"item": "家事代行・沐浴オプション", "amount": HOUSEWORK_OPTION})
        
        if transport_fee > 0:
            breakdown.append({"item": "交通費", "amount": transport_fee})
    
    else:
        facility_fee = 0
        sibling_discount = 0
    
    meal_total = 0
    if snack:
        meal_total += SNACK_PRICE
        breakdown.append({"item": "おやつ", "amount": SNACK_PRICE})
    if lunch_price > 0:
        meal_total += lunch_price
        breakdown.append({"item": "昼食", "amount": lunch_price})
    if dinner_price > 0:
        meal_total += dinner_price
        breakdown.append({"item": "夕食", "amount": dinner_price})
    
    total = base_fee + facility_fee + meal_total
    if service_type == "一時預かり保育" and has_sibling:
        total -= sibling_discount
    if service_type == "ベビーシッター（自宅派遣型）":
        if housework_option:
            total += HOUSEWORK_OPTION
        total += transport_fee
    
    return {
        "service_type": service_type,
        "day_type": "土日祝" if holiday else "平日",
        "total_minutes": total_minutes,
        "total_hours": round(total_hours, 2),
        "base_fee": base_fee,
        "facility_fee": facility_fee if service_type != "ベビーシッター（自宅派遣型）" else 0,
        "meal_total": meal_total,
        "sibling_adjustment": -sibling_discount if service_type == "一時預かり保育" else (int(total_hours * SIBLING_ADDITION_HOME) if service_type == "ベビーシッター（自宅派遣型）" and has_sibling else 0),
        "transport_fee": transport_fee if service_type == "ベビーシッター（自宅派遣型）" else 0,
        "housework_option": HOUSEWORK_OPTION if housework_option and service_type == "ベビーシッター（自宅派遣型）" else 0,
        "total": total,
        "breakdown": breakdown
    }

def calculate_extension_fee(
    scheduled_end: str,
    actual_end: str,
    service_type: str = "一時預かり保育",
    is_holiday: bool = False
) -> Tuple[int, int]:
    if not actual_end:
        return 0, 0
    
    scheduled = parse_time(scheduled_end)
    actual = parse_time(actual_end)
    
    if actual <= scheduled:
        return 0, 0
    
    extension_minutes = int((actual - scheduled).total_seconds() / 60)
    
    extension_units = round_to_unit(extension_minutes, 15)
    
    day_type = "holiday" if is_holiday else "weekday"
    
    if service_type == "一時預かり保育":
        rate = TEMPORARY_CARE_RATES[day_type]["overtime"]
    elif service_type == "ベビーシッター（施設型）":
        rate = FACILITY_SITTER_RATES[day_type]["overtime"]
    else:
        rate = HOME_SITTER_RATES[day_type]["overtime"]
    
    extension_fee = int((extension_units / 60) * rate)
    
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
        result["facility_fee"] = FACILITY_FEE_SITTER
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

def get_rate_table(service_type: str) -> Dict:
    if service_type == "一時預かり保育":
        return TEMPORARY_CARE_RATES
    elif service_type == "ベビーシッター（施設型）":
        return FACILITY_SITTER_RATES
    elif service_type == "ベビーシッター（自宅派遣型）":
        return HOME_SITTER_RATES
    return TEMPORARY_CARE_RATES
