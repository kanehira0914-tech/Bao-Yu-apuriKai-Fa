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
    page_title="こぐまハウス 業務支援システム",
    page_icon="🐻",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #5D4E37;
        padding: 1rem 0;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #8B7355;
        margin-bottom: 1rem;
    }
    .card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .status-active {
        color: #28a745;
        font-weight: bold;
    }
    .status-cancelled {
        color: #dc3545;
        font-weight: bold;
    }
    .big-button button {
        font-size: 1.5rem !important;
        padding: 1rem 2rem !important;
    }
    .stButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

init_database()

if 'selected_reservation_id' not in st.session_state:
    st.session_state.selected_reservation_id = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "home"

def main():
    st.sidebar.markdown("## 🐻 こぐまハウス")
    st.sidebar.markdown("業務支援システム")
    st.sidebar.markdown("---")
    
    menu = st.sidebar.radio(
        "メニュー",
        ["🏠 ホーム", "📁 データ取込", "👶 本日の児童", "📋 予約一覧", "📝 実績入力", "🧾 領収書発行"],
        label_visibility="collapsed"
    )
    
    if "ホーム" in menu:
        show_home()
    elif "データ取込" in menu:
        show_data_import()
    elif "本日の児童" in menu:
        show_today_children()
    elif "予約一覧" in menu:
        show_reservations()
    elif "実績入力" in menu:
        show_record_input()
    elif "領収書発行" in menu:
        show_receipt_generation()

