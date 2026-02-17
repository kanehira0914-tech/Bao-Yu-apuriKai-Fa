import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import json
import hashlib
import secrets
import pytz

JST = pytz.timezone('Asia/Tokyo')

def get_jst_now() -> datetime:
    """日本時間（JST）の現在日時を取得"""
    return datetime.now(JST)

DATABASE_PATH = "nursery.db"

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

FACILITY_HOUSE = "house"
FACILITY_BABY = "baby"
DEFAULT_FACILITY = FACILITY_HOUSE


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
        'facility_id': f"TEXT DEFAULT '{DEFAULT_FACILITY}'",
    }
    
    cursor.execute("PRAGMA table_info(reservations)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    for col_name, col_type in reservations_columns.items():
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_type}")
                if col_name == 'facility_id':
                    cursor.execute(f"UPDATE reservations SET facility_id = '{DEFAULT_FACILITY}' WHERE facility_id IS NULL")
            except:
                pass
    
    staff_columns = {
        'facility_id': f"TEXT DEFAULT '{DEFAULT_FACILITY}'",
    }
    
    cursor.execute("PRAGMA table_info(staff)")
    existing_staff_cols = {row[1] for row in cursor.fetchall()}
    
    for col_name, col_type in staff_columns.items():
        if col_name not in existing_staff_cols:
            try:
                cursor.execute(f"ALTER TABLE staff ADD COLUMN {col_name} {col_type}")
                cursor.execute(f"UPDATE staff SET facility_id = 'both' WHERE facility_id IS NULL")
            except:
                pass
    
    conn.commit()
    conn.close()


