import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import streamlit.components.v1 as components

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
    
    /* --- 📱 跨裝置閱讀舒適度優化 (流體字體與排版) --- */
    p, span, label, div[data-testid="stMarkdownContainer"] { line-height: 1.6 !important; }
    h1 { font-size: clamp(1.5rem, 4vw, 2.2rem) !important; }
    h3 { font-size: clamp(1.2rem, 3vw, 1.5rem) !important; }
    h4 { font-size: clamp(1.1rem, 2.5vw, 1.2rem) !important; }
    [data-testid="stMetricValue"] { font-size: clamp(1.5rem, 4vw, 2rem) !important; }
    /* 關鍵修復：防止 iPhone(iOS) 在點擊輸入框時強制放大畫面 */
    input, select, textarea, [data-baseweb="select"] { font-size: 16px !important; }
</style>
""", unsafe_allow_html=True)

# --- 📱 注入手機版滑動切換分頁 (Swipe to switch tabs) 的 JavaScript ---
components.html("""
<script>
const parentWindow = window.parent;
const doc = parentWindow.document;

// 防止重新載入時重複綁定監聽器
if (!parentWindow.swipeBound) {
    let touchstartX = 0;
    let touchstartY = 0;

    doc.addEventListener('touchstart', e => {
        touchstartX = e.changedTouches[0].screenX;
        touchstartY = e.changedTouches[0].screenY;
    }, {passive: true});

    doc.addEventListener('touchend', e => {
        let touchendX = e.changedTouches[0].screenX;
        let touchendY = e.changedTouches[0].screenY;
        
        // 如果滑動位置在資料表(DataFrame)內，保留原生水平滾動，不切換分頁
        if (e.target.closest('[data-testid="stDataFrame"]')) return;

        const xDiff = touchendX - touchstartX;
        const yDiff = touchendY - touchstartY;

        // 判斷是否為水平滑動 (X軸位移大於Y軸，且滑動距離超過 50px)
        if (Math.abs(xDiff) > Math.abs(yDiff) && Math.abs(xDiff) > 50) {
            const tabs = Array.from(doc.querySelectorAll('button[role="tab"]'));
            if (!tabs || tabs.length === 0) return;

            const activeTabIndex = tabs.findIndex(tab => tab.getAttribute('aria-selected') === 'true');
            if (activeTabIndex === -1) return;

            if (xDiff < 0) { // 向左滑 -> 下一頁
                if (activeTabIndex < tabs.length - 1) tabs[activeTabIndex + 1].click();
            } else { // 向右滑 -> 上一頁
                if (activeTabIndex > 0) tabs[activeTabIndex - 1].click();
            }
        }
    }, {passive: true});
    
    parentWindow.swipeBound = true;
}
</script>
""", height=0, width=0)

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
    df["記錄者"] = df["記錄者"].fillna(current_user if 'current_user' in locals() else "未知") # 確保沒有空值
        
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
if 'group_members' not in st.session_state:
    st.session_state['group_members'] = load_members()
GROUP_MEMBERS = st.session_state['group_members']

if 'pending_items' not in st.session_state:
    st.session_state['pending_items'] = []

# --- 初始導引 (Apple 風格歡迎畫面) ---
if not GROUP_MEMBERS:
    st.title(":material/waving_hand: 歡迎使用智慧記帳")
    st.markdown("#### 為了給您最舒適的體驗，請先設定第一位成員。")
    st.caption("這通常是您自己。未來您可以隨時在「設定」中加入其他夥伴！")
    
    with st.container(border=True):
        col_m, col_btn = st.columns([3, 1])
        with col_m:
            first_member = st.text_input("輸入您的名稱", placeholder="例如：自己、小明...", label_visibility="collapsed")
        with col_btn:
            if st.button(":material/person_add: 開始使用", type="primary", use_container_width=True):
                if first_member and first_member not in GROUP_MEMBERS:
                    GROUP_MEMBERS.append(first_member)
                    save_members(GROUP_MEMBERS)
                    st.session_state['group_members'] = GROUP_MEMBERS
                    st.rerun()
                elif first_member in GROUP_MEMBERS:
                    st.warning("此成員已存在喔！")
    st.stop() 

# --- 主畫面頂部 (乾淨標題與操作者切換) ---
c_title, c_user = st.columns([3, 1])
with c_title:
    st.title(":material/account_balance_wallet: 你最信賴記帳的好夥伴")
with c_user:
    st.write("") # 微調垂直對齊
    current_user = st.selectbox(":material/person: 操作者", GROUP_MEMBERS, help="預設記帳人", label_visibility="collapsed")

# --- Apple 風格：無感切換的四個底部標籤 (Tabs) ---
tab1, tab2, tab3, tab4 = st.tabs([
    ":material/edit_document: 記帳", 
    ":material/payments: 結算", 
    ":material/history: 明細",
    ":material/settings: 設定"
])

with tab1:
    input_c1, input_c2 = st.columns(2)
    with input_c1:
        with st.container(border=True):
            st.write("#### :material/edit_square: 手動輸入")
            with st.form("manual_add", clear_on_submit=True):
                mn, mp = st.text_input("品項名稱"), st.number_input("金額", min_value=0.0)
                if st.form_submit_button("加入清單", use_container_width=True) and mn:
                    st.session_state['pending_items'].append({"name": mn, "price": mp}); st.rerun()
                    
    with input_c2:
        with st.container(border=True):
            st.write("#### :material/add_a_photo: 掃描收據")
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
                    c_target.info(":material/subdirectory_arrow_right: 所有人平分")
                else:
                    c_target.info(f":material/subdirectory_arrow_right: {u_payer} 自己負擔")
                
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
        st.write("#### :material/account_balance: 成員財務概況")
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
                    st.metric(label=f":material/person: {m} 的總消費", value=f"${personal_total:,.0f}")
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
    st.caption(":material/lightbulb: 若發現帳目有誤，可直接在此表格內雙擊修改，修改後記得點擊下方儲存。")
    data = load_all_data()
    
    edited_df = st.data_editor(
        data, num_rows="dynamic", use_container_width=True,
        column_config={
            "金額": st.column_config.NumberColumn(format="$%.1f"),
            "誰付錢_代墊": st.column_config.SelectboxColumn(options=GROUP_MEMBERS),
            "誰消費_應付": st.column_config.SelectboxColumn(options=GROUP_MEMBERS + ["所有人"]),
            "分帳模式": st.column_config.SelectboxColumn(options=["個人花費", "幫人代墊", "大家均分", "轉帳/還款"]),
            "記錄者": st.column_config.TextColumn("記錄者", disabled=True)
        },
        key="history_editor"
    )
    if st.button(":material/save: 保存編輯器變更", type="primary"):
        # 防呆：處理在編輯器中新增資料時，因鎖定欄位(記錄者)或忘記填寫而產生的空值
        edited_df['記錄者'] = edited_df['記錄者'].fillna(current_user)
        edited_df.loc[edited_df['記錄者'] == "", '記錄者'] = current_user
        edited_df['日期'] = edited_df['日期'].fillna(datetime.now().strftime("%Y-%m-%d"))
        edited_df.loc[edited_df['日期'] == "", '日期'] = datetime.now().strftime("%Y-%m-%d")
        
        save_full_df(edited_df)
        st.success("已更新資料庫！")
        st.rerun()

with tab4:
    st.write("#### :material/group: 成員管理")
    c_add, c_rem = st.columns(2)
    with c_add:
        with st.container(border=True):
            st.write("**:material/person_add: 新增成員**")
            new_member = st.text_input("輸入新成員名稱", placeholder="輸入名稱...", label_visibility="collapsed")
            if st.button("加入群組", use_container_width=True) and new_member:
                if new_member not in GROUP_MEMBERS:
                    GROUP_MEMBERS.append(new_member)
                    save_members(GROUP_MEMBERS)
                    st.session_state['group_members'] = GROUP_MEMBERS
                    st.success(f"已加入 {new_member}")
                    st.rerun()
                else:
                    st.warning("成員已存在")
    with c_rem:
        with st.container(border=True):
            st.write("**:material/person_remove: 移除成員**")
            if GROUP_MEMBERS:
                member_to_remove = st.selectbox("選擇要移除的成員", GROUP_MEMBERS, label_visibility="collapsed")
                if st.button("確認移除", type="primary", use_container_width=True):
                    GROUP_MEMBERS.remove(member_to_remove)
                    save_members(GROUP_MEMBERS)
                    st.session_state['group_members'] = GROUP_MEMBERS
                    st.rerun()
            else:
                st.info("目前沒有可移除的成員。")
                
    st.divider()
    st.write("#### :material/database: 系統與資料庫")
    if os.path.exists(DATA_FILE):
        file_size_kb = os.path.getsize(DATA_FILE) / 1024
        st.caption(f":material/save: 目前資料庫檔案大小: {file_size_kb:.2f} KB | 總記帳筆數: {len(load_all_data())} 筆")
        if st.button(":material/delete: 清空所有歷史紀錄", type="primary"):
            save_full_df(pd.DataFrame(columns=["日期", "品項", "金額", "誰付錢_代墊", "誰消費_應付", "分帳模式", "記錄者"]))
            st.rerun()

# --- 頁尾 (Footer) ---
st.markdown("""
    <div style='text-align: center; color: #888; font-size: 13px; margin-top: 50px;'>
        多媒高金生團隊製作<br>
        Copyright &copy; All Rights Reserved.
    </div>
""", unsafe_allow_html=True)