def show_home():
    st.markdown('<div class="main-header">🐻 こぐまハウス 業務支援システム</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    today = date.today().isoformat()
    today_reservations = get_reservations_by_date(today)
    all_reservations = get_all_reservations()
    
    with col1:
        st.metric("本日の予約", f"{len(today_reservations)}件")
    
    with col2:
        active = sum(1 for r in today_reservations if not r.get('is_cancelled'))
        st.metric("受入予定", f"{active}件")
    
    with col3:
        st.metric("総予約数", f"{len(all_reservations)}件")
    
    st.markdown("---")
    
    st.subheader("📋 本日の予約一覧")
    if today_reservations:
        for res in today_reservations:
            is_cancelled = res.get('is_cancelled', 0)
            status_class = "status-cancelled" if is_cancelled else "status-active"
            status_text = "キャンセル" if is_cancelled else "予定"
            
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                with col1:
                    st.write(f"**{res.get('child_name', '')}**")
                    st.caption(res.get('child_name_kana', ''))
                with col2:
                    st.write(f"{res.get('start_time', '')} - {res.get('end_time', '')}")
                with col3:
                    st.write(res.get('service_category', ''))
                with col4:
                    st.markdown(f'<span class="{status_class}">{status_text}</span>', unsafe_allow_html=True)
                st.markdown("---")
    else:
        st.info("本日の予約はありません")
    
    st.markdown("---")
    st.subheader("🔧 クイックアクション")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📁 CSVデータ取込", use_container_width=True):
            st.session_state.current_page = "import"
            st.rerun()
    with col2:
        if st.button("👶 本日の児童一覧", use_container_width=True):
            st.session_state.current_page = "today"
            st.rerun()
    with col3:
        if st.button("🧾 領収書発行", use_container_width=True):
            st.session_state.current_page = "receipt"
            st.rerun()

def show_data_import():
    st.markdown('<div class="main-header">📁 CSVデータ取込</div>', unsafe_allow_html=True)
    st.markdown("SelectTypeからエクスポートした予約CSVをアップロードしてください。")
    
    uploaded_file = st.file_uploader(
        "CSVファイルを選択",
        type=['csv'],
        help="SelectType形式のCSVファイルをアップロードしてください"
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
                st.error("ファイルの読み込みに失敗しました。エンコーディングを確認してください。")
                return
            
            st.success(f"✅ ファイルを読み込みました（{len(df)}行）")
            
            with st.expander("📊 プレビュー（最初の10件）"):
                st.dataframe(df.head(10))
            
            st.markdown("### 取込オプション")
            
            if st.button("📥 データベースに取り込む", type="primary", use_container_width=True):
                with st.spinner("取込中..."):
                    count = import_csv_data(df)
                    st.success(f"✅ {count}件のデータを取り込みました！")
                    st.balloons()
        
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")
    
    st.markdown("---")
    st.markdown("### 📌 CSVフォーマットについて")
    st.info("""
    以下の列が含まれるSelectType形式のCSVに対応しています：
    - 予約日時
    - 予約内容
    - お子様のお名前
    - お子様のお名前(ふりがな)
    - メールアドレス
    - 住所
    - 保護者名（東京都BS事業申請者）
    - 決済金額 等
    """)

def show_today_children():
    st.markdown('<div class="main-header">👶 本日の児童一覧</div>', unsafe_allow_html=True)
    
    selected_date = st.date_input("日付を選択", value=date.today())
    
    reservations = get_reservations_by_date(selected_date.isoformat())
    
    if not reservations:
        st.info("選択した日付の予約はありません")
        return
    
    for res in reservations:
        is_cancelled = res.get('is_cancelled', 0)
        
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                status_icon = "❌" if is_cancelled else "✅"
                st.markdown(f"### {status_icon} {res.get('child_name', '')}")
                st.caption(f"({res.get('child_name_kana', '')})")
                
                st.write(f"⏰ {res.get('start_time', '')} - {res.get('end_time', '')}")
                st.write(f"📋 {res.get('service_category', '')}")
                
                if res.get('check_in_time'):
                    st.write(f"🟢 登園: {res.get('check_in_time', '')[:16]}")
                if res.get('check_out_time'):
                    st.write(f"🔴 降園: {res.get('check_out_time', '')[:16]}")
            
            with col2:
                if st.button("詳細を開く", key=f"detail_{res['id']}", use_container_width=True):
                    st.session_state.selected_reservation_id = res['id']
                    st.rerun()
            
            st.markdown("---")

def show_reservations():
    st.markdown('<div class="main-header">📋 予約一覧</div>', unsafe_allow_html=True)
    
    reservations = get_all_reservations()
    
    if not reservations:
        st.info("予約データがありません。CSVを取り込んでください。")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        search_name = st.text_input("🔍 お子様の名前で検索")
    with col2:
        category_filter = st.selectbox(
            "サービス区分",
            ["すべて", "一時預かり保育", "ベビーシッター（施設型）", "ベビーシッター（自宅派遣型）", "その他"]
        )
    
    filtered = reservations
    if search_name:
        filtered = [r for r in filtered if search_name in r.get('child_name', '') or search_name in r.get('child_name_kana', '')]
    if category_filter != "すべて":
        filtered = [r for r in filtered if r.get('service_category') == category_filter]
    
    st.write(f"全{len(filtered)}件")
    
    for res in filtered[:50]:
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
            
            with col1:
                st.write(f"**{res.get('child_name', '')}**")
            with col2:
                st.write(res.get('reservation_date', ''))
            with col3:
                st.write(res.get('service_category', '')[:10])
            with col4:
                amount = res.get('total_amount', 0) or 0
                st.write(f"¥{amount:,}")
            with col5:
                if st.button("選択", key=f"select_{res['id']}"):
                    st.session_state.selected_reservation_id = res['id']
                    st.rerun()
            
            st.markdown("---")

def show_record_input():
    st.markdown('<div class="main-header">📝 実績入力</div>', unsafe_allow_html=True)
    
    if st.session_state.selected_reservation_id:
        show_detail_input(st.session_state.selected_reservation_id)
    else:
        st.info("👆 「本日の児童」または「予約一覧」から児童を選択してください")
        
        st.markdown("---")
        st.subheader("📅 本日の予約から選択")
        
        today_reservations = get_reservations_by_date(date.today().isoformat())
        
        if today_reservations:
            for res in today_reservations:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**{res.get('child_name', '')}** - {res.get('start_time', '')}〜{res.get('end_time', '')}")
                with col2:
                    if st.button("選択", key=f"quick_{res['id']}"):
                        st.session_state.selected_reservation_id = res['id']
                        st.rerun()
        else:
            st.write("本日の予約はありません")

def show_detail_input(reservation_id: int):
    res = get_reservation_by_id(reservation_id)
    
    if not res:
        st.error("予約が見つかりません")
        st.session_state.selected_reservation_id = None
        return
    
    if st.button("← 一覧に戻る"):
        st.session_state.selected_reservation_id = None
        st.rerun()
    
    st.markdown(f"## 👶 {res.get('child_name', '')}さん")
    st.caption(f"({res.get('child_name_kana', '')})")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"📅 {res.get('reservation_date', '')}")
    with col2:
        st.info(f"⏰ {res.get('start_time', '')} - {res.get('end_time', '')}")
    with col3:
        st.info(f"📋 {res.get('service_category', '')}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🚪 登降園", "🍚 ケア記録", "💰 料金計算", "📄 連絡帳"])
    
    with tab1:
        show_attendance_tab(res)
    
    with tab2:
        show_care_tab(res)
    
    with tab3:
        show_pricing_tab(res)
    
    with tab4:
        show_notes_tab(res)

