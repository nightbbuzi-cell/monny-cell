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
DATA_FILE = "group_expense_data.csv"
MEMBERS_FILE = "group_members.txt"
DEFAULT_MEMBERS = ["陳胤翔", "鄭宇廷", "朋友A"]

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
            except: continue
    for i, line in enumerate(results):
        if any(k in line for k in ["發票金額", "付現", "總計", "現金"]):
            nums = re.findall(r'\d+', "".join(results[i:i+2]))
            if nums: total = float(nums[0]); break
    return items, total

# --- UI 介面 ---
st.title("💰 智慧記帳：專業防重複系統")

if 'group_members' not in st.session_state:
    st.session_state['group_members'] = load_members()
GROUP_MEMBERS = st.session_state['group_members']

if 'pending_items' not in st.session_state:
    st.session_state['pending_items'] = []

with st.sidebar:
    st.header(" 群組與個人設定")
    
    with st.expander("➕ 邀請/新增成員", expanded=False):
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

    current_user = st.selectbox("👤 您是哪位？ (當前操作者)", GROUP_MEMBERS)
    st.info(f"👋 哈囉，**{current_user}**！\n\n(您新增的帳目將會標記由您記錄)")
    
    st.divider()
    st.header("📸 掃描收據")
    uploaded_file = st.file_uploader("上傳收據", type=["jpg", "png"])
    
    if uploaded_file:
        st.image(uploaded_file, caption="收據預覽", use_container_width=True)
        
    if uploaded_file and st.button("🚀 執行辨識"):
        if HAS_EASYOCR:
            with st.spinner("辨識中..."):
                items, total = process_receipt(Image.open(uploaded_file))
                st.session_state['pending_items'] = items
                st.session_state['detected_total'] = total
        else:
            st.error("系統尚未安裝 easyocr 套件，無法進行影像辨識。請在終端機執行 `pip install easyocr` 來安裝。")

    st.divider()
    if st.button("🗑️ 清空所有歷史紀錄", type="primary"):
        save_full_df(pd.DataFrame(columns=["日期", "品項", "金額", "誰付錢_代墊", "誰消費_應付", "分帳模式", "記錄者"]))
        st.rerun()

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📝 帳務輸入 (緩衝區)")
    
    with st.expander("➕ 手動新增品項", expanded=False):
        with st.form("manual_add", clear_on_submit=True):
            mn, mp = st.text_input("品項名稱"), st.number_input("金額", min_value=0.0)
            if st.form_submit_button("加入清單") and mn:
                st.session_state['pending_items'].append({"name": mn, "price": mp}); st.rerun()

    # 只要有待處理品項，或者剛剛執行過影像掃描（有產生 detected_total），就顯示緩衝區
    show_buffer = len(st.session_state['pending_items']) > 0 or ('detected_total' in st.session_state)

    if show_buffer:
        st.write("#### ⏳ 待確認明細")
        
        if 'detected_total' in st.session_state and st.session_state['detected_total'] > 0:
            st.info(f"🧾 系統辨識收據總金額為：**${st.session_state['detected_total']}** (僅供參考)")
        
        # --- 新增：確認與調整總品項數量 ---
        current_count = len(st.session_state['pending_items'])
        new_count = st.number_input("🔢 確認/調整總品項數量", min_value=0, value=current_count, step=1, help="若辨識數量有誤，可直接修改此數字，系統會自動為您增減輸入欄位。")
        
        if new_count != current_count:
            if new_count > current_count:
                # 如果新數量比較多，補足缺少的空品項
                for _ in range(new_count - current_count):
                    st.session_state['pending_items'].append({"name": "", "price": 0.0})
            else:
                # 如果新數量比較少，從後面刪除多餘的品項
                st.session_state['pending_items'] = st.session_state['pending_items'][:new_count]
            st.rerun()

        # 用來存儲使用者在 UI 上修改後的結果
        confirmed_batch = []
        
        for idx, item in enumerate(st.session_state['pending_items']):
            with st.container(border=True):
                # 增加一個欄位給刪除按鈕
                c_n, c_p, c_m, c_del = st.columns([2, 1, 1.5, 0.4])
                un = c_n.text_input("品項", item['name'], key=f"n_{idx}")
                up = c_p.number_input("金額", value=item['price'], key=f"p_{idx}")
                u_mode = c_m.selectbox("分帳模式", ["全算我的", "指定某人", "大家均分"], key=f"m_{idx}")
                
                # 在新欄位中加入刪除按鈕，並透過 st.write 調整垂直位置
                c_del.write(" ") # 佔位符，讓按鈕稍微往下對齊
                if c_del.button("🗑️", key=f"del_{idx}", help="刪除此項目"):
                    st.session_state['pending_items'].pop(idx)
                    st.rerun()

                target_consumer = current_user
                if u_mode == "指定某人": target_consumer = st.selectbox("誰消費？", GROUP_MEMBERS, key=f"t_{idx}")
                elif u_mode == "大家均分": target_consumer = "所有人"
                
                confirmed_batch.append({
                    "日期": datetime.now().strftime("%Y-%m-%d"),
                    "品項": un, "金額": up, "誰付錢_代墊": current_user, 
                "誰消費_應付": target_consumer, "分帳模式": u_mode,
                "記錄者": current_user
                })

        st.divider()
        c_btn1, c_btn2 = st.columns(2)
        if c_btn1.button("✅ 批次儲存至帳本", type="primary", use_container_width=True):
            df_tmp = load_all_data()
            df_tmp = pd.concat([df_tmp, pd.DataFrame(confirmed_batch)], ignore_index=True)
            save_full_df(df_tmp)
            st.session_state['pending_items'] = [] # 清空緩衝區
            if 'detected_total' in st.session_state:
                del st.session_state['detected_total'] # 清除暫存金額
            st.success("全部項目已入帳！")
            st.rerun()
            
        if c_btn2.button("❌ 全部捨棄", use_container_width=True):
            st.session_state['pending_items'] = []
            if 'detected_total' in st.session_state:
                del st.session_state['detected_total']
            st.rerun()
    else:
        st.info("目前沒有待處理項目。")

