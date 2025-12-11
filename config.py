"""
料金設定マスタ
すべての料金・時間帯設定をここで一元管理
料金改定時はこのファイルの数値を変更するだけで対応可能
"""

FEE_CONFIG = {
    "temporary_care": {
        "name": "一時預かり保育",
        "slots": [
            {
                "name": "通常",
                "start_hour": 9, "start_minute": 0,
                "end_hour": 17, "end_minute": 0,
                "rate_weekday": 2000,
                "rate_holiday": 3200,
            },
            {
                "name": "時間外（早朝）",
                "start_hour": 7, "start_minute": 0,
                "end_hour": 9, "end_minute": 0,
                "rate_weekday": 2800,
                "rate_holiday": 4000,
            },
            {
                "name": "時間外（夜間）",
                "start_hour": 17, "start_minute": 0,
                "end_hour": 22, "end_minute": 0,
                "rate_weekday": 2800,
                "rate_holiday": 4000,
            },
        ],
        "facility_fee": 550,
        "sibling_discount_per_hour": 400,
        "min_hours": None,
    },
    
    "facility_sitter": {
        "name": "ベビーシッター（施設型）",
        "slots": [
            {
                "name": "通常",
                "start_hour": 9, "start_minute": 0,
                "end_hour": 17, "end_minute": 0,
                "rate_weekday": 3200,
                "rate_holiday": 4000,
            },
            {
                "name": "時間外（早朝）",
                "start_hour": 7, "start_minute": 0,
                "end_hour": 9, "end_minute": 0,
                "rate_weekday": 4000,
                "rate_holiday": 4500,
            },
            {
                "name": "時間外（夜間）",
                "start_hour": 17, "start_minute": 0,
                "end_hour": 22, "end_minute": 0,
                "rate_weekday": 4000,
                "rate_holiday": 4500,
            },
        ],
        "facility_fee": 2200,
        "min_hours": 2,
    },
    
    "home_sitter": {
        "name": "自宅ベビーシッター",
        "slots": [
            {
                "name": "通常",
                "start_hour": 9, "start_minute": 0,
                "end_hour": 17, "end_minute": 0,
                "rate_weekday": 3500,
                "rate_holiday": 3900,
            },
            {
                "name": "時間外（早朝）",
                "start_hour": 7, "start_minute": 0,
                "end_hour": 9, "end_minute": 0,
                "rate_weekday": 3800,
                "rate_holiday": 4200,
            },
            {
                "name": "時間外（夕方）",
                "start_hour": 17, "start_minute": 0,
                "end_hour": 20, "end_minute": 0,
                "rate_weekday": 3800,
                "rate_holiday": 4200,
            },
            {
                "name": "早朝夜間（深夜前）",
                "start_hour": 0, "start_minute": 0,
                "end_hour": 7, "end_minute": 0,
                "rate_weekday": 4000,
                "rate_holiday": 4400,
            },
            {
                "name": "早朝夜間（夜間）",
                "start_hour": 20, "start_minute": 0,
                "end_hour": 24, "end_minute": 0,
                "rate_weekday": 4000,
                "rate_holiday": 4400,
            },
        ],
        "sibling_addition_per_hour": 1000,
        "housework_option_fee": 1100,
        "min_hours": 3,
    },
    
    "common": {
        "snack_price": 150,
    },
}