def show_attendance_tab(res: dict):
    st.subheader("🚪 登降園管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🟢 登園")
        if res.get('check_in_time'):
            st.success(f"登園済: {res['check_in_time'][:16]}")
        else:
            if st.button("🟢 登園を記録", type="primary", use_container_width=True, key="checkin"):
                update_attendance(res['id'], {'check_in_time': datetime.now().isoformat()})
                st.success("登園を記録しました！")
                st.rerun()
    
    with col2:
        st.markdown("### 🔴 降園")
        if res.get('check_out_time'):
            st.success(f"降園済: {res['check_out_time'][:16]}")
        else:
            if st.button("🔴 降園を記録", type="primary", use_container_width=True, key="checkout"):
                now = datetime.now()
                update_data = {'check_out_time': now.isoformat()}
                
                scheduled_end = res.get('end_time', '')
                if scheduled_end:
                    ext_min, ext_fee = calculate_extension_fee(scheduled_end, now.strftime("%H:%M"))
                    if ext_min > 0:
                        update_data['extension_minutes'] = ext_min
                        update_data['extension_fee'] = ext_fee
                        st.warning(f"⏰ 延長{ext_min}分（延長料金: ¥{ext_fee:,}）")
                
                update_attendance(res['id'], update_data)
                st.success("降園を記録しました！")
                st.rerun()
    
    st.markdown("---")
    
    st.subheader("❌ キャンセル処理")
    
    if res.get('is_cancelled'):
        st.warning(f"この予約はキャンセル済みです（{res.get('cancel_type', '')}）")
    else:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📅 当日キャンセル（50%請求）", use_container_width=True):
                base_price = res.get('base_price', 0) or 0
                cancel_amount = int(base_price * CANCEL_FEE_RATE)
                update_attendance(res['id'], {
                    'is_cancelled': 1,
                    'cancel_type': '当日キャンセル',
                    'total_amount': cancel_amount
                })
                st.warning(f"当日キャンセルとして処理しました（請求額: ¥{cancel_amount:,}）")
                st.rerun()
        with col2:
            if st.button("🚫 無料キャンセル", use_container_width=True):
                update_attendance(res['id'], {
                    'is_cancelled': 1,
                    'cancel_type': '無料キャンセル',
                    'total_amount': 0
                })
                st.info("無料キャンセルとして処理しました")
                st.rerun()