with col2:
    st.subheader("📊 帳本清算中心")
    placeholder = st.container()
    data = load_all_data()
    
    st.write("#### 📜 歷史明細編輯器")
    edited_df = st.data_editor(
        data, num_rows="dynamic", use_container_width=True,
        column_config={
            "金額": st.column_config.NumberColumn(format="$%.1f"),
            "誰付錢_代墊": st.column_config.SelectboxColumn(options=GROUP_MEMBERS),
            "誰消費_應付": st.column_config.SelectboxColumn(options=GROUP_MEMBERS + ["所有人"]),
            "分帳模式": st.column_config.SelectboxColumn(options=["全算我的", "指定某人", "大家均分"]),
            "記錄者": st.column_config.TextColumn("📝 記錄者", disabled=True)
        },
        key="history_editor"
    )

    with placeholder:
        st.write("#### 💰 誰欠誰錢 (結算表)")
        if not edited_df.empty:
            summary = []
            num_m = len(GROUP_MEMBERS)
            for m in GROUP_MEMBERS:
                paid = edited_df[edited_df['誰付錢_代墊'] == m]['金額'].sum()
                direct = edited_df[edited_df['誰消費_應付'] == m]['金額'].sum()
                split = edited_df[edited_df['誰消費_應付'] == '所有人']['金額'].sum() / num_m
                summary.append({"成員": m, "代墊金額": paid, "個人應付": direct + split, "餘額": paid - (direct + split)})
            st.table(pd.DataFrame(summary).style.format(precision=1).map(
                lambda v: 'color: red;' if v < 0 else 'color: green;', subset=['餘額']
            ))

    if st.button("💾 保存編輯器變更"):
        save_full_df(edited_df); st.success("已更新資料庫！"); st.rerun()