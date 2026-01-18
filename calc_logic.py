"""
保育料金計算ロジック
3つのサービス種別に対応した料金計算モジュール
※料金設定はデータベースから読み込み
"""

from datetime import datetime, date, time, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
import jpholiday

from database import get_fee_config_from_db


def get_fee_config():
    """データベースから料金設定を取得"""
    return get_fee_config_from_db()


@dataclass
class TimeSlot:
    """時間帯の定義"""
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    rate_weekday: int
    rate_holiday: int


@dataclass
class FeeBreakdownItem:
    """料金内訳の1項目"""
    description: str
    hours: float
    rate: int
    amount: int


@dataclass
class CalculationResult:
    """計算結果"""
    service_type: str
    day_type: str
    total_minutes: int
    breakdown: List[FeeBreakdownItem]
    base_fee: int
    facility_fee: int
    sibling_adjustment: int
    meal_fee: int
    option_fee: int
    transport_fee: int
    total: int
    warnings: List[str]


def _build_slots_from_config(service_key: str) -> List[TimeSlot]:
    """データベースの設定からTimeSlotリストを生成"""
    fee_config = get_fee_config()
    config = fee_config[service_key]
    slots = []
    for slot_data in config["slots"]:
        slots.append(TimeSlot(
            name=slot_data["name"],
            start_hour=slot_data["start_hour"],
            start_minute=slot_data["start_minute"],
            end_hour=slot_data["end_hour"],
            end_minute=slot_data["end_minute"],
            rate_weekday=slot_data["rate_weekday"],
            rate_holiday=slot_data["rate_holiday"],
        ))
    return slots


def get_temporary_care_slots() -> List[TimeSlot]:
    return _build_slots_from_config("temporary_care")


def get_facility_sitter_slots() -> List[TimeSlot]:
    return _build_slots_from_config("facility_sitter")


def get_home_sitter_slots() -> List[TimeSlot]:
    return _build_slots_from_config("home_sitter")


def get_facility_fee_temporary() -> int:
    config = get_fee_config()
    return config["temporary_care"]["facility_fee"]


def get_facility_fee_sitter() -> int:
    config = get_fee_config()
    return config["facility_sitter"]["facility_fee"]


def get_sibling_discount_per_hour() -> int:
    config = get_fee_config()
    return config["temporary_care"]["sibling_discount_per_hour"]


def get_sibling_addition_per_hour() -> int:
    config = get_fee_config()
    return config["home_sitter"]["sibling_addition_per_hour"]


def get_snack_price() -> int:
    config = get_fee_config()
    return config["common"]["snack_price"]


def get_housework_option_fee() -> int:
    config = get_fee_config()
    return config["home_sitter"]["housework_option_fee"]


def get_min_hours_facility_sitter() -> int:
    config = get_fee_config()
    return config["facility_sitter"]["min_hours"]


def get_min_hours_home_sitter() -> int:
    config = get_fee_config()
    return config["home_sitter"]["min_hours"]


FACILITY_FEE_TEMPORARY = 550
FACILITY_FEE_SITTER = 2200
SIBLING_DISCOUNT_PER_HOUR = 400
SIBLING_ADDITION_PER_HOUR = 1000
SNACK_PRICE = 150
HOUSEWORK_OPTION = 1100
MIN_HOURS_FACILITY_SITTER = 2
MIN_HOURS_HOME_SITTER = 3


def is_holiday_or_weekend(check_date: date) -> bool:
    """土日祝日かどうかを判定"""
    if check_date.weekday() >= 5:
        return True
    try:
        if jpholiday.is_holiday(check_date):
            return True
    except:
        pass
    return False


def time_to_minutes(t: time) -> int:
    """timeオブジェクトを分に変換"""
    return t.hour * 60 + t.minute


def calculate_slot_overlap(
    start_minutes: int,
    end_minutes: int,
    slot_start_minutes: int,
    slot_end_minutes: int
) -> int:
    """2つの時間範囲の重複分数を計算"""
    overlap_start = max(start_minutes, slot_start_minutes)
    overlap_end = min(end_minutes, slot_end_minutes)
    return max(0, overlap_end - overlap_start)