def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(f'''
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
            facility_id TEXT DEFAULT '{DEFAULT_FACILITY}',
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
            facility_id TEXT DEFAULT 'both',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM staff")
    if cursor.fetchone()[0] == 0:
        default_staff = [
            ("黒田千景", "クロダチカゲ", "令和6年3月8日", "居宅型保育基礎研修修了者", "both"),
            ("由良清湖", "ユラセイコ", "令和5年4月1日", "保育士資格を保有し、補足研修を修了した者", "both"),
        ]
        cursor.executemany(
            "INSERT INTO staff (name, name_kana, certification_date, certification_type, facility_id) VALUES (?, ?, ?, ?, ?)",
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        salt = secrets.token_hex(16)
        password_hash = hash_password('admin123', salt)
        cursor.execute(
            "INSERT INTO users (username, password_hash, salt, role, display_name) VALUES (?, ?, ?, ?, ?)",
            ('admin', password_hash, salt, 'admin', '管理者')
        )
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fee_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value INTEGER NOT NULL,
            category TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id INTEGER,
            username TEXT,
            session_token_prefix TEXT,
            details TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM fee_settings")
    if cursor.fetchone()[0] == 0:
        default_fees = [
            ('temp_weekday_normal', 2000, 'temporary_care', '一時預かり 平日通常'),
            ('temp_holiday_normal', 3200, 'temporary_care', '一時預かり 土日祝通常'),
            ('temp_weekday_overtime', 2800, 'temporary_care', '一時預かり 平日時間外'),
            ('temp_holiday_overtime', 4000, 'temporary_care', '一時預かり 土日祝時間外'),
            ('temp_facility_fee', 550, 'temporary_care', '一時預かり 施設利用料'),
            ('temp_sibling_discount', 400, 'temporary_care', '一時預かり 兄弟割引/H'),
            
            ('facility_weekday_normal', 3200, 'facility_sitter', '施設型シッター 平日通常'),
            ('facility_holiday_normal', 4000, 'facility_sitter', '施設型シッター 土日祝通常'),
            ('facility_weekday_overtime', 4000, 'facility_sitter', '施設型シッター 平日時間外'),
            ('facility_holiday_overtime', 4500, 'facility_sitter', '施設型シッター 土日祝時間外'),
            ('facility_facility_fee', 2200, 'facility_sitter', '施設型シッター 施設利用料'),
            
            ('home_weekday_normal', 3500, 'home_sitter', '自宅シッター 平日通常'),
            ('home_holiday_normal', 3900, 'home_sitter', '自宅シッター 土日祝通常'),
            ('home_weekday_overtime', 3800, 'home_sitter', '自宅シッター 平日時間外'),
            ('home_holiday_overtime', 4200, 'home_sitter', '自宅シッター 土日祝時間外'),
            ('home_weekday_night', 4000, 'home_sitter', '自宅シッター 平日早朝夜間'),
            ('home_holiday_night', 4400, 'home_sitter', '自宅シッター 土日祝早朝夜間'),
            ('home_sibling_addition', 1000, 'home_sitter', '自宅シッター 兄弟加算/H'),
            ('home_housework_fee', 1100, 'home_sitter', '自宅シッター 家事代行オプション'),
            
            ('snack_price', 150, 'option', 'おやつ代'),
            ('bento_price', 500, 'option', 'お弁当代'),
            ('tebura_set_price', 300, 'option', '手ぶらセット'),
        ]
        cursor.executemany(
            "INSERT INTO fee_settings (setting_key, setting_value, category, description) VALUES (?, ?, ?, ?)",
            default_fees
        )
    
    conn.commit()
    conn.close()
    
    migrate_database()


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode()).hexdigest()


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    return hash_password(password, salt) == password_hash


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user = dict(row)
        if verify_password(password, user['password_hash'], user['salt']):
            return {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'display_name': user['display_name']
            }
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, display_name, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


SESSION_EXPIRY_DAYS = 30

def create_session(user_id: int) -> str:
    """ユーザーのセッショントークンを作成（30日有効）"""
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()
    
    session_token = secrets.token_urlsafe(32)
    expires_at = (get_jst_now() + timedelta(days=SESSION_EXPIRY_DAYS)).isoformat()
    
    cursor.execute(
        "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
        (user_id, session_token, expires_at)
    )
    conn.commit()
    conn.close()
    return session_token


def validate_session(session_token: str, user_agent: str = None) -> Optional[Dict]:
    """セッショントークンを検証し、有効ならユーザー情報を返す
    
    失敗時のログ分類:
    - VALIDATE_NO_TOKEN: トークン自体が空/None（iOSのCookie拒否・削除の可能性）
    - VALIDATE_TOKEN_NOT_IN_DB: トークンがDBに存在しない（別デバイスでログアウト済み、またはDB初期化済み）
    - VALIDATE_EXPIRED: トークンはDBにあるが有効期限切れ
    - VALIDATE_USER_DELETED: セッションはあるがユーザーが削除されている
    - VALIDATE_ERROR: DB接続エラー等の予期しないエラー
    """
    if not session_token:
        log_session_event(
            "VALIDATE_NO_TOKEN", 
            details="セッショントークンが空またはNone。原因: (1)Cookieが存在しない (2)iOSのITP/プライベートブラウズによるCookie拒否 (3)Safari設定でCookieブロック中 (4)Cookieの有効期限切れでブラウザが自動削除",
            user_agent=user_agent
        )
        return None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM user_sessions WHERE session_token = ?", (session_token,))
        session_row = cursor.fetchone()
        
        if not session_row:
            conn.close()
            log_session_event(
                "VALIDATE_TOKEN_NOT_IN_DB", 
                session_token=session_token,
                details="トークンがDBに存在しない。原因: (1)別デバイス/ブラウザで明示的にログアウト済み (2)管理者によるセッション削除 (3)cleanup_expired_sessionsで期限切れ削除済み (4)DB初期化/リセット",
                user_agent=user_agent
            )
            return None
        
        session_data = dict(session_row)
        user_id = session_data['user_id']
        expires_at_str = session_data['expires_at']
        
        cursor.execute("SELECT id, username, role, display_name FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        conn.close()
        
        if not user_row:
            log_session_event(
                "VALIDATE_USER_DELETED", 
                session_token=session_token,
                details=f"セッションのユーザー(user_id={user_id})がusersテーブルに存在しない。原因: 管理者がユーザーを削除した可能性",
                user_agent=user_agent
            )
            delete_session(session_token)
            return None
        
        user_data = dict(user_row)
        expires_at = datetime.fromisoformat(expires_at_str)
        now_jst = get_jst_now().replace(tzinfo=None)
        
        if expires_at > now_jst:
            remaining = expires_at - now_jst
            remaining_days = remaining.days
            log_session_event(
                "VALIDATE_SUCCESS", 
                user_id=user_data['id'], 
                username=user_data['username'],
                session_token=session_token,
                details=f"検証成功。有効期限: {expires_at.strftime('%Y-%m-%d %H:%M')} JST（残り{remaining_days}日）、現在時刻: {now_jst.strftime('%Y-%m-%d %H:%M')} JST",
                user_agent=user_agent
            )
            return {
                'id': user_data['id'],
                'username': user_data['username'],
                'role': user_data['role'],
                'display_name': user_data['display_name']
            }
        else:
            expired_ago = now_jst - expires_at
            expired_hours = expired_ago.total_seconds() / 3600
            log_session_event(
                "VALIDATE_EXPIRED", 
                user_id=user_data['id'], 
                username=user_data['username'],
                session_token=session_token,
                details=f"有効期限切れ。期限: {expires_at.strftime('%Y-%m-%d %H:%M')} JST、現在: {now_jst.strftime('%Y-%m-%d %H:%M')} JST（{expired_hours:.1f}時間超過）。原因: セッション有効期限({SESSION_EXPIRY_DAYS}日)を超過",
                user_agent=user_agent
            )
            delete_session(session_token)
            return None
        
    except Exception as e:
        log_session_event(
            "VALIDATE_ERROR", 
            session_token=session_token,
            details=f"予期しないエラー: {type(e).__name__}: {str(e)}。原因: DB接続障害またはデータ破損の可能性",
            user_agent=user_agent
        )
        return None


def delete_session(session_token: str):
    """セッションを削除"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE session_token = ?", (session_token,))
    conn.commit()
    conn.close()


def delete_user_sessions(user_id: int):
    """ユーザーの全セッションを削除"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def cleanup_expired_sessions():
    """期限切れセッションを削除"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE expires_at < ?", (get_jst_now().replace(tzinfo=None).isoformat(),))
    conn.commit()
    conn.close()


def log_session_event(event_type: str, user_id: int = None, username: str = None, 
                      session_token: str = None, details: str = None, user_agent: str = None):
    """セッションイベントをログに記録（デバッグ用）- JST時刻で保存"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        token_prefix = session_token[:8] + "..." if session_token and len(session_token) > 8 else session_token
        jst_now = get_jst_now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            """INSERT INTO session_logs 
               (event_type, user_id, username, session_token_prefix, details, user_agent, created_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, user_id, username, token_prefix, details, user_agent, jst_now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        pass


def get_session_logs(limit: int = 100) -> List[Dict]:
    """セッションログを取得"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM session_logs ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_users() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, display_name, created_at FROM users ORDER BY created_at")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_user(username: str, password: str, role: str = 'user', display_name: str = None) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)
        cursor.execute(
            "INSERT INTO users (username, password_hash, salt, role, display_name) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, salt, role, display_name or username)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def update_user_password(user_id: int, new_password: str) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        salt = secrets.token_hex(16)
        password_hash = hash_password(new_password, salt)
        cursor.execute(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (password_hash, salt, datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        return True
    except:
        return False


def update_user(user_id: int, display_name: str = None, role: str = None) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        conn.close()
        return True
    except:
        return False


def delete_user(user_id: int) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ? AND username != 'admin'", (user_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False


def get_all_fee_settings() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fee_settings ORDER BY category, setting_key")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_fee_settings_by_category(category: str) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fee_settings WHERE category = ? ORDER BY setting_key", (category,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_fee_setting(setting_key: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM fee_settings WHERE setting_key = ?", (setting_key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0


def update_fee_setting(setting_key: str, setting_value: int) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fee_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
            (setting_value, datetime.now().isoformat(), setting_key)
        )
        conn.commit()
        conn.close()
        return True
    except:
        return False


def get_fee_config_from_db() -> Dict:
    """データベースから料金設定を読み込み、FEE_CONFIG形式で返す"""
    settings = {}
    for row in get_all_fee_settings():
        settings[row['setting_key']] = row['setting_value']
    
    return {
        "temporary_care": {
            "name": "一時預かり保育",
            "slots": [
                {
                    "name": "通常",
                    "start_hour": 9, "start_minute": 0,
                    "end_hour": 17, "end_minute": 0,
                    "rate_weekday": settings.get('temp_weekday_normal', 2000),
                    "rate_holiday": settings.get('temp_holiday_normal', 3200),
                },
                {
                    "name": "時間外（早朝）",
                    "start_hour": 7, "start_minute": 0,
                    "end_hour": 9, "end_minute": 0,
                    "rate_weekday": settings.get('temp_weekday_overtime', 2800),
                    "rate_holiday": settings.get('temp_holiday_overtime', 4000),
                },
                {
                    "name": "時間外（夜間）",
                    "start_hour": 17, "start_minute": 0,
                    "end_hour": 22, "end_minute": 0,
                    "rate_weekday": settings.get('temp_weekday_overtime', 2800),
                    "rate_holiday": settings.get('temp_holiday_overtime', 4000),
                },
            ],
            "facility_fee": settings.get('temp_facility_fee', 550),
            "sibling_discount_per_hour": settings.get('temp_sibling_discount', 400),
            "min_hours": 1,
        },
        
        "facility_sitter": {
            "name": "ベビーシッター（施設型）",
            "slots": [
                {
                    "name": "通常",
                    "start_hour": 9, "start_minute": 0,
                    "end_hour": 17, "end_minute": 0,
                    "rate_weekday": settings.get('facility_weekday_normal', 3200),
                    "rate_holiday": settings.get('facility_holiday_normal', 4000),
                },
                {
                    "name": "時間外（早朝）",
                    "start_hour": 7, "start_minute": 0,
                    "end_hour": 9, "end_minute": 0,
                    "rate_weekday": settings.get('facility_weekday_overtime', 4000),
                    "rate_holiday": settings.get('facility_holiday_overtime', 4500),
                },
                {
                    "name": "時間外（夜間）",
                    "start_hour": 17, "start_minute": 0,
                    "end_hour": 22, "end_minute": 0,
                    "rate_weekday": settings.get('facility_weekday_overtime', 4000),
                    "rate_holiday": settings.get('facility_holiday_overtime', 4500),
                },
            ],
            "facility_fee": settings.get('facility_facility_fee', 2200),
            "min_hours": 2,
        },
        
        "home_sitter": {
            "name": "自宅ベビーシッター",
            "slots": [
                {
                    "name": "通常",
                    "start_hour": 9, "start_minute": 0,
                    "end_hour": 17, "end_minute": 0,
                    "rate_weekday": settings.get('home_weekday_normal', 3500),
                    "rate_holiday": settings.get('home_holiday_normal', 3900),
                },
                {
                    "name": "時間外（早朝）",
                    "start_hour": 7, "start_minute": 0,
                    "end_hour": 9, "end_minute": 0,
                    "rate_weekday": settings.get('home_weekday_overtime', 3800),
                    "rate_holiday": settings.get('home_holiday_overtime', 4200),
                },
                {
                    "name": "時間外（夕方）",
                    "start_hour": 17, "start_minute": 0,
                    "end_hour": 20, "end_minute": 0,
                    "rate_weekday": settings.get('home_weekday_overtime', 3800),
                    "rate_holiday": settings.get('home_holiday_overtime', 4200),
                },
                {
                    "name": "早朝夜間（深夜前）",
                    "start_hour": 0, "start_minute": 0,
                    "end_hour": 7, "end_minute": 0,
                    "rate_weekday": settings.get('home_weekday_night', 4000),
                    "rate_holiday": settings.get('home_holiday_night', 4400),
                },
                {
                    "name": "早朝夜間（夜間）",
                    "start_hour": 20, "start_minute": 0,
                    "end_hour": 24, "end_minute": 0,
                    "rate_weekday": settings.get('home_weekday_night', 4000),
                    "rate_holiday": settings.get('home_holiday_night', 4400),
                },
            ],
            "sibling_addition_per_hour": settings.get('home_sibling_addition', 1000),
            "housework_option_fee": settings.get('home_housework_fee', 1100),
            "min_hours": 3,
        },
        
        "common": {
            "snack_price": settings.get('snack_price', 150),
            "bento_price": settings.get('bento_price', 500),
            "tebura_set_price": settings.get('tebura_set_price', 300),
        },
    }


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

def import_csv_data(df, facility_id: str = None) -> int:
    if facility_id is None:
        facility_id = DEFAULT_FACILITY
    
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
            
            facility_fee_amount = 0
            option_price = 0
            if '選択肢の合計料金' in row and row['選択肢の合計料金']:
                try:
                    facility_fee_amount = int(str(row['選択肢の合計料金']).replace(',', '').replace('¥', ''))
                except:
                    pass
            
            service_category = determine_service_category(reservation_type)
            
            if not child_name or child_name == 'nan':
                continue
            
            cursor.execute('''
                SELECT id FROM reservations 
                WHERE reservation_datetime = ? AND child_name = ? AND facility_id = ?
            ''', (datetime_str, child_name, facility_id))
            
            if cursor.fetchone():
                continue
            
            cursor.execute('''
                INSERT INTO reservations (
                    reservation_datetime, reservation_date, start_time, end_time,
                    reservation_type, child_name, child_name_kana, email, address,
                    guardian_name, management_memo, welfare_service, base_price,
                    facility_fee, option_price, service_category, facility_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime_str, date_part, start_time, end_time,
                reservation_type, child_name, child_name_kana, email, address,
                guardian_name, management_memo, welfare_service, base_price,
                facility_fee_amount, option_price, service_category, facility_id
            ))
            
            reservation_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO attendance_records (reservation_id, total_amount)
                VALUES (?, ?)
            ''', (reservation_id, base_price + facility_fee_amount))
            
            imported_count += 1
            
        except Exception as e:
            print(f"Error importing row: {e}")
            continue
    
    conn.commit()
    conn.close()
    return imported_count

def get_reservations_by_date(target_date: str, facility_id: str = None) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if facility_id:
        cursor.execute('''
            SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
                   a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
                   a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
                   a.discount2_amount, a.additional_fee, a.additional_note,
                   a.staff_name, a.certification_date, a.certification_type, a.total_amount
            FROM reservations r
            LEFT JOIN attendance_records a ON r.id = a.reservation_id
            WHERE r.reservation_date = ? AND r.facility_id = ?
            ORDER BY r.start_time
        ''', (target_date, facility_id))
    else:
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

def get_all_reservations(facility_id: str = None) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if facility_id:
        cursor.execute('''
            SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
                   a.is_cancelled, a.cancel_type, a.total_amount
            FROM reservations r
            LEFT JOIN attendance_records a ON r.id = a.reservation_id
            WHERE r.facility_id = ?
            ORDER BY r.reservation_date DESC, r.start_time
        ''', (facility_id,))
    else:
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


def get_reservations_by_month(year: int, month: int, facility_id: str = None) -> List[Dict]:
    """指定した年月の予約を取得"""
    conn = get_connection()
    cursor = conn.cursor()
    
    start_date = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1:04d}-01-01"
    else:
        end_date = f"{year:04d}-{month+1:02d}-01"
    
    if facility_id:
        cursor.execute('''
            SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
                   a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
                   a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
                   a.discount2_amount, a.additional_fee, a.additional_note,
                   a.staff_name, a.certification_date, a.certification_type, a.total_amount
            FROM reservations r
            LEFT JOIN attendance_records a ON r.id = a.reservation_id
            WHERE r.reservation_date >= ? AND r.reservation_date < ? AND r.facility_id = ?
            ORDER BY r.reservation_date, r.start_time
        ''', (start_date, end_date, facility_id))
    else:
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


def get_reservations_by_date_range(start_date: str, end_date: str, facility_id: str = None) -> List[Dict]:
    """指定した日付範囲の予約を取得"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if facility_id:
        cursor.execute('''
            SELECT r.*, a.id as attendance_id, a.check_in_time, a.check_out_time,
                   a.is_cancelled, a.cancel_type, a.extension_minutes, a.extension_fee,
                   a.transport_fee, a.discount1, a.discount1_amount, a.discount2,
                   a.discount2_amount, a.additional_fee, a.additional_note,
                   a.staff_name, a.certification_date, a.certification_type, a.total_amount
            FROM reservations r
            LEFT JOIN attendance_records a ON r.id = a.reservation_id
            WHERE r.reservation_date >= ? AND r.reservation_date <= ? AND r.facility_id = ?
            ORDER BY r.reservation_date, r.start_time
        ''', (start_date, end_date, facility_id))
    else:
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

def get_staff_list(facility_id: str = None) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if facility_id:
        cursor.execute('''
            SELECT * FROM staff 
            WHERE facility_id = ? OR facility_id = 'both'
            ORDER BY name
        ''', (facility_id,))
    else:
        cursor.execute('SELECT * FROM staff ORDER BY name')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def add_staff(name: str, name_kana: str, certification_date: str, 
              certification_type: str, facility_id: str = 'both') -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO staff (name, name_kana, certification_date, certification_type, facility_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, name_kana, certification_date, certification_type, facility_id))
    
    staff_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return staff_id


def update_staff(staff_id: int, name: str, name_kana: str, 
                 certification_date: str, certification_type: str, facility_id: str = 'both'):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE staff
        SET name = ?, name_kana = ?, certification_date = ?, certification_type = ?, facility_id = ?
        WHERE id = ?
    ''', (name, name_kana, certification_date, certification_type, facility_id, staff_id))
    
    conn.commit()
    conn.close()


def delete_staff(staff_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM staff WHERE id = ?', (staff_id,))
    
    conn.commit()
    conn.close()


def get_staff_by_id(staff_id: int) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM staff WHERE id = ?', (staff_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


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
