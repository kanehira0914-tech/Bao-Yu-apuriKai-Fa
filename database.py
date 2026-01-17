import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import json

DATABASE_PATH = "nursery.db"

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_database():
    """既存データベースに不足カラムを追加するマイグレーション"""
    conn = get_connection()
    cursor = conn.cursor()
    
    reservations_columns = {
        'base_price': 'INTEGER DEFAULT 0',
        'facility_fee': 'INTEGER DEFAULT 0',
        'option_price': 'INTEGER DEFAULT 0',
        'service_category': 'TEXT',
        'welfare_service': 'INTEGER DEFAULT 0',
    }
    
    cursor.execute("PRAGMA table_info(reservations)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    for col_name, col_type in reservations_columns.items():
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_type}")
            except:
                pass
    
    conn.commit()
    conn.close()


def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_datetime TEXT,
            reservation_date DATE,
            start_time TEXT,
            end_time TEXT,
            reservation_type TEXT,
            child_name TEXT,
            child_name_kana TEXT,
            email TEXT,
            address TEXT,
            guardian_name TEXT,
            management_memo TEXT,
            welfare_service INTEGER DEFAULT 0,
            base_price INTEGER DEFAULT 0,
            facility_fee INTEGER DEFAULT 0,
            option_price INTEGER DEFAULT 0,
            service_category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER,
            check_in_time TIMESTAMP,
            check_out_time TIMESTAMP,
            is_cancelled INTEGER DEFAULT 0,
            cancel_type TEXT,
            extension_minutes INTEGER DEFAULT 0,
            extension_fee INTEGER DEFAULT 0,
            transport_fee INTEGER DEFAULT 0,
            discount1 TEXT,
            discount1_amount INTEGER DEFAULT 0,
            discount2 TEXT,
            discount2_amount INTEGER DEFAULT 0,
            additional_fee INTEGER DEFAULT 0,
            additional_note TEXT,
            staff_name TEXT,
            certification_date TEXT,
            certification_type TEXT,
            total_amount INTEGER DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS care_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER,
            record_type TEXT,
            record_time TIMESTAMP,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            name_kana TEXT,
            certification_date TEXT,
            certification_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM staff")
    if cursor.fetchone()[0] == 0:
        default_staff = [
            ("黒田千景", "クロダチカゲ", "令和6年3月8日", "居宅型保育基礎研修修了者"),
            ("由良清湖", "ユラセイコ", "令和5年4月1日", "保育士資格を保有し、補足研修を修了した者"),
        ]
        cursor.executemany(
            "INSERT INTO staff (name, name_kana, certification_date, certification_type) VALUES (?, ?, ?, ?)",
            default_staff
        )
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nap_check_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER,
            nap_index INTEGER DEFAULT 1,
            check_time TEXT,
            arrow_direction TEXT DEFAULT 'up',
            is_corrected INTEGER DEFAULT 0,
            staff_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id),
            UNIQUE(reservation_id, nap_index, check_time)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    migrate_database()

def determine_service_category(reservation_type: str) -> str:
    if "こぐまBaby" in reservation_type or "Baby" in reservation_type:
        return "一時預かり保育"
    elif "ベビーシッター利用支援事業" in reservation_type:
        return "ベビーシッター（施設型）"
    elif "ご自宅ベビーシッター" in reservation_type:
        return "ベビーシッター（自宅派遣型）"
    elif "レンタルルーム" in reservation_type:
        return "レンタルルーム"
    else:
        return "その他"

def parse_datetime_range(datetime_str: str) -> tuple:
    try:
        datetime_str = datetime_str.replace('\n', ' ').replace('‾', '-').replace('〜', '-').replace('~', '-')
        parts = datetime_str.split(' ')
        date_part = parts[0]
        time_range = ' '.join(parts[1:]).replace('：', ':').replace(' ', '')
        
        if '-' in time_range:
            times = time_range.split('-')
            start_time = times[0].strip()
            end_time = times[1].strip() if len(times) > 1 else ""
        else:
            start_time = time_range
            end_time = ""
        
        return date_part, start_time, end_time
    except:
        return datetime_str, "", ""

