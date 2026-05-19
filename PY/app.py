import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
import numpy as np
import re
import os

# --- 基礎設定 ---
st.set_page_config(page_title="智慧記帳 - 專業防重複版", layout="wide")

# --- 🎨 自訂質感主題 (支援淺色/深色模式自動切換) ---
st.markdown("""
<style>
    /* 僅保留立體區塊的陰影與圓角設計，讓顏色完美跟隨 Streamlit 系統自動切換 */
    div[data-testid="stExpander"], div[data-testid="stForm"] { 
        border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); 
    }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "group_expense_data.csv")
MEMBERS_FILE = os.path.join(BASE_DIR, "group_members.txt")
DEFAULT_MEMBERS = []

def load_members():
    if os.path.exists(MEMBERS_FILE):
        with open(MEMBERS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    return DEFAULT_MEMBERS.copy()

def save_members(members):
    with open(MEMBERS_FILE, "w", encoding="utf-8") as f:
        for m in members:
            f.write(m + "\n")

@st.cache_resource
def load_ocr_reader():
    if HAS_EASYOCR:
        return easyocr.Reader(['ch_tra', 'en'])
    return None

reader = load_ocr_reader()

# --- 資料讀取與自動修正 ---
def load_all_data():
    if not os.path.exists(DATA_FILE):
        df = pd.DataFrame(columns=["日期", "品項", "金額", "誰付錢_代墊", "誰消費_應付", "分帳模式", "記錄者"])
        df.to_csv(DATA_FILE, index=False)
        return df
    df = pd.read_csv(DATA_FILE)
    if "記錄者" not in df.columns:
        df["記錄者"] = "未知" # 保護舊資料不會報錯
        
    # 自動轉換舊版的分帳模式名稱為新版
    df["分帳模式"] = df["分帳模式"].replace({
        "全算我的": "個人花費",
        "指定某人": "幫人代墊"
    })
    return df

def save_full_df(df):
    df.to_csv(DATA_FILE, index=False)

# --- 核心辨識邏輯 ---
def process_receipt(image):
    if reader is None:
        return [], 0.0
        
    img_array = np.array(image)
    results = reader.readtext(img_array, detail=0)
    items, total = [], 0.0
    for i in range(len(results)):
        line = results[i].strip()
        if "#" in line:
            try:
                name = results[i+1] if len(line) <= 4 else line.split("#")[-1]
                name = "".join(re.findall(r'[\u4e00-\u9fa5]+', name))
                price = 0.0
                for nl in results[i+1 : i+4]:
                    nums = re.findall(r'\d+', nl)
                    if nums:
                        pv = nums[0]
                        price = float(pv[:2] if len(pv) >= 3 and int(pv) > 100 else pv)
                        break
                if name: items.append({"name": name, "price": price})
            except Exception: continue
    for i, line in enumerate(results):
        if any(k in line for k in ["發票金額", "付現", "總計", "現金"]):
            nums = re.findall(r'\d+', "".join(results[i:i+2]))
            if nums: total = float(nums[0]); break
    return items, total

# --- UI 介面 ---
st.title(":material/account_balance_wallet: 智慧記帳：專業防重複系統 (:material/stars: 雲端更新版)")
st.markdown("##### :material/receipt_long: 輕鬆管理群組帳務，支援收據自動辨識、手動記帳與自動分帳計算！")
st.divider()

if 'group_members' not in st.session_state:
    st.session_state['group_members'] = load_members()
GROUP_MEMBERS = st.session_state['group_members']

if 'pending_items' not in st.session_state:
    st.session_state['pending_items'] = []

# --- 初始導引 (Onboarding) ---
if not GROUP_MEMBERS:
    st.info("👋 **歡迎來到智慧記帳系統！**")
    st.write("#### 🚀 第一步：請先建立您的記帳成員名單")
    st.caption("請輸入您或夥伴的名稱，加入第一位成員後即可解鎖完整的記帳功能！")
    
    with st.container(border=True):
        col_m, col_btn = st.columns([3, 1])
        with col_m:
            first_member = st.text_input("輸入新成員名稱", placeholder="例如：自己、小明...", label_visibility="collapsed")
        with col_btn:
            if st.button(":material/person_add: 建立成員", type="primary", use_container_width=True):
                if first_member and first_member not in GROUP_MEMBERS:
                    GROUP_MEMBERS.append(first_member)
                    save_members(GROUP_MEMBERS)
                    st.session_state['group_members'] = GROUP_MEMBERS
                    st.rerun()
                elif first_member in GROUP_MEMBERS:
                    st.warning("此成員已存在喔！")
    st.stop() # 停止渲染後續的側邊欄與記帳介面

with st.sidebar:
    st.header(f":material/group: 群組與個人設定 (共 {len(GROUP_MEMBERS)} 人)")
    
    with st.expander(":material/person_add: 邀請/新增成員", expanded=False):
        new_member = st.text_input("輸入新成員名稱")
        if st.button("加入群組") and new_member:
            if new_member not in GROUP_MEMBERS:
                GROUP_MEMBERS.append(new_member)
                save_members(GROUP_MEMBERS)
                st.session_state['group_members'] = GROUP_MEMBERS
                st.success(f"已將 {new_member} 加入群組！")
                st.rerun()
            else:
                st.warning("此成員已在群組中喔！")
                
    with st.expander(":material/person_remove: 移除成員", expanded=False):
        if GROUP_MEMBERS:
            member_to_remove = st.selectbox("選擇要移除的成員", GROUP_MEMBERS)
            if st.button("確認移除", type="primary"):
                GROUP_MEMBERS.remove(member_to_remove)
                save_members(GROUP_MEMBERS)
                st.session_state['group_members'] = GROUP_MEMBERS
                st.rerun()
        else:
            st.info("目前沒有成員可移除。")

    current_user = st.selectbox(":material/person: 您是哪位？ (當前操作者)", GROUP_MEMBERS)
    st.info(f":material/waving_hand: 哈囉，**{current_user}**！\n\n(您新增的帳目將會標記由您記錄)")
    
    st.divider()
    if os.path.exists(DATA_FILE):
        file_size_kb = os.path.getsize(DATA_FILE) / 1024
        st.caption(f":material/save: 目前資料庫檔案大小: {file_size_kb:.2f} KB")
        record_count = len(load_all_data())
        st.caption(f":material/receipt: 總記帳筆數: {record_count} 筆")
        
    if st.button(":material/delete: 清空所有歷史紀錄", type="primary"):
        save_full_df(pd.DataFrame(columns=["日期", "品項", "金額", "誰付錢_代墊", "誰消費_應付", "分帳模式", "記錄者"]))
        st.rerun()

# --- 循序漸進的主畫面分頁 ---
tab1, tab2, tab3 = st.tabs([
    ":material/edit_document: 1. 記帳輸入", 
    ":material/payments: 2. 結算總覽", 
    ":material/history: 3. 歷史修改"
])

with tab1:
    input_c1, input_c2 = st.columns(2)
    with input_c1:
        with st.container(border=True):
            st.write("#### ✍️ 手動輸入")
            with st.form("manual_add", clear_on_submit=True):
                mn, mp = st.text_input("品項名稱"), st.number_input("金額", min_value=0.0)
                if st.form_submit_button("加入清單", use_container_width=True) and mn:
                    st.session_state['pending_items'].append({"name": mn, "price": mp}); st.rerun()
                    
    with input_c2:
        with st.container(border=True):
            st.write("#### 📸 掃描收據")
            uploaded_file = st.file_uploader("上傳收據", type=["jpg", "png"], label_visibility="collapsed")
            if uploaded_file and st.button(":material/rocket_launch: 執行辨識", use_container_width=True):
                if HAS_EASYOCR:
                    with st.spinner("辨識中..."):
                        items, total = process_receipt(Image.open(uploaded_file))
                        st.session_state['pending_items'] = items
                        st.session_state['detected_total'] = total
                else:
                    st.error("系統尚未安裝 easyocr 套件，無法進行影像辨識。")

    # 只要有待處理品項，或者剛剛執行過影像掃描（有產生 detected_total），就顯示緩衝區
    show_buffer = len(st.session_state['pending_items']) > 0 or ('detected_total' in st.session_state)

    if show_buffer:
        st.divider()
        st.write("#### :material/hourglass_empty: 待確認明細")
        
        if 'detected_total' in st.session_state and st.session_state['detected_total'] > 0:
            st.info(f":material/receipt_long: 系統辨識收據總金額為：**${st.session_state['detected_total']}** (僅供參考)")
        
        current_count = len(st.session_state['pending_items'])
        new_count = st.number_input(":material/format_list_numbered: 確認/調整總品項數量", min_value=0, value=current_count, step=1, help="若辨識數量有誤，可直接修改此數字，系統會自動為您增減輸入欄位。")
        
        if new_count != current_count:
            if new_count > current_count:
                for _ in range(new_count - current_count):
                    st.session_state['pending_items'].append({"name": "", "price": 0.0})
            else:
                st.session_state['pending_items'] = st.session_state['pending_items'][:new_count]
            st.rerun()

        confirmed_batch = []
        
        for idx, item in enumerate(st.session_state['pending_items']):
            with st.container(border=True):
                c_n, c_p, c_del = st.columns([3, 2, 0.5])
                un = c_n.text_input("品項", item['name'], key=f"n_{idx}")
                up = c_p.number_input("金額", value=item['price'], key=f"p_{idx}")
                
                c_del.write(" ")
                if c_del.button(":material/delete:", key=f"del_{idx}", help="刪除此項目"):
                    st.session_state['pending_items'].pop(idx)
                    st.rerun()

                c_payer, c_m, c_target = st.columns(3)
                default_payer = GROUP_MEMBERS.index(current_user) if current_user in GROUP_MEMBERS else 0
                u_payer = c_payer.selectbox("付錢者", GROUP_MEMBERS, index=default_payer, key=f"payer_{idx}")
                u_mode = c_m.selectbox("分帳模式", ["個人花費", "幫人代墊", "大家均分", "轉帳/還款"], key=f"m_{idx}")
                
                target_consumer = u_payer
                if u_mode in ["幫人代墊", "轉帳/還款"]:
                    target_consumer = c_target.selectbox("對象", GROUP_MEMBERS, key=f"t_{idx}")
                elif u_mode == "大家均分":
                    target_consumer = "所有人"
                    c_target.info("👉 所有人平分")
                else:
                    c_target.info(f"👉 {u_payer} 自己負擔")
                
                confirmed_batch.append({
                    "日期": datetime.now().strftime("%Y-%m-%d"),
                    "品項": un, "金額": up, "誰付錢_代墊": u_payer, 
                    "誰消費_應付": target_consumer, "分帳模式": u_mode,
                    "記錄者": current_user
                })

        st.divider()
        c_btn1, c_btn2 = st.columns(2)
        if c_btn1.button(":material/check_circle: 批次儲存至帳本", type="primary", use_container_width=True):
            df_tmp = load_all_data()
            df_tmp = pd.concat([df_tmp, pd.DataFrame(confirmed_batch)], ignore_index=True)
            save_full_df(df_tmp)
            st.session_state['pending_items'] = []
            if 'detected_total' in st.session_state:
                del st.session_state['detected_total']
            st.success("全部項目已入帳！")
            st.rerun()
            
        if c_btn2.button(":material/cancel: 全部捨棄", use_container_width=True):
            st.session_state['pending_items'] = []
            if 'detected_total' in st.session_state:
                del st.session_state['detected_total']
            st.rerun()

with tab2:
    data = load_all_data()
    if data.empty:
        st.info("目前還沒有任何記帳紀錄喔！請先到「記帳輸入」新增帳目。")
    else:
        st.write("#### 💎 成員財務概況")
        summary = []
        num_m = len(GROUP_MEMBERS)
        
        # 為每個成員建立專屬的數據卡片
        m_cols = st.columns(len(GROUP_MEMBERS) if len(GROUP_MEMBERS) > 0 else 1)
        
        for i, m in enumerate(GROUP_MEMBERS):
            paid = data[data['誰付錢_代墊'] == m]['金額'].sum()
            direct = data[(data['誰消費_應付'] == m) & (data['分帳模式'] != "轉帳/還款")]['金額'].sum()
            split = data[data['誰消費_應付'] == '所有人']['金額'].sum() / num_m if num_m > 0 else 0
            personal_total = direct + split
            received = data[(data['誰消費_應付'] == m) & (data['分帳模式'] == "轉帳/還款")]['金額'].sum()
            balance = paid - (personal_total + received)
            
            summary.append({"成員": m, "個人總消費": personal_total, "總付/代墊": paid, "結算餘額": balance})
            
            # 顯示個人總消費卡片與結算狀態
            with m_cols[i]:
                with st.container(border=True):
                    st.metric(label=f"👤 {m} 的總消費", value=f"${personal_total:,.0f}")
                    if balance > 0:
                        st.markdown(f"**應收回：<span style='color:#388E3C;'>${balance:,.0f}</span>**", unsafe_allow_html=True)
                    elif balance < 0:
                        st.markdown(f"**須付款：<span style='color:#D32F2F;'>${abs(balance):,.0f}</span>**", unsafe_allow_html=True)
                    else:
                        st.markdown("**結算：$0**", unsafe_allow_html=True)

        st.divider()
        st.write("#### :material/payments: 詳細結算表")
        st.dataframe(pd.DataFrame(summary).style.format(precision=1).map(
            lambda v: 'color: #D32F2F; font-weight: bold;' if v < 0 else 'color: #388E3C; font-weight: bold;', subset=['結算餘額']
        ), use_container_width=True, hide_index=True)

with tab3:
    st.write("#### :material/history: 歷史明細編輯器")
    st.caption("💡 若發現帳目有誤，可直接在此表格內雙擊修改，修改後記得點擊下方儲存。")
    data = load_all_data()
    
    edited_df = st.data_editor(
        data, num_rows="dynamic", use_container_width=True,
        column_config={
            "金額": st.column_config.NumberColumn(format="$%.1f"),
            "誰付錢_代墊": st.column_config.SelectboxColumn(options=GROUP_MEMBERS),
            "誰消費_應付": st.column_config.SelectboxColumn(options=GROUP_MEMBERS + ["所有人"]),
            "分帳模式": st.column_config.SelectboxColumn(options=["個人花費", "幫人代墊", "大家均分", "轉帳/還款"]),
            "記錄者": st.column_config.TextColumn(":material/edit_document: 記錄者", disabled=True)
        },
        key="history_editor"
    )
    if st.button(":material/save: 保存編輯器變更", type="primary"):
        save_full_df(edited_df)
        st.success("已更新資料庫！")
        st.rerun()