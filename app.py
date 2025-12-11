import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os

from database import (
    init_database, import_csv_data, get_reservations_by_date,
    get_all_reservations, update_attendance, add_care_record,
    get_care_records, get_staff_list, get_reservation_by_id
)
from pricing import (
    calculate_total_price, calculate_extension_fee, needs_certification,
    FACILITY_FEE, CANCEL_FEE_RATE
)
from pdf_generator import generate_receipt_pdf
from care_notes import generate_care_summary, RECORD_TYPES, get_record_type_label

st.set_page_config(
    page_title="こぐまハウス",
    page_icon="🐻",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)

init_database()

if 'selected_reservation_id' not in st.session_state:
    st.session_state.selected_reservation_id = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "home"

def navigate_to(page_name: str):
    st.session_state.current_page = page_name

def main():
    st.sidebar.markdown("## 🐻 こぐまハウス")
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
    
    page = st.session_state.current_page
    
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
    else:
        show_home()

def show_home():
    st.markdown('<div class="main-header">🐻 こぐまハウス</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#8B7355;margin-bottom:1rem;">業務支援システム</p>', unsafe_allow_html=True)
    
    today = date.today().isoformat()
    today_reservations = get_reservations_by_date(today)
    
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
                        update_attendance(res['id'], {'check_in_time': datetime.now().isoformat()})
                        st.rerun()
                elif not has_checkout:
                    if st.button("🔴 降園", key=f"quick_out_{res['id']}", use_container_width=True):
                        now = datetime.now()
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
            
            if st.button("📥 データベースに取り込む", type="primary", use_container_width=True):
                with st.spinner("取込中..."):
                    count = import_csv_data(df)
                    st.success(f"✅ {count}件を取り込みました！")
                    st.balloons()
        
        except Exception as e:
            st.error(f"エラー: {str(e)}")

def show_today_children():
    st.markdown('<div class="main-header">👶 本日の児童</div>', unsafe_allow_html=True)
    
    selected_date = st.date_input(
        "日付",
        value=date.today(),
        label_visibility="collapsed"
    )
    
    reservations = get_reservations_by_date(selected_date.isoformat())
    
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
    st.markdown('<div class="main-header">📋 予約一覧</div>', unsafe_allow_html=True)
    
    reservations = get_all_reservations()
    
    if not reservations:
        st.info("📭 予約データがありません")
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
    
    for res in filtered[:30]:
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
        
        today_reservations = get_reservations_by_date(date.today().isoformat())
        
        if today_reservations:
            st.markdown("### 📅 本日の予約")
            for res in today_reservations:
                if not res.get('is_cancelled'):
                    show_child_card(res, show_quick_actions=True)
        else:
            st.write("本日の予約はありません")