def calculate_time_breakdown(
    start_time: time,
    end_time: time,
    slots: List[TimeSlot],
    is_holiday: bool
) -> List[FeeBreakdownItem]:
    """時間帯ごとの料金内訳を計算"""
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    
    breakdown = []
    
    for slot in slots:
        slot_start = slot.start_hour * 60 + slot.start_minute
        slot_end = slot.end_hour * 60 + slot.end_minute
        
        if slot_end == 24 * 60:
            slot_end = 24 * 60
        
        overlap = calculate_slot_overlap(start_minutes, end_minutes, slot_start, slot_end)
        
        if overlap > 0:
            hours = overlap / 60
            rate = slot.rate_holiday if is_holiday else slot.rate_weekday
            amount = int(hours * rate)
            
            breakdown.append(FeeBreakdownItem(
                description=f"{slot.name} ({slot.start_hour}:{slot.start_minute:02d}-{slot.end_hour}:{slot.end_minute:02d})",
                hours=round(hours, 2),
                rate=rate,
                amount=amount
            ))
    
    return breakdown


def calculate_temporary_care(
    use_date: date,
    start_time: time,
    end_time: time,
    has_sibling: bool = False,
    include_facility_fee: bool = True,
    snack: bool = False,
    lunch_price: int = 0,
    dinner_price: int = 0
) -> CalculationResult:
    """一時預かり保育の料金計算"""
    is_holiday = is_holiday_or_weekend(use_date)
    day_type = "土日祝" if is_holiday else "平日"
    
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    total_minutes = end_minutes - start_minutes
    total_hours = total_minutes / 60
    
    slots = get_temporary_care_slots()
    breakdown = calculate_time_breakdown(start_time, end_time, slots, is_holiday)
    
    base_fee = sum(item.amount for item in breakdown)
    
    facility_fee = get_facility_fee_temporary() if include_facility_fee else 0
    
    sibling_adjustment = 0
    if has_sibling:
        sibling_adjustment = -int(total_hours * get_sibling_discount_per_hour())
    
    meal_fee = 0
    if snack:
        meal_fee += get_snack_price()
    meal_fee += lunch_price + dinner_price
    
    total = base_fee + facility_fee + sibling_adjustment + meal_fee
    
    return CalculationResult(
        service_type="一時預かり保育",
        day_type=day_type,
        total_minutes=total_minutes,
        breakdown=breakdown,
        base_fee=base_fee,
        facility_fee=facility_fee,
        sibling_adjustment=sibling_adjustment,
        meal_fee=meal_fee,
        option_fee=0,
        transport_fee=0,
        total=total,
        warnings=[]
    )


def calculate_facility_sitter(
    use_date: date,
    start_time: time,
    end_time: time,
    include_facility_fee: bool = True,
    snack: bool = False,
    lunch_price: int = 0,
    dinner_price: int = 0
) -> CalculationResult:
    """ベビーシッター（施設型）の料金計算"""
    is_holiday = is_holiday_or_weekend(use_date)
    day_type = "土日祝" if is_holiday else "平日"
    
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    total_minutes = end_minutes - start_minutes
    total_hours = total_minutes / 60
    
    min_hours = get_min_hours_facility_sitter()
    warnings = []
    if total_hours < min_hours:
        warnings.append(f"⚠️ 最低利用時間は{min_hours}時間です（現在: {total_hours:.1f}時間）")
    
    slots = get_facility_sitter_slots()
    breakdown = calculate_time_breakdown(start_time, end_time, slots, is_holiday)
    
    base_fee = sum(item.amount for item in breakdown)
    
    facility_fee = get_facility_fee_sitter() if include_facility_fee else 0
    
    meal_fee = 0
    if snack:
        meal_fee += get_snack_price()
    meal_fee += lunch_price + dinner_price
    
    total = base_fee + facility_fee + meal_fee
    
    return CalculationResult(
        service_type="ベビーシッター（施設型）",
        day_type=day_type,
        total_minutes=total_minutes,
        breakdown=breakdown,
        base_fee=base_fee,
        facility_fee=facility_fee,
        sibling_adjustment=0,
        meal_fee=meal_fee,
        option_fee=0,
        transport_fee=0,
        total=total,
        warnings=warnings
    )