def import_csv_data(df) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    imported_count = 0
    
    for _, row in df.iterrows():
        try:
            datetime_str = str(row.get('予約日時', ''))
            date_part, start_time, end_time = parse_datetime_range(datetime_str)
            
            reservation_type = str(row.get('予約内容', ''))
            child_name = str(row.get('お子様のお名前', ''))
            child_name_kana = str(row.get('お子様のお名前(ふりがな)', ''))
            email = str(row.get('メールアドレス', ''))
            address = str(row.get('住所', ''))
            guardian_name = str(row.get('保護者名（東京都BS事業申請者）', ''))
            management_memo = str(row.get('管理メモ', ''))
            
            welfare_str = str(row.get('企業の福利厚生システム（ベネフィット・ワン、リロクラブ）の利用をご希望ですか？\n', ''))
            welfare_service = 1 if 'はい' in welfare_str or '希望' in welfare_str else 0
            
            base_price = 0
            for col in ['予約種類(フォーム)料金', '受付枠毎の料金', '決済金額']:
                if col in row and row[col]:
                    try:
                        base_price = int(str(row[col]).replace(',', '').replace('¥', ''))
                        break
                    except:
                        pass
            
            facility_fee = 0
            option_price = 0
            if '選択肢の合計料金' in row and row['選択肢の合計料金']:
                try:
                    facility_fee = int(str(row['選択肢の合計料金']).replace(',', '').replace('¥', ''))
                except:
                    pass
            
            service_category = determine_service_category(reservation_type)
            
            if not child_name or child_name == 'nan':
                continue
            
            cursor.execute('''
                SELECT id FROM reservations 
                WHERE reservation_datetime = ? AND child_name = ?
            ''', (datetime_str, child_name))
            
            if cursor.fetchone():
                continue
            
            cursor.execute('''
                INSERT INTO reservations (
                    reservation_datetime, reservation_date, start_time, end_time,
                    reservation_type, child_name, child_name_kana, email, address,
                    guardian_name, management_memo, welfare_service, base_price,
                    facility_fee, option_price, service_category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime_str, date_part, start_time, end_time,
                reservation_type, child_name, child_name_kana, email, address,
                guardian_name, management_memo, welfare_service, base_price,
                facility_fee, option_price, service_category
            ))
            
            reservation_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO attendance_records (reservation_id, total_amount)
                VALUES (?, ?)
            ''', (reservation_id, base_price + facility_fee))
            
            imported_count += 1
            
        except Exception as e:
            print(f"Error importing row: {e}")
            continue
    
    conn.commit()
    conn.close()
    return imported_count