def show_care_tab(res: dict):
    st.subheader("🍚 ケア記録")
    
    care_records = get_care_records(res['id'])
    
    st.markdown("### 記録を追加")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**🍚 食事**")
        if st.button("食事開始", key="meal_start", use_container_width=True):
            add_care_record(res['id'], 'meal_start')
            st.rerun()
        if st.button("食事終了", key="meal_end", use_container_width=True):
            add_care_record(res['id'], 'meal_end')
            st.rerun()
        if st.button("おやつ", key="snack", use_container_width=True):
            add_care_record(res['id'], 'snack')
            st.rerun()
    
    with col2:
        st.markdown("**😴 睡眠**")
        if st.button("お昼寝開始", key="sleep_start", use_container_width=True):
            add_care_record(res['id'], 'sleep_start')
            st.rerun()
        if st.button("お昼寝終了", key="sleep_end", use_container_width=True):
            add_care_record(res['id'], 'sleep_end')
            st.rerun()
        if st.button("ミルク", key="milk", use_container_width=True):
            add_care_record(res['id'], 'milk')
            st.rerun()
    
    with col3:
        st.markdown("**🚽 排泄**")
        if st.button("おしっこ", key="diaper_wet", use_container_width=True):
            add_care_record(res['id'], 'diaper_wet')
            st.rerun()
        if st.button("うんち", key="diaper_solid", use_container_width=True):
            add_care_record(res['id'], 'diaper_solid')
            st.rerun()
    
    other_note = st.text_input("その他の記録")
    if st.button("その他を記録", key="other"):
        if other_note:
            add_care_record(res['id'], 'other', other_note)
            st.rerun()
    
    st.markdown("---")
    st.markdown("### 📋 本日の記録")
    
    if care_records:
        for record in care_records:
            record_time = record.get('record_time', '')[:16] if record.get('record_time') else ''
            record_type = get_record_type_label(record.get('record_type', ''))
            details = record.get('details', '')
            
            st.write(f"⏰ {record_time} - **{record_type}** {details}")
    else:
        st.info("まだ記録がありません")

def show_pricing_tab(res: dict):
    st.subheader("💰 料金計算")
    
    service_category = res.get('service_category', '')
    
    st.info(f"サービス区分: **{service_category}**")
    
    staff_list = get_staff_list()
    staff_names = [""] + [s['name'] for s in staff_list]
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_staff = st.selectbox(
            "担当スタッフ",
            staff_names,
            index=staff_names.index(res.get('staff_name', '')) if res.get('staff_name') in staff_names else 0
        )
        
        base_price = st.number_input(
            "基本保育料",
            value=res.get('base_price', 0) or 0,
            step=100
        )
        
        if service_category == "一時預かり保育":
            include_facility = st.checkbox("施設利用料を含める（¥550）", value=bool(res.get('facility_fee')))
            facility_fee = FACILITY_FEE if include_facility else 0
        else:
            facility_fee = 0
    
    with col2:
        if service_category == "ベビーシッター（自宅派遣型）":
            transport_fee = st.number_input("交通費", value=res.get('transport_fee', 0) or 0, step=100)
        else:
            transport_fee = 0
        
        extension_fee = res.get('extension_fee', 0) or 0
        if extension_fee > 0:
            st.warning(f"延長料金: ¥{extension_fee:,}")
        
        additional_fee = st.number_input("追加料金", value=res.get('additional_fee', 0) or 0, step=100)
        additional_note = st.text_input("追加料金メモ", value=res.get('additional_note', '') or '')
    
    st.markdown("---")
    st.markdown("### 割引")
    
    col1, col2 = st.columns(2)
    with col1:
        discount1 = st.text_input("割引①（名称）", value=res.get('discount1', '') or '')
        discount1_amount = st.number_input("割引①金額", value=res.get('discount1_amount', 0) or 0, step=100)
    with col2:
        discount2 = st.text_input("割引②（名称）", value=res.get('discount2', '') or '')
        discount2_amount = st.number_input("割引②金額", value=res.get('discount2_amount', 0) or 0, step=100)
    
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
    
    st.markdown("---")
    st.markdown("### 📊 料金内訳")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"基本保育料: ¥{pricing['base_price']:,}")
        if pricing['facility_fee']:
            st.write(f"施設利用料: ¥{pricing['facility_fee']:,}")
        if pricing['transport_fee']:
            st.write(f"交通費: ¥{pricing['transport_fee']:,}")
    with col2:
        if pricing['extension_fee']:
            st.write(f"延長料金: ¥{pricing['extension_fee']:,}")
        if pricing['additional_fee']:
            st.write(f"追加料金: ¥{pricing['additional_fee']:,}")
        if pricing['discount1_amount'] or pricing['discount2_amount']:
            st.write(f"割引合計: -¥{pricing['discount1_amount'] + pricing['discount2_amount']:,}")
    
    st.markdown(f"## 合計: ¥{pricing['total']:,}")
    
    if is_cancelled:
        st.warning("※ キャンセルのため、基本保育料の50%のみ請求")
    
    if needs_certification(service_category):
        st.markdown("---")
        st.markdown("### 📜 要件証明")
        
        selected_staff_data = next((s for s in staff_list if s['name'] == selected_staff), None)
        
        cert_date = st.text_input(
            "要件証明日",
            value=selected_staff_data['certification_date'] if selected_staff_data else res.get('certification_date', '') or ''
        )
        cert_type = st.text_input(
            "要件",
            value=selected_staff_data['certification_type'] if selected_staff_data else res.get('certification_type', '') or ''
        )
    else:
        cert_date = ''
        cert_type = ''
    
    if st.button("💾 保存", type="primary", use_container_width=True):
        update_data = {
            'staff_name': selected_staff,
            'transport_fee': transport_fee,
            'additional_fee': additional_fee,
            'additional_note': additional_note,
            'discount1': discount1,
            'discount1_amount': discount1_amount,
            'discount2': discount2,
            'discount2_amount': discount2_amount,
            'certification_date': cert_date,
            'certification_type': cert_type,
            'total_amount': pricing['total']
        }
        update_attendance(res['id'], update_data)
        st.success("保存しました！")
        st.rerun()