def calculate_home_sitter(
    use_date: date,
    start_time: time,
    end_time: time,
    has_sibling: bool = False,
    housework_option: bool = False,
    transport_fee: int = 0,
    snack: bool = False,
    lunch_price: int = 0,
    dinner_price: int = 0
) -> CalculationResult:
    """自宅ベビーシッターの料金計算"""
    is_holiday = is_holiday_or_weekend(use_date)
    day_type = "土日祝" if is_holiday else "平日"
    
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    total_minutes = end_minutes - start_minutes
    total_hours = total_minutes / 60
    
    min_hours = get_min_hours_home_sitter()
    warnings = []
    if total_hours < min_hours:
        warnings.append(f"⚠️ 最低利用時間は{min_hours}時間です（現在: {total_hours:.1f}時間）")
    
    slots = get_home_sitter_slots()
    breakdown = calculate_time_breakdown(start_time, end_time, slots, is_holiday)
    
    base_fee = sum(item.amount for item in breakdown)
    
    sibling_adjustment = 0
    if has_sibling:
        sibling_adjustment = int(total_hours * get_sibling_addition_per_hour())
    
    option_fee = get_housework_option_fee() if housework_option else 0
    
    meal_fee = 0
    if snack:
        meal_fee += get_snack_price()
    meal_fee += lunch_price + dinner_price
    
    total = base_fee + sibling_adjustment + option_fee + transport_fee + meal_fee
    
    return CalculationResult(
        service_type="自宅ベビーシッター",
        day_type=day_type,
        total_minutes=total_minutes,
        breakdown=breakdown,
        base_fee=base_fee,
        facility_fee=0,
        sibling_adjustment=sibling_adjustment,
        meal_fee=meal_fee,
        option_fee=option_fee,
        transport_fee=transport_fee,
        total=total,
        warnings=warnings
    )


def format_breakdown_text(result: CalculationResult) -> str:
    """計算結果をテキスト形式でフォーマット"""
    lines = []
    lines.append(f"【{result.service_type}】{result.day_type}")
    lines.append(f"利用時間: {result.total_minutes}分（{result.total_minutes/60:.2f}時間）")
    lines.append("")
    lines.append("■ 時間帯別内訳")
    
    for item in result.breakdown:
        lines.append(f"  {item.description}: {item.hours}h × ¥{item.rate:,} = ¥{item.amount:,}")
    
    lines.append(f"  小計: ¥{result.base_fee:,}")
    
    if result.facility_fee > 0:
        lines.append(f"+ 施設利用料: ¥{result.facility_fee:,}")
    
    if result.sibling_adjustment != 0:
        if result.sibling_adjustment < 0:
            lines.append(f"- 兄弟割引: △¥{abs(result.sibling_adjustment):,}")
        else:
            lines.append(f"+ 兄弟加算: ¥{result.sibling_adjustment:,}")
    
    if result.meal_fee > 0:
        lines.append(f"+ 食事代: ¥{result.meal_fee:,}")
    
    if result.option_fee > 0:
        lines.append(f"+ オプション: ¥{result.option_fee:,}")
    
    if result.transport_fee > 0:
        lines.append(f"+ 交通費: ¥{result.transport_fee:,}")
    
    lines.append("")
    lines.append(f"■ 合計金額: ¥{result.total:,}")
    
    return "\n".join(lines)


def get_time_options() -> List[time]:
    """15分刻みの時刻オプションを生成（0:00〜23:45）"""
    options = []
    for hour in range(0, 24):
        for minute in [0, 15, 30, 45]:
            options.append(time(hour, minute))
    return options
