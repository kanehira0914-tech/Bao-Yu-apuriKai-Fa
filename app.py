import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import time
import extra_streamlit_components as stx

from database import (
    init_database, import_csv_data, get_reservations_by_date,
    get_all_reservations, update_attendance, add_care_record,
    get_care_records, get_staff_list, get_reservation_by_id,
    get_reservations_by_month, get_reservations_by_date_range,
    save_nap_check_log, get_nap_check_logs, delete_nap_check_logs,
    add_staff, update_staff, delete_staff, get_staff_by_id,
    FACILITY_HOUSE, FACILITY_BABY, DEFAULT_FACILITY,
    authenticate_user, update_user_password, get_all_users, create_user,
    update_user, delete_user, get_user_by_id,
    get_all_fee_settings, get_fee_settings_by_category, update_fee_setting,
    create_session, validate_session, delete_session, cleanup_expired_sessions,
    log_session_event, get_session_logs, get_jst_now
)

FACILITY_OPTIONS = {
    FACILITY_HOUSE: "🏠 こぐまハウス",
    FACILITY_BABY: "👶 こぐまbaby"
}
from pricing import (
    calculate_total_price, calculate_extension_fee, needs_certification,
    calculate_auto_fee, is_holiday, get_rate_table,
    FACILITY_FEE, FACILITY_FEE_SITTER, CANCEL_FEE_RATE,
    SNACK_PRICE, HOUSEWORK_OPTION
)
from calc_logic import (
    calculate_temporary_care, calculate_facility_sitter, calculate_home_sitter,
    is_holiday_or_weekend, get_time_options, format_breakdown_text,
    FACILITY_FEE_TEMPORARY, FACILITY_FEE_SITTER as CALC_FACILITY_FEE_SITTER,
    SNACK_PRICE as CALC_SNACK_PRICE, HOUSEWORK_OPTION as CALC_HOUSEWORK_OPTION,
    SIBLING_DISCOUNT_PER_HOUR, SIBLING_ADDITION_PER_HOUR
)
from pdf_generator import generate_receipt_pdf
from care_notes import generate_care_summary, RECORD_TYPES, get_record_type_label

st.set_page_config(
    page_title="こぐまハウス",
    page_icon="🐻",
    layout="wide",
    initial_sidebar_state="collapsed"
)

if 'success_message' not in st.session_state:
    st.session_state.success_message = None
if 'success_message_key' not in st.session_state:
    st.session_state.success_message_key = None
if 'current_facility' not in st.session_state:
    st.session_state.current_facility = DEFAULT_FACILITY
if 'logged_in_user' not in st.session_state:
    st.session_state.logged_in_user = None
if 'session_checked' not in st.session_state:
    st.session_state.session_checked = False

COOKIE_NAME = "koguma_session"
SESSION_EXPIRY_DAYS = 30

def get_cookie_manager():
    """CookieManagerを取得（セッション全体で同一インスタンスを使用）"""
    if '_cookie_manager_instance' not in st.session_state:
        st.session_state._cookie_manager_instance = stx.CookieManager(key="koguma_cookies")
    return st.session_state._cookie_manager_instance


def restore_session_from_cookie():
    """Cookieからセッションを復元（CookieManager使用）"""
    if st.session_state.logged_in_user:
        return
    
    if st.session_state.get('_session_restore_done'):
        return
    
    cookie_manager = get_cookie_manager()
    session_token = cookie_manager.get(COOKIE_NAME)
    
    st.session_state._session_restore_done = True
    
    if session_token:
        log_session_event("RESTORE_ATTEMPT", session_token=session_token, details="Cookie復元試行")
        user = validate_session(session_token)
        if user:
            st.session_state.logged_in_user = user
            log_session_event(
                "RESTORE_SUCCESS",
                user_id=user['id'],
                username=user['username'],
                session_token=session_token,
                details="Cookie復元成功"
            )
        else:
            log_session_event(
                "RESTORE_FAILED",
                session_token=session_token,
                details="validate_sessionがNoneを返した"
            )
    else:
        if not st.session_state.get('_no_cookie_logged'):
            log_session_event("NO_COOKIE", details="Cookie取得失敗")
            st.session_state._no_cookie_logged = True


def is_logged_in() -> bool:
    return st.session_state.logged_in_user is not None


def get_current_user() -> dict:
    return st.session_state.logged_in_user


def is_admin() -> bool:
    user = get_current_user()
    return user is not None and user.get('role') == 'admin'


def login(user: dict):
    """ログイン処理（Cookieにセッショントークンを保存）"""
    st.session_state.logged_in_user = user
    
    session_token = create_session(user['id'])
    
    cookie_manager = get_cookie_manager()
    try:
        cookie_manager.set(
            COOKIE_NAME, 
            session_token,
            expires_at=get_jst_now() + timedelta(days=SESSION_EXPIRY_DAYS)
        )
        log_session_event(
            "LOGIN_SUCCESS",
            user_id=user['id'],
            username=user['username'],
            session_token=session_token,
            details=f"ログイン成功、Cookie設定完了（有効期限: {SESSION_EXPIRY_DAYS}日）"
        )
    except Exception as e:
        log_session_event(
            "LOGIN_COOKIE_ERROR",
            user_id=user['id'],
            username=user['username'],
            session_token=session_token,
            details=f"Cookie設定エラー: {str(e)}"
        )


def logout():
    """ログアウト処理（Cookieを削除）"""
    user = st.session_state.logged_in_user
    cookie_manager = get_cookie_manager()
    
    try:
        session_token = cookie_manager.get(COOKIE_NAME)
    except:
        session_token = None
    
    log_session_event(
        "LOGOUT",
        user_id=user.get('id') if user else None,
        username=user.get('username') if user else None,
        session_token=session_token,
        details="明示的ログアウト"
    )
    
    if session_token:
        delete_session(session_token)
        try:
            cookie_manager.delete(COOKIE_NAME)
        except:
            pass
    
    st.session_state.logged_in_user = None
    st.session_state._no_cookie_logged = False
    st.session_state._session_restore_done = False
    st.session_state._mismatch_logged = False


def get_current_facility() -> str:
    return st.session_state.get('current_facility', DEFAULT_FACILITY)


def get_facility_display_name(facility_id: str) -> str:
    return FACILITY_OPTIONS.get(facility_id, facility_id)

def show_success_message(key: str = None):
    if st.session_state.success_message and (key is None or st.session_state.success_message_key == key):
        st.success(st.session_state.success_message)
        st.session_state.success_message = None
        st.session_state.success_message_key = None

def set_success_message(msg: str, key: str = None):
    st.session_state.success_message = msg
    st.session_state.success_message_key = key

st.markdown("""
<style>
    /* Pull-to-Refresh（引っ張り更新）を無効化 - iPad/モバイル対応 */
    body, html {
        overscroll-behavior-y: none;
    }
    
    /* モバイルファースト - 基本スタイル */
    .main-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #5D4E37;
        padding: 0.5rem 0;
        text-align: center;
    }
    
    /* 大きなタッチボタン */
    .stButton > button {
        width: 100%;
        min-height: 60px;
        font-size: 1.1rem !important;
        font-weight: 600;
        border-radius: 12px;
        margin: 4px 0;
        touch-action: manipulation;
    }
    
    /* 登降園の大型ボタン */
    .big-action-btn button {
        min-height: 80px !important;
        font-size: 1.4rem !important;
    }
    
    /* プライマリボタン強調 */
    .stButton > button[kind="primary"] {
        min-height: 70px;
    }
    
    /* メニューカード */
    .menu-card {
        background: linear-gradient(135deg, #fff9f0 0%, #fff 100%);
        padding: 1.2rem;
        border-radius: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 0.8rem;
        border: 1px solid #f0e6d8;
    }
    
    /* 児童カード */
    .child-card {
        background: white;
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        margin-bottom: 0.8rem;
        border-left: 4px solid #8B7355;
    }
    
    /* ステータス表示 */
    .status-active {
        color: #28a745;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .status-cancelled {
        color: #dc3545;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .status-checkedin {
        color: #007bff;
        font-weight: bold;
    }
    
    /* 情報バッジ */
    .info-badge {
        display: inline-block;
        padding: 0.4rem 0.8rem;
        background: #f8f4ef;
        border-radius: 20px;
        font-size: 0.9rem;
        margin: 0.2rem;
    }
    
    /* セクション区切り */
    .section-divider {
        border-top: 2px solid #f0e6d8;
        margin: 1.5rem 0;
    }
    
    /* モバイル用フォント調整 */
    @media (max-width: 768px) {
        .main-header {
            font-size: 1.3rem;
        }
        .stButton > button {
            min-height: 56px;
            font-size: 1rem !important;
        }
        [data-testid="column"] {
            padding: 0 0.25rem !important;
        }
    }
    
    /* テーブルの横スクロール防止 */
    .stDataFrame {
        max-width: 100%;
        overflow-x: auto;
    }
    
    /* タブのタッチ対応 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        min-height: 50px;
        padding: 0.5rem 1rem;
        font-size: 1rem;
    }
    
    /* 入力フィールドの大きさ */
    .stSelectbox, .stNumberInput, .stTextInput {
        margin-bottom: 0.5rem;
    }
    .stSelectbox > div > div, 
    .stNumberInput > div > div > input,
    .stTextInput > div > div > input {
        min-height: 48px;
        font-size: 1rem;
    }
    
    /* メトリクス表示 */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    
    /* サイドバーが閉じている時のヒント非表示 */
    .css-1oe5cao {
        display: none;
    }
    
    /* 午睡チェック監査用テーブル */
    .nap-check-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
        font-size: 0.95rem;
    }
    .nap-check-table th, .nap-check-table td {
        border: 1px solid #ccc;
        padding: 8px 12px;
        text-align: center;
        vertical-align: middle;
    }
    .nap-check-table th {
        background: #f5f0e8;
        font-weight: bold;
        color: #5D4E37;
    }
    .nap-check-table tr:nth-child(even) {
        background: #fafafa;
    }
    .nap-check-table tr:hover {
        background: #f0ebe3;
    }
    
    /* 矢印ボタン */
    .arrow-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border: 2px solid #ccc;
        border-radius: 8px;
        background: white;
        font-size: 1.2rem;
        cursor: pointer;
        margin: 2px;
        transition: all 0.2s;
    }
    .arrow-btn:hover {
        background: #f0f0f0;
    }
    .arrow-btn.selected {
        background: #e3f2fd;
        border-color: #2196f3;
        color: #1976d2;
    }
    
    /* 体位修正マーク（◯） */
    .corrected-mark {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
    }
    .corrected-mark.active::after {
        content: '';
        position: absolute;
        width: 36px;
        height: 36px;
        border: 3px solid #e53935;
        border-radius: 50%;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
    }
</style>
""", unsafe_allow_html=True)

init_database()

if 'selected_reservation_id' not in st.session_state:
    st.session_state.selected_reservation_id = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "home"
if 'care_data_loaded' not in st.session_state:
    st.session_state.care_data_loaded = {}
if 'renrakucho_temp_save' not in st.session_state:
    st.session_state.renrakucho_temp_save = {}