def show_notes_tab(res: dict):
    st.subheader("📄 連絡帳")
    
    care_records = get_care_records(res['id'])
    child_name = res.get('child_name', '')
    
    summary = generate_care_summary(care_records, child_name)
    
    st.markdown("### 本日のご様子")
    st.text_area("連絡帳テキスト", value=summary, height=300, key="care_summary")
    
    if st.button("📋 テキストをコピー用に表示"):
        st.code(summary, language=None)

def show_receipt_generation():
    st.markdown('<div class="main-header">🧾 領収書発行</div>', unsafe_allow_html=True)
    
    if st.session_state.selected_reservation_id:
        res = get_reservation_by_id(st.session_state.selected_reservation_id)
        
        if res:
            st.info(f"選択中: **{res.get('child_name', '')}** ({res.get('reservation_date', '')})")
            
            if st.button("🧾 領収書PDFを発行", type="primary", use_container_width=True):
                try:
                    with st.spinner("PDF生成中..."):
                        pdf_path = generate_receipt_pdf(res)
                    
                    st.success(f"✅ 領収書を生成しました！")
                    
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📥 PDFをダウンロード",
                            data=f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"PDF生成エラー: {str(e)}")
            
            if st.button("← 別の予約を選択"):
                st.session_state.selected_reservation_id = None
                st.rerun()
    else:
        st.info("領収書を発行する予約を選択してください")
    
    st.markdown("---")
    st.subheader("📋 発行対象を選択")
    
    col1, col2 = st.columns(2)
    with col1:
        search_date = st.date_input("日付で絞り込み", value=None)
    with col2:
        search_name = st.text_input("名前で検索")
    
    reservations = get_all_reservations()
    
    if search_date:
        reservations = [r for r in reservations if r.get('reservation_date') == search_date.isoformat()]
    if search_name:
        reservations = [r for r in reservations if search_name in r.get('child_name', '')]
    
    for res in reservations[:20]:
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        with col1:
            st.write(f"**{res.get('child_name', '')}**")
        with col2:
            st.write(res.get('reservation_date', ''))
        with col3:
            amount = res.get('total_amount', 0) or 0
            st.write(f"¥{amount:,}")
        with col4:
            if st.button("選択", key=f"receipt_{res['id']}"):
                st.session_state.selected_reservation_id = res['id']
                st.rerun()
        st.markdown("---")

if __name__ == "__main__":
    main()