def show_detail_input(reservation_id: int):
    res = get_reservation_by_id(reservation_id)
    
    if not res:
        st.error("予約が見つかりません")
        st.session_state.selected_reservation_id = None
        return
    
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
                update_attendance(res['id'], {'check_in_time': datetime.now().isoformat()})
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
                now = datetime.now()
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
    
    st.markdown("### ❌ キャンセル")
    
    if res.get('is_cancelled'):
        st.warning(f"キャンセル済み（{res.get('cancel_type', '')}）")
    else:
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
    
    care_records = get_care_records(res['id'])
    
    st.markdown("**🍽️ 食事**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🍚 食事開始", key="meal_start", use_container_width=True):
            add_care_record(res['id'], 'meal_start')
            st.rerun()
    with col2:
        if st.button("✅ 食事終了", key="meal_end", use_container_width=True):
            add_care_record(res['id'], 'meal_end')
            st.rerun()
    with col3:
        if st.button("🍪 おやつ", key="snack", use_container_width=True):
            add_care_record(res['id'], 'snack')
            st.rerun()
    
    st.markdown("**😴 睡眠**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("😴 お昼寝開始", key="sleep_start", use_container_width=True):
            add_care_record(res['id'], 'sleep_start')
            st.rerun()
    with col2:
        if st.button("☀️ お昼寝終了", key="sleep_end", use_container_width=True):
            add_care_record(res['id'], 'sleep_end')
            st.rerun()
    with col3:
        if st.button("🍼 ミルク", key="milk", use_container_width=True):
            add_care_record(res['id'], 'milk')
            st.rerun()
    
    st.markdown("**🚽 排泄**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💧 おしっこ", key="diaper_wet", use_container_width=True):
            add_care_record(res['id'], 'diaper_wet')
            st.rerun()
    with col2:
        if st.button("💩 うんち", key="diaper_solid", use_container_width=True):
            add_care_record(res['id'], 'diaper_solid')
            st.rerun()
    
    with st.expander("📝 その他の記録"):
        other_note = st.text_input("内容", placeholder="例：機嫌よく遊んでいました", label_visibility="collapsed")
        if st.button("記録する", key="other", use_container_width=True):
            if other_note:
                add_care_record(res['id'], 'other', other_note)
                st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### 📋 本日の記録")
    
    if care_records:
        for record in care_records:
            record_time = record.get('record_time', '')[:16].replace('T', ' ') if record.get('record_time') else ''
            record_type = get_record_type_label(record.get('record_type', ''))
            details = record.get('details', '')
            st.markdown(f"- **{record_time}** {record_type} {details}")
    else:
        st.info("まだ記録がありません")

def show_pricing_tab(res: dict):
    st.markdown("### 💰 料金計算")
    
    service_category = res.get('service_category', '')
    st.info(f"サービス: **{service_category}**")
    
    staff_list = get_staff_list()
    staff_names = ["（選択してください）"] + [s['name'] for s in staff_list]
    
    current_staff = res.get('staff_name', '')
    staff_index = staff_names.index(current_staff) if current_staff in staff_names else 0
    
    selected_staff = st.selectbox(
        "担当スタッフ",
        staff_names,
        index=staff_index
    )
    
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
    
    is_cancelled = res.get('is_cancelled', 0)
    
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
    st.markdown(f"""
    - 基本保育料: ¥{pricing['base_price']:,}
    {"- 施設利用料: ¥" + f"{pricing['facility_fee']:,}" if pricing['facility_fee'] else ""}
    {"- 交通費: ¥" + f"{pricing['transport_fee']:,}" if pricing['transport_fee'] else ""}
    {"- 延長料金: ¥" + f"{pricing['extension_fee']:,}" if pricing['extension_fee'] else ""}
    {"- 追加料金: ¥" + f"{pricing['additional_fee']:,}" if pricing['additional_fee'] else ""}
    """)
    
    if is_cancelled:
        st.warning("※ キャンセルのため50%のみ請求")
    
    st.markdown(f"## 💴 合計: ¥{pricing['total']:,}")
    
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
            'transport_fee': transport_fee,
            'additional_fee': additional_fee,
            'additional_note': additional_note,
            'discount1': discount1 if discount1 != "なし" else '',
            'discount1_amount': discount1_amount,
            'discount2': discount2 if discount2 != "なし" else '',
            'discount2_amount': discount2_amount,
            'certification_date': cert_date,
            'certification_type': cert_type,
            'total_amount': pricing['total']
        }
        update_attendance(res['id'], update_data)
        st.success("✅ 保存しました！")
        st.rerun()

def show_notes_tab(res: dict):
    st.markdown("### 📄 連絡帳")
    
    care_records = get_care_records(res['id'])
    child_name = res.get('child_name', '')
    
    summary = generate_care_summary(care_records, child_name)
    
    st.text_area("本日のご様子", value=summary, height=250, key="care_summary", label_visibility="collapsed")
    
    if st.button("📋 コピー用に表示", use_container_width=True):
        st.code(summary, language=None)

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
    
    search_date = st.date_input("日付で絞り込み", value=None, key="receipt_date")
    
    reservations = get_all_reservations()
    
    if search_date:
        reservations = [r for r in reservations if r.get('reservation_date') == search_date.isoformat()]
    
    for res in reservations[:20]:
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

if __name__ == "__main__":
    main()