def load_care_data_to_session(reservation_id: int, force_reload: bool = False):
    """DBからケア記録を読み込んでsession_stateにセット"""
    rid = reservation_id
    db_key = f"care_db_{rid}"
    
    # 常に最新のデータを取得するように修正（Stateが消える問題への対応）
    records = get_care_records(reservation_id)
    
    care_data = {}
    
    for record in records:
        record_type = record.get('record_type', '')
        details = record.get('details', '') or ''
        
        if record_type == 'temperature_1' and details:
            parts = details.split(' ', 1)
            if len(parts) >= 2:
                try:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data['temp1_time'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    temp_str = parts[1].replace('℃', '').strip()
                    care_data['temp1_val'] = float(temp_str)
                except:
                    pass
        
        elif record_type == 'temperature_2' and details:
            parts = details.split(' ', 1)
            if len(parts) >= 2:
                try:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data['temp2_time'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    temp_str = parts[1].replace('℃', '').strip()
                    care_data['temp2_val'] = float(temp_str)
                except:
                    pass
        
        elif record_type == 'lunch' and details:
            parts = details.split(' ', 2)
            if len(parts) >= 2:
                care_data['lunch_time'] = parts[0]
                care_data['lunch_amount'] = parts[1]
                if len(parts) >= 3:
                    care_data['lunch_content'] = parts[2]
        
        elif record_type == 'snack' and details:
            parts = details.split(' ', 2)
            if len(parts) >= 2:
                care_data['snack_time'] = parts[0]
                care_data['snack_amount'] = parts[1]
                if len(parts) >= 3:
                    care_data['snack_content'] = parts[2]
        
        elif record_type == 'dinner' and details:
            parts = details.split(' ', 1)
            if len(parts) >= 2:
                try:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data['dinner_time'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    care_data['dinner_amount'] = parts[1]
                except:
                    pass
        
        elif record_type == 'milk' and details:
            parts = details.split(' ', 1)
            if len(parts) >= 2:
                try:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data['milk_time_1'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    ml_str = parts[1].replace('ml', '').strip()
                    care_data['milk_amount_1'] = int(ml_str)
                except:
                    pass
        
        elif record_type.startswith('milk_'):
            try:
                idx = int(record_type.split('_')[1])
                parts = details.split(' ', 1)
                if len(parts) >= 2:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data[f'milk_time_{idx}'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    ml_str = parts[1].replace('ml', '').strip()
                    care_data[f'milk_amount_{idx}'] = int(ml_str)
            except:
                pass
        
        elif record_type.startswith('stool_'):
            try:
                idx = int(record_type.split('_')[1])
                parts = details.split(' ', 1)
                if len(parts) >= 2:
                    time_parts = parts[0].split(':')
                    if len(time_parts) == 2:
                        from datetime import time as dt_time
                        care_data[f'stool_time_{idx}'] = dt_time(int(time_parts[0]), int(time_parts[1]))
                    care_data[f'stool_type_{idx}'] = parts[1]
            except:
                pass
        
        elif record_type == 'nap' or record_type.startswith('nap_'):
            try:
                if record_type == 'nap':
                    idx = 1
                else:
                    idx = int(record_type.split('_')[1])
                if '〜' in details:
                    nap_parts = details.split('〜')
                    care_data[f'nap_start_{idx}'] = nap_parts[0]
                    if len(nap_parts) > 1 and nap_parts[1]:
                        care_data[f'nap_end_{idx}'] = nap_parts[1]
            except:
                pass
        
        elif record_type == 'other' and details:
            care_data['other_note'] = details
    
    st.session_state[db_key] = care_data


def generate_5min_intervals(start_time_str: str, end_time_str: str):
    """開始時間から終了時間まで5分刻みの時刻リストを生成"""
    intervals = []
    
    if not start_time_str or not end_time_str:
        return intervals
    
    try:
        start_parts = start_time_str.split(':')
        start_h, start_m = int(start_parts[0]), int(start_parts[1])
        
        end_parts = end_time_str.split(':')
        end_h, end_m = int(end_parts[0]), int(end_parts[1])
        
        current_h, current_m = start_h, start_m
        
        while (current_h < end_h) or (current_h == end_h and current_m <= end_m):
            intervals.append(f"{current_h:02d}:{current_m:02d}")
            current_m += 5
            if current_m >= 60:
                current_m = 0
                current_h += 1
            if current_h >= 24:
                break
            if len(intervals) > 100:
                break
                
    except Exception as e:
        pass
    
    return intervals


def show_nap_check_detail(rid: int, nap_index: int, start_time: str, end_time: str):
    """午睡チェック詳細画面（5分刻みテーブル）"""
    
    st.markdown(f"### 😴 お昼寝{nap_index} 詳細チェック")
    st.markdown(f"**時間帯**: {start_time} 〜 {end_time if end_time else '（終了未設定）'}")
    
    intervals = generate_5min_intervals(start_time, end_time if end_time else "")
    
    if not intervals:
        st.warning("入眠・起床時間を設定してから詳細チェックを行ってください")
        return
    
    existing_logs = get_nap_check_logs(rid, nap_index)
    logs_dict = {log['check_time']: log for log in existing_logs}
    
    facility = get_current_facility()
    staff_list = get_staff_list(facility)
    staff_names = ["---"] + [s['name'] for s in staff_list]
    
    # 午睡チェックの状態管理
    nap_state_key = f"nap_check_state_{rid}_{nap_index}"
    if nap_state_key not in st.session_state:
        st.session_state[nap_state_key] = {}
    
    # 担当者自動入力のための前回値保持
    prev_staff_key = f"prev_staff_{rid}"
    
    for time_slot in intervals:
        if time_slot not in st.session_state[nap_state_key]:
            if time_slot in logs_dict:
                log = logs_dict[time_slot]
                st.session_state[nap_state_key][time_slot] = {
                    'direction': log['arrow_direction'],
                    'corrected': bool(log['is_corrected']),
                    'staff': log['staff_name'] or "---"
                }
            else:
                # 1回目以降のデフォルト担当者設定
                default_staff = "---"
                if prev_staff_key in st.session_state:
                    default_staff = st.session_state[prev_staff_key]
                
                st.session_state[nap_state_key][time_slot] = {
                    'direction': 'up',
                    'corrected': False,
                    'staff': default_staff
                }
    
    arrow_labels = {'up': '↑', 'down': '↓', 'left': '←', 'right': '→'}
    arrow_names = {'up': '仰向け', 'down': 'うつ伏せ', 'left': '左向き', 'right': '右向き'}
    
    st.markdown("---")
    
    st.markdown("**👤 担当者一括設定**")
    bulk_col1, bulk_col2 = st.columns([2, 1])
    with bulk_col1:
        bulk_staff = st.selectbox(
            "一括設定する担当者",
            staff_names,
            key=f"bulk_staff_{rid}_{nap_index}",
            label_visibility="collapsed"
        )
    with bulk_col2:
        if st.button("全員に設定", key=f"bulk_apply_{rid}_{nap_index}", use_container_width=True):
            if bulk_staff != "---":
                for ts in intervals:
                    st.session_state[nap_state_key][ts]['staff'] = bulk_staff
                st.session_state[prev_staff_key] = bulk_staff
                st.rerun()
            else:
                st.warning("担当者を選択してください")
    
    st.markdown("---")
    st.markdown("**凡例**: ↑仰向け ↓うつ伏せ ←左向き →右向き  ◯=体位修正あり")
    st.markdown("---")
    
    col_h1, col_h2, col_h3, col_h4 = st.columns([1, 2, 1, 2])
    with col_h1:
        st.markdown("**時刻**")
    with col_h2:
        st.markdown("**姿勢**")
    with col_h3:
        st.markdown("**修正**")
    with col_h4:
        st.markdown("**担当者**")
    
    st.markdown("---")
    
    for idx, time_slot in enumerate(intervals):
        state = st.session_state[nap_state_key][time_slot]
        
        col1, col2, col3, col4 = st.columns([1, 2, 1, 2])
        
        with col1:
            st.markdown(f"**{time_slot}**")
        
        with col2:
            directions = ['up', 'down', 'left', 'right']
            dir_cols = st.columns(4)
            for d_idx, direction in enumerate(directions):
                with dir_cols[d_idx]:
                    is_selected = state['direction'] == direction
                    btn_label = arrow_labels[direction]
                    if state['corrected'] and is_selected:
                        btn_label = f"⭕{arrow_labels[direction]}"
                    btn_type = "primary" if is_selected else "secondary"
                    if st.button(btn_label, key=f"arrow_{rid}_{nap_index}_{time_slot}_{direction}", 
                                type=btn_type, use_container_width=True):
                        st.session_state[nap_state_key][time_slot]['direction'] = direction
                        st.rerun()
        
        with col3:
            corrected = st.checkbox("◯", value=state['corrected'], 
                                   key=f"corrected_{rid}_{nap_index}_{time_slot}",
                                   label_visibility="collapsed")
            if corrected != state['corrected']:
                st.session_state[nap_state_key][time_slot]['corrected'] = corrected
        
        with col4:
            prev_staff = "---"
            if idx > 0:
                prev_time = intervals[idx - 1]
                prev_staff = st.session_state[nap_state_key].get(prev_time, {}).get('staff', "---")
            
            current_staff = state['staff']
            if current_staff == "---" and prev_staff != "---":
                current_staff = prev_staff
                st.session_state[nap_state_key][time_slot]['staff'] = current_staff
            
            staff_idx = staff_names.index(current_staff) if current_staff in staff_names else 0
            selected_staff = st.selectbox(
                "担当",
                staff_names,
                index=staff_idx,
                key=f"staff_{rid}_{nap_index}_{time_slot}",
                label_visibility="collapsed"
            )
            if selected_staff != state['staff']:
                st.session_state[nap_state_key][time_slot]['staff'] = selected_staff
                st.session_state[prev_staff_key] = selected_staff
                propagated = False
                for other_idx in [1, 2, 3]:
                    other_key = f"nap_check_state_{rid}_{other_idx}"
                    if other_key in st.session_state:
                        for ts in st.session_state[other_key]:
                            if st.session_state[other_key][ts].get('staff') == "---":
                                st.session_state[other_key][ts]['staff'] = selected_staff
                                propagated = True
                if propagated:
                    st.rerun()
        
        st.markdown('<hr style="margin:4px 0; border:none; border-top:1px solid #eee;">', unsafe_allow_html=True)
    
    st.markdown("---")
    
    missing_staff_count = sum(1 for ts in intervals if st.session_state[nap_state_key][ts]['staff'] == "---")
    if missing_staff_count > 0:
        st.warning(f"⚠️ {missing_staff_count}件の時刻で担当者が未選択です")
    
    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("💾 一括保存", key=f"save_nap_check_{rid}_{nap_index}", 
                    type="primary", use_container_width=True):
            if missing_staff_count > 0:
                st.error("全ての時刻に担当者を選択してから保存してください")
            else:
                for time_slot in intervals:
                    state = st.session_state[nap_state_key][time_slot]
                    save_nap_check_log(
                        rid, nap_index, time_slot,
                        state['direction'], state['corrected'], state['staff']
                    )
                st.success(f"✅ {len(intervals)}件の午睡チェックを保存しました")
                if nap_state_key in st.session_state:
                    del st.session_state[nap_state_key]
                st.rerun()
    
    with col_clear:
        if st.button("🗑️ クリア", key=f"clear_nap_check_{rid}_{nap_index}", use_container_width=True):
            delete_nap_check_logs(rid, nap_index)
            if nap_state_key in st.session_state:
                del st.session_state[nap_state_key]
            st.success("午睡チェック記録をクリアしました")
            st.rerun()


def navigate_to(page_name: str):
    st.session_state.current_page = page_name

def show_facility_selector():
    """ヘッダーに施設切替セレクターを表示"""
    facility_options = list(FACILITY_OPTIONS.keys())
    facility_labels = list(FACILITY_OPTIONS.values())
    current_idx = facility_options.index(get_current_facility()) if get_current_facility() in facility_options else 0
    
    selected_label = st.selectbox(
        "施設選択",
        facility_labels,
        index=current_idx,
        key="facility_selector",
        label_visibility="collapsed"
    )
    
    selected_facility = facility_options[facility_labels.index(selected_label)]
    if selected_facility != st.session_state.current_facility:
        st.session_state.current_facility = selected_facility
        st.rerun()


def show_login_page():
    st.markdown('<div class="main-header">🐻 こぐまハウス</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#8B7355;margin-bottom:2rem;">業務支援システム</p>', unsafe_allow_html=True)
    
    st.markdown("### 🔐 ログイン")
    
    with st.form("login_form"):
        username = st.text_input("ユーザーID", placeholder="ユーザーIDを入力")
        password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
        submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)
        
        if submitted:
            if username and password:
                user = authenticate_user(username, password)
                if user:
                    login(user)
                    st.rerun()
                else:
                    st.error("ユーザーIDまたはパスワードが正しくありません")
            else:
                st.warning("ユーザーIDとパスワードを入力してください")
    
    st.markdown("---")
    st.markdown('<p style="text-align:center;color:#999;font-size:0.8rem;">初回ログイン: admin / admin123</p>', unsafe_allow_html=True)


def main():
    init_database()
    cleanup_expired_sessions()
    
    restore_session_from_cookie()
    
    if not is_logged_in():
        show_login_page()
        return
    
    current_user = get_current_user()
    user_is_admin = is_admin()
    
    show_facility_selector()
    
    facility_name = get_facility_display_name(get_current_facility())
    st.sidebar.markdown(f"## {facility_name}")
    role_display = "👑 管理者" if user_is_admin else "👤 スタッフ"
    st.sidebar.markdown(f"{role_display}: {current_user.get('display_name', current_user.get('username'))}")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🏠 ホーム", use_container_width=True):
        navigate_to("home")
        st.rerun()
    if st.sidebar.button("📁 データ取込", use_container_width=True):
        navigate_to("import")
        st.rerun()
    if st.sidebar.button("👶 本日の児童", use_container_width=True):
        navigate_to("today")
        st.rerun()
    if st.sidebar.button("📋 予約一覧", use_container_width=True):
        navigate_to("reservations")
        st.rerun()
    if st.sidebar.button("📝 実績入力", use_container_width=True):
        navigate_to("record")
        st.rerun()
    if st.sidebar.button("🧾 領収書発行", use_container_width=True):
        navigate_to("receipt")
        st.rerun()
    if st.sidebar.button("🧮 料金計算", use_container_width=True):
        navigate_to("fee_calc")
        st.rerun()
    
    st.sidebar.markdown("---")
    if user_is_admin:
        if st.sidebar.button("🔧 管理者ダッシュボード", use_container_width=True):
            navigate_to("admin")
            st.rerun()
    if st.sidebar.button("⚙️ 設定", use_container_width=True):
        navigate_to("settings")
        st.rerun()
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 ログアウト", use_container_width=True):
        logout()
        st.rerun()
    
    page = st.session_state.current_page
    
    if not user_is_admin and page == "admin":
        page = "home"
        st.session_state.current_page = "home"
    
    if page == "home":
        show_home()
    elif page == "import":
        show_data_import()
    elif page == "today":
        show_today_children()
    elif page == "reservations":
        show_reservations()
    elif page == "record":
        show_record_input()
    elif page == "receipt":
        show_receipt_generation()
    elif page == "fee_calc":
        show_fee_calculator()
    elif page == "admin":
        if user_is_admin:
            show_admin_dashboard()
        else:
            show_receipt_generation()
    elif page == "settings":
        show_settings()
    else:
        if user_is_admin:
            show_home()
        else:
            show_receipt_generation()

def show_home():
    facility = get_current_facility()
    facility_name = get_facility_display_name(facility)
    
    current_user = get_current_user()
    user_is_admin = is_admin()
    role_text = "👑 管理者" if user_is_admin else "👤 スタッフ"
    user_display = current_user.get('display_name', current_user.get('username', ''))
    
    col_info, col_logout = st.columns([3, 1])
    with col_info:
        st.markdown(f"**{role_text}**: {user_display}")
    with col_logout:
        if st.button("🚪 ログアウト", key="logout_home", use_container_width=True):
            logout()
            st.rerun()
    
    if user_is_admin:
        if st.button("🔧 管理者ダッシュボード", key="admin_quick", use_container_width=True):
            navigate_to("admin")
            st.rerun()
    
    st.markdown("---")
    
    st.markdown(f'<div class="main-header">{facility_name}</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#8B7355;margin-bottom:1rem;">業務支援システム</p>', unsafe_allow_html=True)
    
    today = date.today().isoformat()
    today_reservations = get_reservations_by_date(today, facility)
    
    col1, col2 = st.columns(2)
    with col1:
        active = sum(1 for r in today_reservations if not r.get('is_cancelled'))
        st.metric("📅 本日の予約", f"{len(today_reservations)}件")
    with col2:
        st.metric("✅ 受入予定", f"{active}件")
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("### 🚀 クイックアクション")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👶 本日の児童", type="primary", use_container_width=True):
            navigate_to("today")
            st.rerun()
    with col2:
        if st.button("📝 実績入力", type="primary", use_container_width=True):
            navigate_to("record")
            st.rerun()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📁 データ取込", use_container_width=True):
            navigate_to("import")
            st.rerun()
    with col2:
        if st.button("🧾 領収書発行", use_container_width=True):
            navigate_to("receipt")
            st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("### 📋 本日の予約")
    
    if today_reservations:
        for res in today_reservations:
            show_child_card(res, show_quick_actions=True)
    else:
        st.info("📭 本日の予約はありません")

def show_child_card(res: dict, show_quick_actions: bool = False):
    is_cancelled = res.get('is_cancelled', 0)
    has_checkin = res.get('check_in_time')
    has_checkout = res.get('check_out_time')
    
    if is_cancelled:
        status = "❌ キャンセル"
        status_class = "status-cancelled"
    elif has_checkout:
        status = "🏁 降園済"
        status_class = "status-checkedin"
    elif has_checkin:
        status = "🟢 在園中"
        status_class = "status-active"
    else:
        status = "⏳ 予定"
        status_class = "status-active"
    
    with st.container():
        st.markdown(f"""
        <div class="child-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
                <div>
                    <strong style="font-size:1.2rem;">{res.get('child_name', '')}</strong>
                    <span style="color:#888;margin-left:0.5rem;">({res.get('child_name_kana', '')})</span>
                </div>
                <span class="{status_class}">{status}</span>
            </div>
            <div style="margin-top:0.5rem;">
                <span class="info-badge">⏰ {res.get('start_time', '')} - {res.get('end_time', '')}</span>
                <span class="info-badge">📋 {res.get('service_category', '')[:8]}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if show_quick_actions and not is_cancelled:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📝 詳細を開く", key=f"detail_{res['id']}", use_container_width=True):
                    st.session_state.selected_reservation_id = res['id']
                    navigate_to("record")
                    st.rerun()
            with col2:
                if not has_checkin:
                    if st.button("🟢 登園", key=f"quick_in_{res['id']}", use_container_width=True):
                        update_attendance(res['id'], {'check_in_time': get_jst_now().isoformat()})
                        st.rerun()
                elif not has_checkout:
                    if st.button("🔴 降園", key=f"quick_out_{res['id']}", use_container_width=True):
                        now = get_jst_now()
                        update_data = {'check_out_time': now.isoformat()}
                        scheduled_end = res.get('end_time', '')
                        if scheduled_end:
                            ext_min, ext_fee = calculate_extension_fee(scheduled_end, now.strftime("%H:%M"))
                            if ext_min > 0:
                                update_data['extension_minutes'] = ext_min
                                update_data['extension_fee'] = ext_fee
                        update_attendance(res['id'], update_data)
                        st.rerun()

def show_data_import():
    st.markdown('<div class="main-header">📁 データ取込</div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "CSVファイルを選択",
        type=['csv'],
        help="SelectType形式のCSVファイル"
    )
    
    if uploaded_file:
        try:
            encodings = ['shift_jis', 'cp932', 'utf-8', 'utf-8-sig', 'euc_jp']
            df = None
            
            for encoding in encodings:
                try:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding=encoding)
                    break
                except:
                    continue
            
            if df is None:
                st.error("ファイルの読み込みに失敗しました")
                return
            
            st.success(f"✅ {len(df)}件のデータを読み込みました")
            
            with st.expander("📊 プレビュー"):
                st.dataframe(df.head(5), use_container_width=True)
            
            facility = get_current_facility()
            facility_name = get_facility_display_name(facility)
            st.info(f"📌 取込先施設: **{facility_name}**")
            
            if st.button("📥 データベースに取り込む", type="primary", use_container_width=True):
                with st.spinner("取込中..."):
                    count = import_csv_data(df, facility)
                    st.success(f"✅ {count}件を「{facility_name}」に取り込みました！")
                    st.balloons()
        
        except Exception as e:
            st.error(f"エラー: {str(e)}")

def show_today_children():
    facility = get_current_facility()
    st.markdown('<div class="main-header">👶 本日の児童</div>', unsafe_allow_html=True)
    
    selected_date = st.date_input(
        "日付",
        value=date.today(),
        label_visibility="collapsed"
    )
    
    reservations = get_reservations_by_date(selected_date.isoformat(), facility)
    
    if not reservations:
        st.info("📭 予約がありません")
        return
    
    active = [r for r in reservations if not r.get('is_cancelled')]
    cancelled = [r for r in reservations if r.get('is_cancelled')]
    
    st.markdown(f"### 📋 予約一覧（{len(active)}件）")
    
    for res in active:
        show_child_card(res, show_quick_actions=True)
    
    if cancelled:
        with st.expander(f"❌ キャンセル済み（{len(cancelled)}件）"):
            for res in cancelled:
                show_child_card(res)

def show_reservations():
    facility = get_current_facility()
    st.markdown('<div class="main-header">📋 予約一覧</div>', unsafe_allow_html=True)
    
    if st.session_state.selected_reservation_id:
        show_detail_input(st.session_state.selected_reservation_id)
        return
    
    today = date.today()
    
    st.markdown("**📅 期間選択**")
    filter_type = st.radio(
        "表示期間",
        ["今月", "日付指定", "月指定"],
        horizontal=True,
        key="res_filter_type"
    )
    
    if filter_type == "今月":
        reservations = get_reservations_by_month(today.year, today.month, facility)
        st.info(f"📅 {today.year}年{today.month}月の予約を表示中")
    elif filter_type == "日付指定":
        selected_date = st.date_input("日付を選択", value=today, key="res_date")
        reservations = get_reservations_by_date(selected_date.isoformat(), facility)
        st.info(f"📅 {selected_date.strftime('%Y年%m月%d日')}の予約を表示中")
    else:
        col1, col2 = st.columns(2)
        with col1:
            sel_year = st.selectbox("年", range(today.year - 1, today.year + 2), index=1, key="res_year")
        with col2:
            sel_month = st.selectbox("月", range(1, 13), index=today.month - 1, key="res_month")
        reservations = get_reservations_by_month(sel_year, sel_month, facility)
        st.info(f"📅 {sel_year}年{sel_month}月の予約を表示中")
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    if not reservations:
        st.info("📭 該当する予約データがありません")
        return
    
    search_name = st.text_input("🔍 名前で検索", placeholder="お子様の名前")
    
    category_options = ["すべて", "一時預かり保育", "ベビーシッター（施設型）", "ベビーシッター（自宅派遣型）"]
    category_filter = st.radio(
        "サービス区分",
        category_options,
        horizontal=True,
        label_visibility="collapsed"
    )
    
    filtered = reservations
    if search_name:
        filtered = [r for r in filtered if search_name in r.get('child_name', '') or search_name in r.get('child_name_kana', '')]
    if category_filter != "すべて":
        filtered = [r for r in filtered if r.get('service_category') == category_filter]
    
    st.markdown(f"**{len(filtered)}件**")
    
    for res in filtered[:50]:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"""
                <div style="padding:0.5rem 0;">
                    <strong>{res.get('child_name', '')}</strong><br>
                    <small style="color:#666;">{res.get('reservation_date', '')} | ¥{(res.get('total_amount', 0) or 0):,}</small>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                if st.button("選択", key=f"sel_{res['id']}", use_container_width=True):
                    st.session_state.selected_reservation_id = res['id']
                    st.rerun()
            st.divider()

def show_record_input():
    st.markdown('<div class="main-header">📝 実績入力</div>', unsafe_allow_html=True)
    
    if st.session_state.selected_reservation_id:
        show_detail_input(st.session_state.selected_reservation_id)
    else:
        st.info("👇 児童を選択してください")
        
        today = date.today()
        
        st.markdown("**📅 日付選択**")
        filter_type = st.radio(
            "表示期間",
            ["今日", "日付指定", "月指定"],
            horizontal=True,
            key="rec_filter_type"
        )
        
        facility = get_current_facility()
        
        if filter_type == "今日":
            reservations = get_reservations_by_date(today.isoformat(), facility)
            st.info(f"📅 {today.strftime('%Y年%m月%d日')}（今日）の予約")
        elif filter_type == "日付指定":
            selected_date = st.date_input("日付を選択", value=today, key="rec_date")
            reservations = get_reservations_by_date(selected_date.isoformat(), facility)
            st.info(f"📅 {selected_date.strftime('%Y年%m月%d日')}の予約")
        else:
            col1, col2 = st.columns(2)
            with col1:
                sel_year = st.selectbox("年", range(today.year - 1, today.year + 2), index=1, key="rec_year")
            with col2:
                sel_month = st.selectbox("月", range(1, 13), index=today.month - 1, key="rec_month")
            reservations = get_reservations_by_month(sel_year, sel_month, facility)
            st.info(f"📅 {sel_year}年{sel_month}月の予約")
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        active_reservations = [r for r in reservations if not r.get('is_cancelled')]
        
        if active_reservations:
            st.markdown(f"### 📋 予約一覧（{len(active_reservations)}件）")
            for res in active_reservations:
                show_child_card(res, show_quick_actions=True)
        else:
            st.write("該当する予約はありません")

def show_detail_input(reservation_id: int):
    res = get_reservation_by_id(reservation_id)
    
    if not res:
        st.error("予約が見つかりません")
        st.session_state.selected_reservation_id = None
        return
    
    load_care_data_to_session(reservation_id, force_reload=True)
    
    if st.button("← 戻る", use_container_width=True):
        st.session_state.selected_reservation_id = None
        st.rerun()
    
    st.markdown(f"""
    <div class="menu-card">
        <h2 style="margin:0;">👶 {res.get('child_name', '')}</h2>
        <p style="color:#666;margin:0.3rem 0;">({res.get('child_name_kana', '')})</p>
        <div style="margin-top:0.5rem;">
            <span class="info-badge">📅 {res.get('reservation_date', '')}</span>
            <span class="info-badge">⏰ {res.get('start_time', '')} - {res.get('end_time', '')}</span>
        </div>
        <div style="margin-top:0.3rem;">
            <span class="info-badge">📋 {res.get('service_category', '')}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["🚪 登降園", "🍚 ケア", "💰 料金", "📄 連絡帳"])
    
    with tab1:
        show_attendance_tab(res)
    
    with tab2:
        show_care_tab(res)
    
    with tab3:
        show_pricing_tab(res)
    
    with tab4:
        show_notes_tab(res)

def show_attendance_tab(res: dict):
    st.markdown("### 🚪 登降園")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if res.get('check_in_time'):
            check_in_display = res['check_in_time'][:16].replace('T', ' ')
            st.success(f"🟢 登園済\n{check_in_display}")
        else:
            st.markdown('<div class="big-action-btn">', unsafe_allow_html=True)
            if st.button("🟢 登園", type="primary", use_container_width=True, key="checkin_main"):
                update_attendance(res['id'], {'check_in_time': get_jst_now().isoformat()})
                st.success("登園を記録しました！")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        if res.get('check_out_time'):
            check_out_display = res['check_out_time'][:16].replace('T', ' ')
            st.success(f"🔴 降園済\n{check_out_display}")
            ext = res.get('extension_minutes', 0)
            if ext > 0:
                st.warning(f"⏰ 延長{ext}分")
        else:
            st.markdown('<div class="big-action-btn">', unsafe_allow_html=True)
            if st.button("🔴 降園", type="primary", use_container_width=True, key="checkout_main"):
                now = get_jst_now()
                update_data = {'check_out_time': now.isoformat()}
                
                scheduled_end = res.get('end_time', '')
                if scheduled_end:
                    ext_min, ext_fee = calculate_extension_fee(scheduled_end, now.strftime("%H:%M"))
                    if ext_min > 0:
                        update_data['extension_minutes'] = ext_min
                        update_data['extension_fee'] = ext_fee
                
                update_attendance(res['id'], update_data)
                st.success("降園を記録しました！")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    if res.get('check_in_time'):
        st.info("✅ 登園済のためキャンセルはできません")
    elif res.get('is_cancelled'):
        st.markdown("### ❌ キャンセル")
        st.warning(f"キャンセル済み（{res.get('cancel_type', '')}）")
    else:
        st.markdown("### ❌ キャンセル")
        cancel_type = st.radio(
            "キャンセル種別",
            ["キャンセルしない", "当日キャンセル（50%請求）", "無料キャンセル"],
            horizontal=False,
            label_visibility="collapsed"
        )
        
        if cancel_type != "キャンセルしない":
            if st.button("⚠️ キャンセル確定", type="secondary", use_container_width=True):
                if "当日" in cancel_type:
                    base_price = res.get('base_price', 0) or 0
                    cancel_amount = int(base_price * CANCEL_FEE_RATE)
                    update_attendance(res['id'], {
                        'is_cancelled': 1,
                        'cancel_type': '当日キャンセル',
                        'total_amount': cancel_amount
                    })
                    st.warning(f"当日キャンセル（請求: ¥{cancel_amount:,}）")
                else:
                    update_attendance(res['id'], {
                        'is_cancelled': 1,
                        'cancel_type': '無料キャンセル',
                        'total_amount': 0
                    })
                    st.info("無料キャンセルしました")
                st.rerun()

def show_care_tab(res: dict):
    st.markdown("### 🍚 ケア記録")
    
    rid = res['id']
    db_key = f"care_db_{rid}"
    care_data = st.session_state.get(db_key, {})
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 再読込", key=f"refresh_care_{rid}", use_container_width=True):
            load_care_data_to_session(rid, force_reload=True)
            st.rerun()
    
    care_records = get_care_records(rid)
    
    amount_options = ["---", "完食", "ほぼ完食", "半分", "少し", "食べなかった"]
    stool_options = ["---", "普通", "軟便", "硬便", "下痢"]
    
    lunch_time_options = ["---"] + [f"{h:02d}:{m:02d}" for h in range(10, 15) for m in [0, 15, 30, 45] if not (h == 14 and m > 0)]
    snack_time_options = ["---"] + [f"{h:02d}:{m:02d}" for h in range(13, 17) for m in [0, 15, 30, 45] if not (h == 16 and m > 0)]
    nap_time_options = ["---"] + [f"{h:02d}:{m:02d}" for h in range(6, 23) for m in [0, 15, 30, 45] if not (h == 22 and m > 0)]
    
    st.markdown("**🌡️ 体温**")
    show_success_message("temp")
    
    temp1_time_default = care_data.get('temp1_time', None)
    temp1_val_default = care_data.get('temp1_val', 36.5)
    temp2_time_default = care_data.get('temp2_time', None)
    temp2_val_default = care_data.get('temp2_val', 36.5)
    
    col1, col2 = st.columns(2)
    with col1:
        temp1_time = st.time_input("検温時刻①", value=temp1_time_default, key=f"temp1_time_{rid}")
    with col2:
        temp1_val = st.number_input("体温①（℃）", min_value=35.0, max_value=42.0, value=temp1_val_default, step=0.1, format="%.1f", key=f"temp1_val_{rid}")
    
    col1, col2 = st.columns(2)
    with col1:
        temp2_time = st.time_input("検温時刻②", value=temp2_time_default, key=f"temp2_time_{rid}")
    with col2:
        temp2_val = st.number_input("体温②（℃）", min_value=35.0, max_value=42.0, value=temp2_val_default, step=0.1, format="%.1f", key=f"temp2_val_{rid}")
    
    if st.button("🌡️ 体温を記録", key=f"save_temp_{rid}", use_container_width=True):
        recorded = False
        if temp1_time:
            add_care_record(rid, 'temperature', f"{temp1_time.strftime('%H:%M')} {temp1_val:.1f}℃", index=1)
            recorded = True
        if temp2_time:
            add_care_record(rid, 'temperature', f"{temp2_time.strftime('%H:%M')} {temp2_val:.1f}℃", index=2)
            recorded = True
        if recorded:
            set_success_message("✅ 体温を記録しました", "temp")
            if db_key in st.session_state:
                del st.session_state[db_key]
        st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("**🍽️ 昼食**")
    show_success_message("lunch")
    lunch_time_default = care_data.get('lunch_time', "---")
    lunch_amount_default = care_data.get('lunch_amount', "---")
    lunch_content_default = care_data.get('lunch_content', "")
    lunch_time_idx = lunch_time_options.index(lunch_time_default) if lunch_time_default in lunch_time_options else 0
    lunch_amount_idx = amount_options.index(lunch_amount_default) if lunch_amount_default in amount_options else 0
    col1, col2 = st.columns(2)
    with col1:
        lunch_time = st.selectbox("昼食時刻", lunch_time_options, index=lunch_time_idx, key=f"lunch_time_{rid}")
    with col2:
        lunch_amount = st.selectbox("昼食の量", amount_options, index=lunch_amount_idx, key=f"lunch_amount_{rid}")
    lunch_content = st.text_input("昼食内容（15文字程度）", value=lunch_content_default, max_chars=20, key=f"lunch_content_{rid}", placeholder="例：ご飯、味噌汁、煮物")
    if st.button("🍚 昼食を記録", key=f"save_lunch_{rid}", use_container_width=True):
        if lunch_time != "---" and lunch_amount != "---":
            details = f"{lunch_time} {lunch_amount}"
            if lunch_content:
                details += f" {lunch_content}"
            add_care_record(rid, 'lunch', details)
            set_success_message("✅ 昼食を記録しました", "lunch")
            if db_key in st.session_state:
                del st.session_state[db_key]
            st.rerun()
    
    st.markdown("**🍪 おやつ**")
    show_success_message("snack")
    snack_time_default = care_data.get('snack_time', "---")
    snack_amount_default = care_data.get('snack_amount', "---")
    snack_content_default = care_data.get('snack_content', "")
    snack_time_idx = snack_time_options.index(snack_time_default) if snack_time_default in snack_time_options else 0
    snack_amount_idx = amount_options.index(snack_amount_default) if snack_amount_default in amount_options else 0
    col1, col2 = st.columns(2)
    with col1:
        snack_time = st.selectbox("おやつ時刻", snack_time_options, index=snack_time_idx, key=f"snack_time_{rid}")
    with col2:
        snack_amount = st.selectbox("おやつの量", amount_options, index=snack_amount_idx, key=f"snack_amount_{rid}")
    snack_content = st.text_input("おやつ内容（15文字程度）", value=snack_content_default, max_chars=20, key=f"snack_content_{rid}", placeholder="例：ビスケット、牛乳")
    if st.button("🍪 おやつを記録", key=f"save_snack_{rid}", use_container_width=True):
        if snack_time != "---" and snack_amount != "---":
            details = f"{snack_time} {snack_amount}"
            if snack_content:
                details += f" {snack_content}"
            add_care_record(rid, 'snack', details)
            set_success_message("✅ おやつを記録しました", "snack")
            if db_key in st.session_state:
                del st.session_state[db_key]
            st.rerun()
    
    st.markdown("**🍽️ 夕食**")
    show_success_message("dinner")
    dinner_time_default = care_data.get('dinner_time', None)
    dinner_amount_default = care_data.get('dinner_amount', "---")
    dinner_amount_idx = amount_options.index(dinner_amount_default) if dinner_amount_default in amount_options else 0
    col1, col2 = st.columns(2)
    with col1:
        dinner_time = st.time_input("夕食時刻", value=dinner_time_default, key=f"dinner_time_{rid}")
    with col2:
        dinner_amount = st.selectbox("夕食の量", amount_options, index=dinner_amount_idx, key=f"dinner_amount_{rid}")
    if st.button("🍽️ 夕食を記録", key=f"save_dinner_{rid}", use_container_width=True):
        if dinner_time and dinner_amount != "---":
            add_care_record(rid, 'dinner', f"{dinner_time.strftime('%H:%M')} {dinner_amount}")
            set_success_message("✅ 夕食を記録しました", "dinner")
            if db_key in st.session_state:
                del st.session_state[db_key]
            st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("**🍼 ミルク（3回分）**")
    show_success_message("milk")
    for i in range(1, 4):
        milk_time_default = care_data.get(f'milk_time_{i}', None)
        milk_amount_default = care_data.get(f'milk_amount_{i}', 100)
        col1, col2 = st.columns(2)
        with col1:
            milk_time = st.time_input(f"時刻{i}", value=milk_time_default, key=f"milk_time_{rid}_{i}")
        with col2:
            milk_amount = st.number_input(f"ミルク量{i}（ml）", min_value=0, max_value=500, value=milk_amount_default, step=10, key=f"milk_amount_{rid}_{i}")
        
        if st.button(f"🍼 ミルク{i}を記録", key=f"save_milk_{rid}_{i}", use_container_width=True):
            if milk_time:
                add_care_record(rid, 'milk', f"{milk_time.strftime('%H:%M')} {milk_amount}ml", index=i)
                set_success_message(f"✅ ミルク{i}を記録しました", "milk")
                if db_key in st.session_state:
                    del st.session_state[db_key]
                st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("**💩 排便（3回分）**")
    show_success_message("stool")
    for i in range(1, 4):
        stool_time_default = care_data.get(f'stool_time_{i}', None)
        stool_type_default = care_data.get(f'stool_type_{i}', "---")
        stool_type_idx = stool_options.index(stool_type_default) if stool_type_default in stool_options else 0
        col1, col2 = st.columns(2)
        with col1:
            stool_time = st.time_input(f"時刻{i}", value=stool_time_default, key=f"stool_time_{rid}_{i}")
        with col2:
            stool_type = st.selectbox(f"便の様子{i}", stool_options, index=stool_type_idx, key=f"stool_type_{rid}_{i}")
        
        if st.button(f"💩 排便{i}を記録", key=f"save_stool_{rid}_{i}", use_container_width=True):
            if stool_time and stool_type != "---":
                add_care_record(rid, 'stool', f"{stool_time.strftime('%H:%M')} {stool_type}", index=i)
                set_success_message(f"✅ 排便{i}を記録しました", "stool")
                if db_key in st.session_state:
                    del st.session_state[db_key]
                st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("**😴 お昼寝（3回分）**")
    show_success_message("nap")
    
    nap_detail_key = f"nap_detail_open_{rid}"
    if nap_detail_key not in st.session_state:
        st.session_state[nap_detail_key] = None
    
    for i in range(1, 4):
        nap_start_default = care_data.get(f'nap_start_{i}', "---")
        nap_end_default = care_data.get(f'nap_end_{i}', "---")
        nap_start_idx = nap_time_options.index(nap_start_default) if nap_start_default in nap_time_options else 0
        nap_end_idx = nap_time_options.index(nap_end_default) if nap_end_default in nap_time_options else 0
        
        st.markdown(f"**お昼寝{i}**")
        col1, col2 = st.columns(2)
        with col1:
            nap_start = st.selectbox(f"開始{i}", nap_time_options, index=nap_start_idx, key=f"nap_start_{rid}_{i}")
        with col2:
            nap_end = st.selectbox(f"終了{i}", nap_time_options, index=nap_end_idx, key=f"nap_end_{rid}_{i}")
        
        col_save, col_detail = st.columns(2)
        with col_save:
            if st.button(f"😴 記録", key=f"save_nap_{rid}_{i}", use_container_width=True):
                if nap_start != "---":
                    if nap_end != "---":
                        add_care_record(rid, f'nap_{i}', f"{nap_start}〜{nap_end}")
                    else:
                        add_care_record(rid, f'nap_{i}', f"{nap_start}〜")
                    set_success_message(f"✅ お昼寝{i}を記録しました", "nap")
                    if db_key in st.session_state:
                        del st.session_state[db_key]
                    st.rerun()
        
        with col_detail:
            if nap_start != "---" and nap_end != "---":
                existing_checks = get_nap_check_logs(rid, i)
                check_count = len(existing_checks)
                detail_label = f"📋 詳細 ({check_count})" if check_count > 0 else "📋 詳細"
                if st.button(detail_label, key=f"nap_detail_{rid}_{i}", use_container_width=True):
                    nap_state_key = f"nap_check_state_{rid}_{i}"
                    if nap_state_key in st.session_state:
                        del st.session_state[nap_state_key]
                    st.session_state[nap_detail_key] = i
                    st.rerun()
            elif nap_start != "---":
                st.button("📋 詳細", key=f"nap_detail_{rid}_{i}_no_end", 
                         use_container_width=True, disabled=True,
                         help="終了時間を設定してください")
            else:
                st.button("📋 詳細", key=f"nap_detail_{rid}_{i}_disabled", 
                         use_container_width=True, disabled=True)
        
        if st.session_state[nap_detail_key] == i:
            st.markdown("---")
            col_back, col_spacer = st.columns([1, 3])
            with col_back:
                if st.button("← 閉じる", key=f"close_nap_detail_{rid}_{i}"):
                    st.session_state[nap_detail_key] = None
                    st.rerun()
            
            show_nap_check_detail(rid, i, nap_start, nap_end if nap_end != "---" else "")
            st.markdown("---")
        
        st.markdown('<hr style="margin:8px 0; border:none; border-top:1px dashed #ddd;">', unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    with st.expander("📝 その他・自由記述"):
        show_success_message("other")
        other_note_default = care_data.get('other_note', "")
        other_note = st.text_area("内容", value=other_note_default, placeholder="例：機嫌よく遊んでいました", height=100, label_visibility="collapsed", key=f"other_note_{rid}")
        if st.button("記録する", key=f"other_{rid}", use_container_width=True):
            if other_note:
                add_care_record(rid, 'other', other_note)
                set_success_message("✅ 記録しました", "other")
                if db_key in st.session_state:
                    del st.session_state[db_key]
                st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### 📋 本日の記録")
    
    if care_records:
        for record in care_records:
            system_time = record.get('record_time', '')[:16].replace('T', ' ') if record.get('record_time') else ''
            record_type_raw = record.get('record_type', '')
            record_type = get_record_type_label(record_type_raw)
            details = record.get('details', '') or ''
            
            if record_type_raw.startswith('temperature'):
                parts = details.split(' ', 1)
                if len(parts) == 2:
                    display = f"検温時間 {parts[0]} {record_type} {parts[1]}"
                else:
                    display = f"{record_type} {details}"
            elif record_type_raw in ['lunch', 'snack', 'dinner']:
                parts = details.split(' ', 1)
                if len(parts) == 2:
                    display = f"{record_type} {parts[0]} {parts[1]}"
                else:
                    display = f"{record_type} {details}"
            elif record_type_raw == 'milk' or record_type_raw.startswith('milk_'):
                parts = details.split(' ', 1)
                if len(parts) == 2:
                    display = f"{record_type} {parts[0]} {parts[1]}"
                else:
                    display = f"{record_type} {details}"
            elif record_type_raw.startswith('stool'):
                parts = details.split(' ', 1)
                if len(parts) == 2:
                    display = f"{record_type} {parts[0]} {parts[1]}"
                else:
                    display = f"{record_type} {details}"
            elif record_type_raw == 'nap' or record_type_raw.startswith('nap_'):
                display = f"{record_type} {details}"
            elif record_type_raw == 'diaper_wet':
                display = f"{record_type} {details}"
            else:
                display = f"{record_type} {details}"
            
            st.markdown(f'- {display} <span style="color:#999;font-size:0.8em;">（記録: {system_time}）</span>', unsafe_allow_html=True)
    else:
        st.info("まだ記録がありません")

def show_pricing_tab(res: dict):
    st.markdown("### 💰 料金計算")
    
    service_category = res.get('service_category', '')
    st.info(f"サービス: **{service_category}**")
    
    calc_mode = st.radio(
        "計算方法",
        ["自動計算", "手動入力"],
        horizontal=True,
        key="calc_mode"
    )
    
    facility = get_current_facility()
    staff_list = get_staff_list(facility)
    staff_names = ["（選択してください）"] + [s['name'] for s in staff_list]
    
    current_staff = res.get('staff_name', '')
    staff_index = staff_names.index(current_staff) if current_staff in staff_names else 0
    
    selected_staff = st.selectbox(
        "担当スタッフ",
        staff_names,
        index=staff_index
    )
    
    is_cancelled = res.get('is_cancelled', 0)
    
    if calc_mode == "自動計算":
        st.markdown("#### ⏰ 利用時間")
        
        res_date_str = res.get('reservation_date', '')
        try:
            if res_date_str:
                use_date = datetime.strptime(res_date_str, "%Y-%m-%d").date()
            else:
                use_date = date.today()
        except:
            use_date = date.today()
        
        col1, col2 = st.columns(2)
        with col1:
            use_date_input = st.date_input("利用日", value=use_date, key="use_date")
        with col2:
            holiday_auto = is_holiday(use_date_input)
            is_holiday_check = st.checkbox(
                "土日祝として計算",
                value=holiday_auto,
                key="is_holiday"
            )
        
        res_start_time = res.get('start_time', '') or '09:00'
        res_end_time = res.get('end_time', '') or '17:00'
        
        col1, col2 = st.columns(2)
        with col1:
            try:
                default_start = datetime.strptime(res_start_time.replace('：', ':'), "%H:%M").time()
            except:
                default_start = datetime.strptime("09:00", "%H:%M").time()
            start_time = st.time_input("開始時刻（予約時間）", value=default_start, key="start_time", help=f"予約: {res_start_time}")
        with col2:
            try:
                default_end = datetime.strptime(res_end_time.replace('：', ':'), "%H:%M").time()
            except:
                default_end = datetime.strptime("17:00", "%H:%M").time()
            end_time = st.time_input("終了時刻（予約時間）", value=default_end, key="end_time", help=f"予約: {res_end_time}")
        
        st.markdown("#### 🍽️ オプション")
        
        has_sibling = st.checkbox(
            "兄弟あり" + ("（△400円/時間）" if service_category == "一時預かり保育" else "（+1,000円/時間）" if service_category == "ベビーシッター（自宅派遣型）" else ""),
            key="has_sibling"
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            snack = st.checkbox(f"おやつ（¥{SNACK_PRICE}）", key="snack")
        with col2:
            lunch_options = [0, 400, 500, 600, 700, 800]
            lunch_price = st.selectbox("昼食", lunch_options, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="lunch")
        with col3:
            dinner_options = [0, 400, 500, 600, 700, 800]
            dinner_price = st.selectbox("夕食", dinner_options, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="dinner")
        
        housework_option = False
        transport_fee = 0
        if service_category == "ベビーシッター（自宅派遣型）":
            col1, col2 = st.columns(2)
            with col1:
                housework_option = st.checkbox(f"家事代行・沐浴（¥{HOUSEWORK_OPTION}）", key="housework")
            with col2:
                transport_fee = st.number_input("交通費（円）", value=res.get('transport_fee', 0) or 0, step=100, min_value=0, key="transport")
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown("#### 🏷️ 割引・追加料金")
        
        col1, col2 = st.columns(2)
        with col1:
            discount_text = st.text_input("割引内容", value=res.get('discount1', '') or '', key="discount_text", placeholder="例: クーポン割引")
        with col2:
            discount_amount = st.number_input("割引金額（円）", value=res.get('discount1_amount', 0) or 0, step=100, min_value=0, key="discount_amt")
        
        col1, col2 = st.columns(2)
        with col1:
            additional_text = st.text_input("追加料金内容", value=res.get('additional_note', '') or '', key="additional_text", placeholder="例: 特別対応")
        with col2:
            additional_amount = st.number_input("追加料金（円）", value=res.get('additional_fee', 0) or 0, step=100, min_value=0, key="additional_amt")
        
        auto_result = calculate_auto_fee(
            service_type=service_category,
            start_time=start_time,
            end_time=end_time,
            use_date=use_date_input,
            is_holiday_manual=is_holiday_check,
            has_sibling=has_sibling,
            snack=snack,
            lunch_price=lunch_price,
            dinner_price=dinner_price,
            housework_option=housework_option,
            transport_fee=transport_fee
        )
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 📊 料金内訳")
        
        st.markdown(f"**{auto_result['day_type']}** / {auto_result['total_hours']}時間（{auto_result['total_minutes']}分）")
        
        for item in auto_result['breakdown']:
            if item['amount'] != 0:
                if item['amount'] < 0:
                    st.markdown(f"- {item['item']}: △¥{abs(item['amount']):,}")
                else:
                    st.markdown(f"- {item['item']}: ¥{item['amount']:,}")
        
        if discount_amount > 0:
            st.markdown(f"- {discount_text or '割引'}: △¥{discount_amount:,}")
        if additional_amount > 0:
            st.markdown(f"- {additional_text or '追加料金'}: ¥{additional_amount:,}")
        
        total_amount = auto_result['total'] - discount_amount + additional_amount
        base_price = auto_result['base_fee']
        facility_fee = auto_result['facility_fee']
        
    else:
        base_price = st.number_input(
            "基本保育料（円）",
            value=res.get('base_price', 0) or 0,
            step=500,
            min_value=0
        )
        
        facility_fee = 0
        if service_category == "一時預かり保育":
            include_facility = st.checkbox(
                f"施設利用料を含める（¥{FACILITY_FEE}）",
                value=bool(res.get('facility_fee'))
            )
            facility_fee = FACILITY_FEE if include_facility else 0
        elif service_category == "ベビーシッター（施設型）":
            facility_fee = FACILITY_FEE_SITTER
            st.info(f"施設利用料: ¥{FACILITY_FEE_SITTER:,}")
        
        transport_fee = 0
        if service_category == "ベビーシッター（自宅派遣型）":
            transport_fee = st.number_input(
                "交通費（円）",
                value=res.get('transport_fee', 0) or 0,
                step=100,
                min_value=0
            )
        
        extension_fee = res.get('extension_fee', 0) or 0
        if extension_fee > 0:
            st.warning(f"⏰ 延長料金: ¥{extension_fee:,}")
        
        with st.expander("🏷️ 割引・追加"):
            discount_options = ["なし", "兄弟割引", "リピート割引", "その他"]
            discount1 = st.selectbox("割引①", discount_options, index=0)
            discount1_amount = 0
            if discount1 != "なし":
                discount1_amount = st.number_input("割引①金額", value=0, step=100, min_value=0, key="d1_amt")
            
            discount2 = st.selectbox("割引②", discount_options, index=0)
            discount2_amount = 0
            if discount2 != "なし":
                discount2_amount = st.number_input("割引②金額", value=0, step=100, min_value=0, key="d2_amt")
            
            additional_fee = st.number_input("追加料金", value=res.get('additional_fee', 0) or 0, step=100, min_value=0)
            additional_note = st.text_input("追加料金メモ", value=res.get('additional_note', '') or '')
        
        pricing = calculate_total_price(
            service_category=service_category,
            base_price=base_price,
            facility_fee=facility_fee,
            option_price=res.get('option_price', 0) or 0,
            extension_fee=extension_fee,
            transport_fee=transport_fee,
            discount1_amount=discount1_amount,
            discount2_amount=discount2_amount,
            additional_fee=additional_fee,
            is_cancelled=bool(is_cancelled),
            include_facility_fee=(service_category == "一時預かり保育" and facility_fee > 0)
        )
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        st.markdown("### 📊 料金内訳")
        st.markdown(f"- 基本保育料: ¥{pricing['base_price']:,}")
        if pricing['facility_fee']:
            st.markdown(f"- 施設利用料: ¥{pricing['facility_fee']:,}")
        if pricing['transport_fee']:
            st.markdown(f"- 交通費: ¥{pricing['transport_fee']:,}")
        if pricing['extension_fee']:
            st.markdown(f"- 延長料金: ¥{pricing['extension_fee']:,}")
        if discount1_amount > 0:
            st.markdown(f"- {discount1 or '割引①'}: △¥{discount1_amount:,}")
        if discount2_amount > 0:
            st.markdown(f"- {discount2 or '割引②'}: △¥{discount2_amount:,}")
        if pricing['additional_fee']:
            st.markdown(f"- 追加料金: ¥{pricing['additional_fee']:,}")
        
        total_amount = pricing['total']
    
    if is_cancelled:
        st.warning("※ キャンセルのため50%のみ請求")
        total_amount = int(base_price * CANCEL_FEE_RATE)
    
    st.markdown(f"## 💴 合計: ¥{total_amount:,}")
    
    cert_date = ''
    cert_type = ''
    if needs_certification(service_category):
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown("### 📜 要件証明")
        
        selected_staff_data = next((s for s in staff_list if s['name'] == selected_staff), None)
        
        cert_date = st.text_input(
            "要件証明日",
            value=selected_staff_data['certification_date'] if selected_staff_data else res.get('certification_date', '') or ''
        )
        
        cert_type_options = [
            "居宅型保育基礎研修修了者",
            "ACSAベビーシッター養成（新任）研修及び現任研修修了者",
            "保育士資格を保有し、補足研修を修了した者",
            "看護師資格を保有し一定の保育経験を有する者",
            "その他"
        ]
        current_cert = selected_staff_data['certification_type'] if selected_staff_data else res.get('certification_type', '')
        cert_index = cert_type_options.index(current_cert) if current_cert in cert_type_options else 0
        cert_type = st.selectbox("要件", cert_type_options, index=cert_index)
    
    if st.button("💾 保存", type="primary", use_container_width=True):
        update_data = {
            'staff_name': selected_staff if selected_staff != "（選択してください）" else '',
            'base_price': base_price,
            'facility_fee': facility_fee,
            'transport_fee': transport_fee if service_category == "ベビーシッター（自宅派遣型）" else 0,
            'certification_date': cert_date,
            'certification_type': cert_type,
            'total_amount': total_amount
        }
        if calc_mode == "自動計算":
            update_data['discount1'] = discount_text
            update_data['discount1_amount'] = discount_amount
            update_data['additional_fee'] = additional_amount
            update_data['additional_note'] = additional_text
        else:
            update_data['discount1'] = discount1 if discount1 != "なし" else ''
            update_data['discount1_amount'] = discount1_amount
            update_data['discount2'] = discount2 if discount2 != "なし" else ''
            update_data['discount2_amount'] = discount2_amount
            update_data['additional_fee'] = additional_fee
            update_data['additional_note'] = additional_note
        update_attendance(res['id'], update_data)
        st.success("✅ 保存しました！")
        st.rerun()

def show_notes_tab(res: dict):
    st.markdown("### 📄 連絡帳")
    
    rid = res['id']
    care_records = get_care_records(rid)
    child_name = res.get('child_name', '')
    
    db_summary = generate_care_summary(care_records, child_name)
    
    temp_key = f"renrakucho_{rid}"
    if temp_key in st.session_state.renrakucho_temp_save:
        initial_value = st.session_state.renrakucho_temp_save[temp_key]
    else:
        initial_value = db_summary
    
    edited_summary = st.text_area(
        "本日のご様子（編集可能）", 
        value=initial_value, 
        height=250, 
        key=f"care_summary_{rid}",
        help="内容を編集後、一時保存ボタンで保存できます"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 一時保存", use_container_width=True, key=f"temp_save_{rid}"):
            st.session_state.renrakucho_temp_save[temp_key] = edited_summary
            st.success("✅ 一時保存しました")
    
    with col2:
        if st.button("🔄 DB内容を再読込", use_container_width=True, key=f"reload_{rid}"):
            if temp_key in st.session_state.renrakucho_temp_save:
                del st.session_state.renrakucho_temp_save[temp_key]
            st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    st.markdown("**📋 コピー用テキスト**")
    st.info("下のテキストを長押しでコピーできます")
    st.code(edited_summary, language=None)

def show_receipt_generation():
    st.markdown('<div class="main-header">🧾 領収書発行</div>', unsafe_allow_html=True)
    
    if st.session_state.selected_reservation_id:
        res = get_reservation_by_id(st.session_state.selected_reservation_id)
        
        if res:
            st.markdown(f"""
            <div class="menu-card">
                <strong>{res.get('child_name', '')}</strong><br>
                <small>{res.get('reservation_date', '')} | ¥{(res.get('total_amount', 0) or 0):,}</small>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🧾 領収書PDFを発行", type="primary", use_container_width=True):
                try:
                    with st.spinner("PDF生成中..."):
                        pdf_path = generate_receipt_pdf(res)
                    
                    st.success("✅ 領収書を生成しました！")
                    
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📥 PDFをダウンロード",
                            data=f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"PDF生成エラー: {str(e)}")
            
            if st.button("← 別の予約を選択", use_container_width=True):
                st.session_state.selected_reservation_id = None
                st.rerun()
    else:
        st.info("👇 領収書を発行する予約を選択")
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    today = date.today()
    
    st.markdown("**📅 期間選択**")
    filter_type = st.radio(
        "表示期間",
        ["今月", "日付指定", "月指定"],
        horizontal=True,
        key="rcpt_filter_type"
    )
    
    facility = get_current_facility()
    
    if filter_type == "今月":
        reservations = get_reservations_by_month(today.year, today.month, facility)
        st.info(f"📅 {today.year}年{today.month}月の予約を表示中")
    elif filter_type == "日付指定":
        selected_date = st.date_input("日付を選択", value=today, key="rcpt_date")
        reservations = get_reservations_by_date(selected_date.isoformat(), facility)
        st.info(f"📅 {selected_date.strftime('%Y年%m月%d日')}の予約を表示中")
    else:
        col1, col2 = st.columns(2)
        with col1:
            sel_year = st.selectbox("年", range(today.year - 1, today.year + 2), index=1, key="rcpt_year")
        with col2:
            sel_month = st.selectbox("月", range(1, 13), index=today.month - 1, key="rcpt_month")
        reservations = get_reservations_by_month(sel_year, sel_month, facility)
        st.info(f"📅 {sel_year}年{sel_month}月の予約を表示中")
    
    if not reservations:
        st.info("📭 該当する予約がありません")
        return
    
    st.markdown(f"**{len(reservations)}件**")
    
    for res in reservations[:50]:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"""
            <div style="padding:0.5rem 0;">
                <strong>{res.get('child_name', '')}</strong><br>
                <small style="color:#666;">{res.get('reservation_date', '')} | ¥{(res.get('total_amount', 0) or 0):,}</small>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            if st.button("選択", key=f"rcpt_{res['id']}", use_container_width=True):
                st.session_state.selected_reservation_id = res['id']
                st.rerun()
        st.divider()


def show_fee_calculator():
    st.markdown('<div class="main-header">🧮 料金計算シミュレーター</div>', unsafe_allow_html=True)
    st.markdown('<p style="color:#8B7355;">サービス種別ごとの料金を自動計算</p>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🏠 一時預かり保育", "🏢 ベビーシッター（施設型）", "🏡 自宅ベビーシッター"])
    
    time_options = get_time_options()
    time_labels = [f"{t.hour}:{t.minute:02d}" for t in time_options]
    lunch_opts = [0, 400, 500, 600, 700, 800]
    
    with tab1:
        st.markdown("### 一時預かり保育")
        st.markdown("""
        <div style="background:#f8f9fa;padding:0.8rem;border-radius:8px;margin-bottom:1rem;font-size:0.9rem;">
        <b>料金体系:</b><br>
        ・通常時間 (9:00-17:00): 平日 ¥2,000/h、土日祝 ¥3,200/h<br>
        ・時間外 (7:00-9:00, 17:00-22:00): 平日 ¥2,800/h、土日祝 ¥4,000/h<br>
        ・施設利用料: ¥550/回<br>
        ・兄弟割引: △¥400/h
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            use_date_1 = st.date_input("利用日", value=date.today(), key="temp_date")
        with col2:
            is_hol_1 = is_holiday_or_weekend(use_date_1)
            st.markdown(f"**曜日区分:** {'🔴 土日祝' if is_hol_1 else '🔵 平日'}")
        
        col1, col2 = st.columns(2)
        with col1:
            start_idx_1 = st.selectbox("開始時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=36, key="temp_start")
        with col2:
            end_idx_1 = st.selectbox("終了時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=68, key="temp_end")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            include_facility_1 = st.checkbox("施設利用料を含める", value=True, key="temp_facility")
        with col2:
            has_sibling_1 = st.checkbox(f"兄弟あり（△¥{SIBLING_DISCOUNT_PER_HOUR}/h）", key="temp_sibling")
        with col3:
            snack_1 = st.checkbox(f"おやつ（¥{CALC_SNACK_PRICE}）", key="temp_snack")
        
        col1, col2 = st.columns(2)
        with col1:
            lunch_1 = st.selectbox("昼食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="temp_lunch")
        with col2:
            dinner_1 = st.selectbox("夕食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="temp_dinner")
        
        if st.button("💰 計算する", type="primary", use_container_width=True, key="calc_temp"):
            result = calculate_temporary_care(
                use_date=use_date_1,
                start_time=time_options[start_idx_1],
                end_time=time_options[end_idx_1],
                has_sibling=has_sibling_1,
                include_facility_fee=include_facility_1,
                snack=snack_1,
                lunch_price=lunch_1,
                dinner_price=dinner_1
            )
            
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            st.markdown("### 📊 計算結果")
            
            for warning in result.warnings:
                st.warning(warning)
            
            st.markdown(f"**{result.day_type}** / 利用時間: {result.total_minutes}分（{result.total_minutes/60:.2f}時間）")
            
            st.markdown("#### 時間帯別内訳")
            for item in result.breakdown:
                st.markdown(f"- {item.description}: {item.hours}h × ¥{item.rate:,} = **¥{item.amount:,}**")
            
            st.markdown(f"**基本料金小計:** ¥{result.base_fee:,}")
            
            if result.facility_fee > 0:
                st.markdown(f"+ 施設利用料: ¥{result.facility_fee:,}")
            if result.sibling_adjustment != 0:
                st.markdown(f"- 兄弟割引: △¥{abs(result.sibling_adjustment):,}")
            if result.meal_fee > 0:
                st.markdown(f"+ 食事代: ¥{result.meal_fee:,}")
            
            st.markdown(f"## 💴 合計: ¥{result.total:,}")
    
    with tab2:
        st.markdown("### ベビーシッター（施設型）")
        st.markdown("""
        <div style="background:#f8f9fa;padding:0.8rem;border-radius:8px;margin-bottom:1rem;font-size:0.9rem;">
        <b>料金体系:</b><br>
        ・通常時間 (9:00-17:00): 平日 ¥3,200/h、土日祝 ¥4,000/h<br>
        ・時間外 (7:00-9:00, 17:00-22:00): 平日 ¥4,000/h、土日祝 ¥4,500/h<br>
        ・施設利用料: ¥2,200/回<br>
        ・<b style="color:#dc3545;">最低利用: 2時間以上</b>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            use_date_2 = st.date_input("利用日", value=date.today(), key="fac_date")
        with col2:
            is_hol_2 = is_holiday_or_weekend(use_date_2)
            st.markdown(f"**曜日区分:** {'🔴 土日祝' if is_hol_2 else '🔵 平日'}")
        
        col1, col2 = st.columns(2)
        with col1:
            start_idx_2 = st.selectbox("開始時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=36, key="fac_start")
        with col2:
            end_idx_2 = st.selectbox("終了時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=68, key="fac_end")
        
        col1, col2 = st.columns(2)
        with col1:
            include_facility_2 = st.checkbox("施設利用料を含める", value=True, key="fac_facility")
        with col2:
            snack_2 = st.checkbox(f"おやつ（¥{CALC_SNACK_PRICE}）", key="fac_snack")
        
        col1, col2 = st.columns(2)
        with col1:
            lunch_2 = st.selectbox("昼食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="fac_lunch")
        with col2:
            dinner_2 = st.selectbox("夕食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="fac_dinner")
        
        if st.button("💰 計算する", type="primary", use_container_width=True, key="calc_fac"):
            result = calculate_facility_sitter(
                use_date=use_date_2,
                start_time=time_options[start_idx_2],
                end_time=time_options[end_idx_2],
                include_facility_fee=include_facility_2,
                snack=snack_2,
                lunch_price=lunch_2,
                dinner_price=dinner_2
            )
            
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            st.markdown("### 📊 計算結果")
            
            for warning in result.warnings:
                st.warning(warning)
            
            st.markdown(f"**{result.day_type}** / 利用時間: {result.total_minutes}分（{result.total_minutes/60:.2f}時間）")
            
            st.markdown("#### 時間帯別内訳")
            for item in result.breakdown:
                st.markdown(f"- {item.description}: {item.hours}h × ¥{item.rate:,} = **¥{item.amount:,}**")
            
            st.markdown(f"**基本料金小計:** ¥{result.base_fee:,}")
            
            if result.facility_fee > 0:
                st.markdown(f"+ 施設利用料: ¥{result.facility_fee:,}")
            if result.meal_fee > 0:
                st.markdown(f"+ 食事代: ¥{result.meal_fee:,}")
            
            st.markdown(f"## 💴 合計: ¥{result.total:,}")
    
    with tab3:
        st.markdown("### 自宅ベビーシッター")
        st.markdown("""
        <div style="background:#f8f9fa;padding:0.8rem;border-radius:8px;margin-bottom:1rem;font-size:0.9rem;">
        <b>料金体系:</b><br>
        ・通常時間 (9:00-17:00): 平日 ¥3,500/h、土日祝 ¥3,900/h<br>
        ・時間外 (7:00-9:00, 17:00-20:00): 平日 ¥3,800/h、土日祝 ¥4,200/h<br>
        ・早朝夜間 (~7:00, 20:00~): 平日 ¥4,000/h、土日祝 ¥4,400/h<br>
        ・兄弟加算: +¥1,000/h<br>
        ・<b style="color:#dc3545;">最低利用: 3時間以上</b>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            use_date_3 = st.date_input("利用日", value=date.today(), key="home_date")
        with col2:
            is_hol_3 = is_holiday_or_weekend(use_date_3)
            st.markdown(f"**曜日区分:** {'🔴 土日祝' if is_hol_3 else '🔵 平日'}")
        
        col1, col2 = st.columns(2)
        with col1:
            start_idx_3 = st.selectbox("開始時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=36, key="home_start")
        with col2:
            end_idx_3 = st.selectbox("終了時刻", range(len(time_options)), 
                format_func=lambda i: time_labels[i], index=68, key="home_end")
        
        col1, col2 = st.columns(2)
        with col1:
            has_sibling_3 = st.checkbox(f"兄弟あり（+¥{SIBLING_ADDITION_PER_HOUR}/h）", key="home_sibling")
        with col2:
            housework_3 = st.checkbox(f"家事代行・沐浴（¥{CALC_HOUSEWORK_OPTION}）", key="home_housework")
        
        transport_3 = st.number_input("交通費（円）", value=0, step=100, min_value=0, key="home_transport")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            snack_3 = st.checkbox(f"おやつ（¥{CALC_SNACK_PRICE}）", key="home_snack")
        with col2:
            lunch_3 = st.selectbox("昼食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="home_lunch")
        with col3:
            dinner_3 = st.selectbox("夕食", lunch_opts, format_func=lambda x: f"¥{x}" if x > 0 else "なし", key="home_dinner")
        
        if st.button("💰 計算する", type="primary", use_container_width=True, key="calc_home"):
            result = calculate_home_sitter(
                use_date=use_date_3,
                start_time=time_options[start_idx_3],
                end_time=time_options[end_idx_3],
                has_sibling=has_sibling_3,
                housework_option=housework_3,
                transport_fee=transport_3,
                snack=snack_3,
                lunch_price=lunch_3,
                dinner_price=dinner_3
            )
            
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            st.markdown("### 📊 計算結果")
            
            for warning in result.warnings:
                st.warning(warning)
            
            st.markdown(f"**{result.day_type}** / 利用時間: {result.total_minutes}分（{result.total_minutes/60:.2f}時間）")
            
            st.markdown("#### 時間帯別内訳")
            for item in result.breakdown:
                st.markdown(f"- {item.description}: {item.hours}h × ¥{item.rate:,} = **¥{item.amount:,}**")
            
            st.markdown(f"**基本料金小計:** ¥{result.base_fee:,}")
            
            if result.sibling_adjustment > 0:
                st.markdown(f"+ 兄弟加算: ¥{result.sibling_adjustment:,}")
            if result.option_fee > 0:
                st.markdown(f"+ 家事代行・沐浴: ¥{result.option_fee:,}")
            if result.transport_fee > 0:
                st.markdown(f"+ 交通費: ¥{result.transport_fee:,}")
            if result.meal_fee > 0:
                st.markdown(f"+ 食事代: ¥{result.meal_fee:,}")
            
            st.markdown(f"## 💴 合計: ¥{result.total:,}")


def show_admin_dashboard():
    if not is_admin():
        st.error("このページにアクセスする権限がありません。")
        return
    
    st.markdown('<div class="main-header">🔧 管理者ダッシュボード</div>', unsafe_allow_html=True)
    
    if st.button("← ホームに戻る", use_container_width=False):
        navigate_to("home")
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 👤 スタッフアカウント管理")
    
    show_success_message("user_add")
    show_success_message("user_update")
    show_success_message("user_delete")
    show_success_message("password_reset")
    
    current_user = get_current_user()
    
    if 'show_add_user_form' not in st.session_state:
        st.session_state.show_add_user_form = False
    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None
    if 'resetting_password_user_id' not in st.session_state:
        st.session_state.resetting_password_user_id = None
    if 'confirm_delete_user_id' not in st.session_state:
        st.session_state.confirm_delete_user_id = None
    
    col_add_user, col_spacer_user = st.columns([1, 3])
    with col_add_user:
        if st.button("➕ 新規スタッフ登録", type="primary", use_container_width=True, key="add_user_btn"):
            st.session_state.show_add_user_form = True
            st.session_state.editing_user_id = None
            st.session_state.resetting_password_user_id = None
            st.session_state.confirm_delete_user_id = None
    
    if st.session_state.show_add_user_form:
        st.markdown("#### 新規ユーザー登録")
        with st.form("add_user_form"):
            new_username = st.text_input("ユーザーID *", placeholder="例: staff01")
            new_display_name = st.text_input("表示名", placeholder="例: 山田太郎")
            new_user_password = st.text_input("初期パスワード *", type="password", placeholder="4文字以上")
            new_role = st.selectbox("権限", ["一般スタッフ", "管理者"])
            new_role_value = "admin" if new_role == "管理者" else "user"
            
            col_u_submit, col_u_cancel = st.columns(2)
            with col_u_submit:
                u_submitted = st.form_submit_button("✅ 登録", type="primary", use_container_width=True)
            with col_u_cancel:
                u_cancelled = st.form_submit_button("❌ キャンセル", use_container_width=True)
            
            if u_submitted:
                if not new_username.strip():
                    st.error("ユーザーIDを入力してください")
                elif len(new_user_password) < 4:
                    st.error("パスワードは4文字以上で設定してください")
                else:
                    if create_user(new_username.strip(), new_user_password, new_role_value, new_display_name.strip() or new_username.strip()):
                        st.session_state.show_add_user_form = False
                        set_success_message(f"✅ ユーザー「{new_username}」を登録しました", "user_add")
                        st.rerun()
                    else:
                        st.error("ユーザーIDが既に使用されています")
            
            if u_cancelled:
                st.session_state.show_add_user_form = False
                st.rerun()
        st.markdown("---")
    
    users = get_all_users()
    if users:
        st.markdown(f"**登録済みユーザー: {len(users)}名**")
        
        st.markdown("""
        <style>
        .user-table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }
        .user-table th {
            background-color: #f0f2f6;
            padding: 10px;
            text-align: left;
            border-bottom: 2px solid #ddd;
            font-weight: 600;
        }
        .user-table td {
            padding: 10px;
            border-bottom: 1px solid #eee;
        }
        .user-table tr:hover {
            background-color: #f9f9f9;
        }
        .role-badge-admin {
            background: #fff3e0;
            color: #e65100;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        .role-badge-user {
            background: #e3f2fd;
            color: #1565c0;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        </style>
        """, unsafe_allow_html=True)
        
        table_html = """
        <table class="user-table">
            <thead>
                <tr>
                    <th>ユーザーID</th>
                    <th>表示名</th>
                    <th>権限</th>
                    <th>作成日</th>
                </tr>
            </thead>
            <tbody>
        """
        for user in users:
            role_class = "role-badge-admin" if user['role'] == 'admin' else "role-badge-user"
            role_text = "管理者" if user['role'] == 'admin' else "スタッフ"
            created_at = user.get('created_at', '-')
            if created_at and created_at != '-':
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_at = dt.strftime('%Y/%m/%d')
                except:
                    created_at = created_at[:10] if len(created_at) >= 10 else created_at
            table_html += f"""
                <tr>
                    <td><strong>{user['username']}</strong></td>
                    <td>{user.get('display_name', '') or '-'}</td>
                    <td><span class="{role_class}">{role_text}</span></td>
                    <td>{created_at}</td>
                </tr>
            """
        table_html += "</tbody></table>"
        st.markdown(table_html, unsafe_allow_html=True)
        
        st.markdown("---")
        
        for user in users:
            user_id = user['id']
            is_editing_user = st.session_state.editing_user_id == user_id
            is_resetting_password = st.session_state.resetting_password_user_id == user_id
            is_confirming_delete = st.session_state.confirm_delete_user_id == user_id
            is_current_user = current_user and current_user['id'] == user_id
            is_admin_user = user['username'] == 'admin'
            can_delete = not is_current_user and not is_admin_user
            
            with st.container():
                if is_confirming_delete and can_delete:
                    st.warning(f"⚠️ 「{user['username']}」を削除してもよろしいですか？この操作は取り消せません。")
                    col_confirm, col_cancel_del = st.columns(2)
                    with col_confirm:
                        if st.button("✅ 削除する", key=f"confirm_del_{user_id}", type="primary", use_container_width=True):
                            delete_user(user_id)
                            st.session_state.confirm_delete_user_id = None
                            set_success_message(f"🗑️ ユーザー「{user['username']}」を削除しました", "user_delete")
                            st.rerun()
                    with col_cancel_del:
                        if st.button("❌ キャンセル", key=f"cancel_del_{user_id}", use_container_width=True):
                            st.session_state.confirm_delete_user_id = None
                            st.rerun()
                elif is_resetting_password:
                    st.markdown(f"#### 🔑 パスワードリセット: {user['username']}")
                    with st.form(f"reset_password_form_{user_id}"):
                        reset_password = st.text_input("新しいパスワード *", type="password", placeholder="4文字以上")
                        reset_confirm = st.text_input("パスワード確認 *", type="password", placeholder="もう一度入力")
                        
                        col_reset, col_cancel_reset = st.columns(2)
                        with col_reset:
                            reset_btn = st.form_submit_button("🔑 リセット", type="primary", use_container_width=True)
                        with col_cancel_reset:
                            cancel_reset_btn = st.form_submit_button("❌ キャンセル", use_container_width=True)
                        
                        if reset_btn:
                            if len(reset_password) < 4:
                                st.error("パスワードは4文字以上で設定してください")
                            elif reset_password != reset_confirm:
                                st.error("パスワードが一致しません")
                            else:
                                if update_user_password(user_id, reset_password):
                                    st.session_state.resetting_password_user_id = None
                                    set_success_message(f"✅ ユーザー「{user['username']}」のパスワードをリセットしました", "password_reset")
                                    st.rerun()
                                else:
                                    st.error("パスワードのリセットに失敗しました")
                        
                        if cancel_reset_btn:
                            st.session_state.resetting_password_user_id = None
                            st.rerun()
                elif is_editing_user:
                    st.markdown(f"#### ✏️ 編集中: {user['username']}")
                    with st.form(f"edit_user_form_{user_id}"):
                        edit_display_name = st.text_input("表示名", value=user.get('display_name', '') or '')
                        edit_role = st.selectbox("権限", ["一般スタッフ", "管理者"], 
                                                 index=1 if user['role'] == 'admin' else 0)
                        edit_role_value = "admin" if edit_role == "管理者" else "user"
                        
                        col1_u, col2_u = st.columns(2)
                        with col1_u:
                            save_u_btn = st.form_submit_button("💾 保存", type="primary", use_container_width=True)
                        with col2_u:
                            cancel_u_btn = st.form_submit_button("❌ キャンセル", use_container_width=True)
                        
                        if save_u_btn:
                            update_user(user_id, edit_display_name.strip(), edit_role_value)
                            st.session_state.editing_user_id = None
                            set_success_message(f"✅ ユーザー「{user['username']}」を更新しました", "user_update")
                            st.rerun()
                        
                        if cancel_u_btn:
                            st.session_state.editing_user_id = None
                            st.rerun()
                else:
                    role_display = "👑 管理者" if user['role'] == 'admin' else "👤 スタッフ"
                    user_label = f"**{user['username']}** {role_display}"
                    if is_current_user:
                        user_label += " (自分)"
                    
                    with st.expander(user_label, expanded=False):
                        col_edit, col_reset_pw, col_delete = st.columns(3)
                        with col_edit:
                            if st.button("✏️ 編集", key=f"edit_user_{user_id}", use_container_width=True):
                                st.session_state.editing_user_id = user_id
                                st.session_state.show_add_user_form = False
                                st.session_state.resetting_password_user_id = None
                                st.session_state.confirm_delete_user_id = None
                                st.rerun()
                        with col_reset_pw:
                            if st.button("🔑 パスワード", key=f"reset_pw_{user_id}", use_container_width=True):
                                st.session_state.resetting_password_user_id = user_id
                                st.session_state.editing_user_id = None
                                st.session_state.show_add_user_form = False
                                st.session_state.confirm_delete_user_id = None
                                st.rerun()
                        with col_delete:
                            if can_delete:
                                if st.button("🗑️ 削除", key=f"delete_user_{user_id}", use_container_width=True):
                                    st.session_state.confirm_delete_user_id = user_id
                                    st.session_state.editing_user_id = None
                                    st.session_state.show_add_user_form = False
                                    st.session_state.resetting_password_user_id = None
                                    st.rerun()
                            else:
                                reason = "自分自身" if is_current_user else "システム管理者"
                                st.button(f"🔒 削除不可", key=f"no_del_{user_id}", disabled=True, use_container_width=True, help=f"{reason}は削除できません")
    else:
        st.info("ユーザーが登録されていません。")
    
    st.markdown("---")
    st.markdown("### 💰 料金マスター管理")
    
    show_success_message("fee_update")
    
    fee_categories = [
        ("temporary_care", "一時預かり保育"),
        ("facility_sitter", "ベビーシッター（施設型）"),
        ("home_sitter", "自宅ベビーシッター"),
        ("option", "オプション料金"),
    ]
    
    fee_tabs = st.tabs([cat[1] for cat in fee_categories])
    
    for idx, (category_key, category_name) in enumerate(fee_categories):
        with fee_tabs[idx]:
            fee_settings = get_fee_settings_by_category(category_key)
            
            if fee_settings:
                with st.form(f"fee_form_{category_key}"):
                    updated_values = {}
                    
                    for setting in fee_settings:
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.markdown(f"**{setting['description']}**")
                        with col2:
                            new_value = st.number_input(
                                f"金額 ({setting['setting_key']})",
                                min_value=0,
                                value=setting['setting_value'],
                                step=50,
                                key=f"fee_{setting['setting_key']}",
                                label_visibility="collapsed"
                            )
                            updated_values[setting['setting_key']] = new_value
                    
                    if st.form_submit_button(f"💾 {category_name}の料金を保存", type="primary", use_container_width=True):
                        success_count = 0
                        for key, value in updated_values.items():
                            if update_fee_setting(key, value):
                                success_count += 1
                        if success_count == len(updated_values):
                            set_success_message(f"✅ {category_name}の料金設定を更新しました", "fee_update")
                            st.rerun()
                        else:
                            st.error("一部の料金設定の更新に失敗しました")
            else:
                st.info(f"{category_name}の料金設定がありません。")
    
    st.markdown("---")
    st.markdown("### 📋 セッションログ（デバッグ用）")
    st.caption("iPad等での意図しないログアウトの原因特定用。直近100件のセッション関連イベントを表示。")
    
    if st.button("🔄 ログを更新", key="refresh_session_logs"):
        st.rerun()
    
    session_logs = get_session_logs(100)
    if session_logs:
        log_data = []
        for log in session_logs:
            event_style = {
                "LOGIN_SUCCESS": "🟢",
                "LOGOUT": "🔴",
                "RESTORE_SUCCESS": "🟢",
                "RESTORE_ATTEMPT": "🟡",
                "RESTORE_FAILED": "🔴",
                "VALIDATE_SUCCESS": "🟢",
                "VALIDATE_EXPIRED": "🟠",
                "VALIDATE_NOT_FOUND": "🔴",
                "VALIDATE_ERROR": "🔴",
                "VALIDATE_NO_TOKEN": "⚪",
                "NO_COOKIE": "⚪",
                "COOKIE_READ_ERROR": "🔴",
                "SESSION_STATE_MISMATCH": "🟠",
                "LOGIN_COOKIE_ERROR": "🔴",
            }.get(log['event_type'], "⚪")
            
            log_data.append({
                "日時": log['created_at'][:19] if log['created_at'] else "",
                "イベント": f"{event_style} {log['event_type']}",
                "ユーザー": log['username'] or "-",
                "トークン": log['session_token_prefix'] or "-",
                "詳細": log['details'] or "-",
            })
        
        st.dataframe(log_data, use_container_width=True, height=400)
        
        with st.expander("イベントタイプ凡例"):
            st.markdown("""
            - 🟢 **LOGIN_SUCCESS** / **RESTORE_SUCCESS** / **VALIDATE_SUCCESS**: 正常なログイン・復元・検証
            - 🟡 **RESTORE_ATTEMPT**: Cookie復元試行中
            - 🟠 **VALIDATE_EXPIRED** / **SESSION_STATE_MISMATCH**: 期限切れまたはiOS特有の問題
            - 🔴 **LOGOUT**: 明示的ログアウト
            - 🔴 **RESTORE_FAILED** / **VALIDATE_NOT_FOUND**: セッションがDBに存在しない
            - 🔴 **VALIDATE_ERROR** / **COOKIE_READ_ERROR** / **LOGIN_COOKIE_ERROR**: エラー発生
            - ⚪ **NO_COOKIE** / **VALIDATE_NO_TOKEN**: 初回アクセスまたはCookie未設定
            """)
    else:
        st.info("セッションログがありません。")


def show_settings():
    st.markdown('<div class="main-header">⚙️ 設定</div>', unsafe_allow_html=True)
    
    if st.button("← ホームに戻る", use_container_width=False):
        navigate_to("home")
        st.rerun()
    
    current_user = get_current_user()
    
    st.markdown("---")
    st.markdown("### 🔑 パスワード変更")
    
    show_success_message("password_change")
    
    with st.form("password_change_form"):
        new_password = st.text_input("新しいパスワード", type="password", placeholder="新しいパスワードを入力")
        confirm_password = st.text_input("パスワード確認", type="password", placeholder="もう一度入力")
        pw_submitted = st.form_submit_button("パスワードを変更", use_container_width=True)
        
        if pw_submitted:
            if not new_password:
                st.error("新しいパスワードを入力してください")
            elif len(new_password) < 4:
                st.error("パスワードは4文字以上で設定してください")
            elif new_password != confirm_password:
                st.error("パスワードが一致しません")
            else:
                if update_user_password(current_user['id'], new_password):
                    set_success_message("✅ パスワードを変更しました", "password_change")
                    st.rerun()
                else:
                    st.error("パスワードの変更に失敗しました")
    
    st.markdown("---")
    st.markdown("### 👥 スタッフ管理")
    
    if 'editing_staff_id' not in st.session_state:
        st.session_state.editing_staff_id = None
    if 'show_add_form' not in st.session_state:
        st.session_state.show_add_form = False
    
    staff_list = get_staff_list()
    
    col_add, col_spacer = st.columns([1, 3])
    with col_add:
        if st.button("➕ 新規スタッフ追加", type="primary", use_container_width=True):
            st.session_state.show_add_form = True
            st.session_state.editing_staff_id = None
    
    facility_options_staff = ["both", FACILITY_HOUSE, FACILITY_BABY]
    facility_labels_staff = ["両方の施設", "🏠 こぐまハウスのみ", "👶 こぐまbabyのみ"]
    
    if st.session_state.show_add_form:
        st.markdown("#### 新規スタッフ登録")
        with st.form("add_staff_form"):
            new_name = st.text_input("氏名 *", placeholder="例: 山田 花子")
            new_kana = st.text_input("氏名（かな）", placeholder="例: ヤマダ ハナコ")
            new_cert_date = st.text_input("資格取得日", placeholder="例: 令和6年4月1日")
            new_cert_type = st.text_input("資格種別", placeholder="例: 保育士資格を保有し、補足研修を修了した者")
            new_facility = st.selectbox("所属施設", facility_labels_staff, index=0)
            new_facility_id = facility_options_staff[facility_labels_staff.index(new_facility)]
            
            col_submit, col_cancel = st.columns(2)
            with col_submit:
                submitted = st.form_submit_button("✅ 登録", type="primary", use_container_width=True)
            with col_cancel:
                cancelled = st.form_submit_button("❌ キャンセル", use_container_width=True)
            
            if submitted:
                if new_name.strip():
                    add_staff(new_name.strip(), new_kana.strip(), new_cert_date.strip(), new_cert_type.strip(), new_facility_id)
                    st.session_state.show_add_form = False
                    set_success_message(f"✅ スタッフ「{new_name}」を登録しました", "staff_add")
                    st.rerun()
                else:
                    st.error("氏名を入力してください")
            
            if cancelled:
                st.session_state.show_add_form = False
                st.rerun()
        st.markdown("---")
    
    show_success_message("staff_add")
    show_success_message("staff_update")
    show_success_message("staff_delete")
    
    if staff_list:
        st.markdown(f"**登録済みスタッフ: {len(staff_list)}名**")
        
        for staff in staff_list:
            staff_id = staff['id']
            is_editing = st.session_state.editing_staff_id == staff_id
            
            with st.container():
                if is_editing:
                    st.markdown(f"#### ✏️ 編集中: {staff['name']}")
                    with st.form(f"edit_staff_form_{staff_id}"):
                        edit_name = st.text_input("氏名 *", value=staff['name'])
                        edit_kana = st.text_input("氏名（かな）", value=staff.get('name_kana', '') or '')
                        edit_cert_date = st.text_input("資格取得日", value=staff.get('certification_date', '') or '')
                        edit_cert_type = st.text_input("資格種別", value=staff.get('certification_type', '') or '')
                        current_facility_id = staff.get('facility_id', 'both') or 'both'
                        current_facility_idx = facility_options_staff.index(current_facility_id) if current_facility_id in facility_options_staff else 0
                        edit_facility = st.selectbox("所属施設", facility_labels_staff, index=current_facility_idx)
                        edit_facility_id = facility_options_staff[facility_labels_staff.index(edit_facility)]
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            save_btn = st.form_submit_button("💾 保存", type="primary", use_container_width=True)
                        with col2:
                            cancel_btn = st.form_submit_button("❌ キャンセル", use_container_width=True)
                        with col3:
                            delete_btn = st.form_submit_button("🗑️ 削除", use_container_width=True)
                        
                        if save_btn:
                            if edit_name.strip():
                                update_staff(staff_id, edit_name.strip(), edit_kana.strip(), 
                                           edit_cert_date.strip(), edit_cert_type.strip(), edit_facility_id)
                                st.session_state.editing_staff_id = None
                                set_success_message(f"✅ スタッフ「{edit_name}」を更新しました", "staff_update")
                                st.rerun()
                            else:
                                st.error("氏名を入力してください")
                        
                        if cancel_btn:
                            st.session_state.editing_staff_id = None
                            st.rerun()
                        
                        if delete_btn:
                            delete_staff(staff_id)
                            st.session_state.editing_staff_id = None
                            set_success_message(f"🗑️ スタッフ「{staff['name']}」を削除しました", "staff_delete")
                            st.rerun()
                else:
                    staff_facility = staff.get('facility_id', 'both') or 'both'
                    facility_display = "両方" if staff_facility == 'both' else ("こぐまハウス" if staff_facility == FACILITY_HOUSE else "こぐまbaby")
                    st.markdown(f"""
                    <div style="background:#f8f9fa;padding:12px;border-radius:8px;margin-bottom:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
                            <div>
                                <strong style="font-size:1.1rem;">{staff['name']}</strong>
                                <span style="color:#888;margin-left:8px;">({staff.get('name_kana', '') or '-'})</span>
                                <span style="background:#e3f2fd;color:#1976d2;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px;">{facility_display}</span>
                            </div>
                        </div>
                        <div style="font-size:0.85rem;color:#666;margin-top:4px;">
                            資格取得日: {staff.get('certification_date', '-') or '-'}<br>
                            資格種別: {staff.get('certification_type', '-') or '-'}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("✏️ 編集", key=f"edit_staff_{staff_id}", use_container_width=False):
                        st.session_state.editing_staff_id = staff_id
                        st.session_state.show_add_form = False
                        st.rerun()
    else:
        st.info("スタッフが登録されていません。「新規スタッフ追加」ボタンから登録してください。")


if __name__ == "__main__":
    main()