def get_reservations_by_date(target_date: str) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
               a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
               a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
               a.discount2_amount, a.additional_fee, a.additional_note,
               a.staff_name, a.certification_date, a.certification_type, a.total_amount
        FROM reservations r
        LEFT JOIN attendance_records a ON r.id = a.reservation_id
        WHERE r.reservation_date = ?
        ORDER BY r.start_time
    ''', (target_date,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_all_reservations() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
               a.is_cancelled, a.cancel_type, a.total_amount
        FROM reservations r
        LEFT JOIN attendance_records a ON r.id = a.reservation_id
        ORDER BY r.reservation_date DESC, r.start_time
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_reservations_by_month(year: int, month: int) -> List[Dict]:
    """指定した年月の予約を取得"""
    conn = get_connection()
    cursor = conn.cursor()
    
    start_date = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1:04d}-01-01"
    else:
        end_date = f"{year:04d}-{month+1:02d}-01"
    
    cursor.execute('''
        SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
               a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
               a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
               a.discount2_amount, a.additional_fee, a.additional_note,
               a.staff_name, a.certification_date, a.certification_type, a.total_amount
        FROM reservations r
        LEFT JOIN attendance_records a ON r.id = a.reservation_id
        WHERE r.reservation_date >= ? AND r.reservation_date < ?
        ORDER BY r.reservation_date, r.start_time
    ''', (start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_reservations_by_date_range(start_date: str, end_date: str) -> List[Dict]:
    """指定した日付範囲の予約を取得"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
               a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
               a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
               a.discount2_amount, a.additional_fee, a.additional_note,
               a.staff_name, a.certification_date, a.certification_type, a.total_amount
        FROM reservations r
        LEFT JOIN attendance_records a ON r.id = a.reservation_id
        WHERE r.reservation_date >= ? AND r.reservation_date <= ?
        ORDER BY r.reservation_date, r.start_time
    ''', (start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def update_attendance(reservation_id: int, data: Dict):
    conn = get_connection()
    cursor = conn.cursor()
    
    data['updated_at'] = datetime.now().isoformat()
    
    set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
    values = list(data.values())
    values.append(reservation_id)
    
    cursor.execute(f'''
        UPDATE attendance_records
        SET {set_clause}
        WHERE reservation_id = ?
    ''', values)
    
    conn.commit()
    conn.close()

def add_care_record(reservation_id: int, record_type: str, details: str = "", index: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    
    unique_types = ['lunch', 'snack', 'dinner']
    indexed_types = ['temperature', 'stool']
    direct_indexed_types = ['nap_1', 'nap_2', 'nap_3']
    
    if record_type in unique_types:
        cursor.execute('''
            SELECT id FROM care_records
            WHERE reservation_id = ? AND record_type = ?
        ''', (reservation_id, record_type))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE care_records
                SET details = ?, record_time = ?
                WHERE id = ?
            ''', (details, datetime.now().isoformat(), existing['id']))
        else:
            cursor.execute('''
                INSERT INTO care_records (reservation_id, record_type, record_time, details)
                VALUES (?, ?, ?, ?)
            ''', (reservation_id, record_type, datetime.now().isoformat(), details))
    elif record_type in indexed_types:
        record_key = f"{record_type}_{index}"
        cursor.execute('''
            SELECT id FROM care_records
            WHERE reservation_id = ? AND record_type = ?
        ''', (reservation_id, record_key))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE care_records
                SET details = ?, record_time = ?
                WHERE id = ?
            ''', (details, datetime.now().isoformat(), existing['id']))
        else:
            cursor.execute('''
                INSERT INTO care_records (reservation_id, record_type, record_time, details)
                VALUES (?, ?, ?, ?)
            ''', (reservation_id, record_key, datetime.now().isoformat(), details))
    elif record_type in direct_indexed_types:
        cursor.execute('''
            SELECT id FROM care_records
            WHERE reservation_id = ? AND record_type = ?
        ''', (reservation_id, record_type))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE care_records
                SET details = ?, record_time = ?
                WHERE id = ?
            ''', (details, datetime.now().isoformat(), existing['id']))
        else:
            cursor.execute('''
                INSERT INTO care_records (reservation_id, record_type, record_time, details)
                VALUES (?, ?, ?, ?)
            ''', (reservation_id, record_type, datetime.now().isoformat(), details))
    else:
        cursor.execute('''
            INSERT INTO care_records (reservation_id, record_type, record_time, details)
            VALUES (?, ?, ?, ?)
        ''', (reservation_id, record_type, datetime.now().isoformat(), details))
    
    conn.commit()
    conn.close()

def get_care_records(reservation_id: int) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM care_records
        WHERE reservation_id = ?
        ORDER BY record_time
    ''', (reservation_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_staff_list() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM staff ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_reservation_by_id(reservation_id: int) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
               a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
               a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
               a.discount2_amount, a.additional_fee, a.additional_note,
               a.staff_name, a.certification_date, a.certification_type, a.total_amount
        FROM reservations r
        LEFT JOIN attendance_records a ON r.id = a.reservation_id
        WHERE r.id = ?
    ''', (reservation_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def save_nap_check_log(reservation_id: int, nap_index: int, check_time: str, 
                        arrow_direction: str, is_corrected: bool, staff_name: str):
    """午睡チェックログを保存（upsert）"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id FROM nap_check_logs
        WHERE reservation_id = ? AND nap_index = ? AND check_time = ?
    ''', (reservation_id, nap_index, check_time))
    
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('''
            UPDATE nap_check_logs
            SET arrow_direction = ?, is_corrected = ?, staff_name = ?, updated_at = ?
            WHERE id = ?
        ''', (arrow_direction, 1 if is_corrected else 0, staff_name, 
              datetime.now().isoformat(), existing['id']))
    else:
        cursor.execute('''
            INSERT INTO nap_check_logs 
            (reservation_id, nap_index, check_time, arrow_direction, is_corrected, staff_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (reservation_id, nap_index, check_time, arrow_direction, 
              1 if is_corrected else 0, staff_name))
    
    conn.commit()
    conn.close()


def get_nap_check_logs(reservation_id: int, nap_index: int) -> List[Dict]:
    """特定の午睡セッションのチェックログを取得"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM nap_check_logs
        WHERE reservation_id = ? AND nap_index = ?
        ORDER BY check_time
    ''', (reservation_id, nap_index))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def delete_nap_check_logs(reservation_id: int, nap_index: int):
    """特定の午睡セッションのチェックログを削除"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM nap_check_logs
        WHERE reservation_id = ? AND nap_index = ?
    ''', (reservation_id, nap_index))
    
    conn.commit()
    conn.close()


init_database()
