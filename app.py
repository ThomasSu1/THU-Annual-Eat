"""
THU Annual Eat Web UI - 贤狼赫萝的年度干饭账本
=========================================
基于 Streamlit 的清华大学校园卡消费数据可视化工具。
包含自动深色模式修复、智能充值过滤和多维度数据图表。

Author: [Your Name/GitHub ID]
Theme: Spice and Wolf (Holo)
"""

import base64
import datetime
import json
import os
import requests
from typing import Optional, List, Dict, Any

import pandas as pd
import plotly.express as px
import streamlit as st
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


# ==========================================
# ⚙️ 配置与常量
# ==========================================
CONFIG_DIR = ".streamlit"
CONFIG_FILE = "config.toml"
THEME_CONFIG_CONTENT = """
[theme]
base = "light"
primaryColor = "#d84315"
backgroundColor = "#fdf6e3"
secondaryBackgroundColor = "#eee8d5"
textColor = "#3e2723"
font = "serif"
"""

# CSS 样式配置 (狼与香辛料主题)
SPICE_THEME_CSS = """
<style>
    /* 全局背景设置 */
    .stApp {
        background: radial-gradient(circle at center, #fdf6e3 0%, #f4e4bc 100%);
    }

    /* 输入框样式修正：强制白底黑字 */
    div[data-baseweb="input"] {
        background-color: #fffbf0 !important;
        border: 1px solid #8d6e63 !important;
    }
    input {
        color: #3e2723 !important;
        font-weight: bold;
    }
    
    /* 全局字体颜色修正 */
    label, .stMarkdown, h1, h2, h3, p, span, div, li {
        color: #3e2723 !important;
    }

    /* 侧边栏样式 */
    [data-testid="stSidebar"] {
        background-color: #eee8d5 !important;
    }
    
    /* 指标卡片 (Metric) 样式 */
    div[data-testid="metric-container"] {
        background-color: rgba(255, 255, 255, 0.7) !important;
        border: 2px solid #8d6e63 !important;
        box-shadow: none !important;
    }
    [data-testid="stMetricValue"] {
        color: #bf360c !important; /* 赫萝红 */
    }
    
    /* 按钮样式 */
    .stButton > button {
        background: linear-gradient(to bottom, #ffca28, #ffb300) !important;
        color: #3e2723 !important;
        border: 2px solid #e65100 !important;
    }
</style>
"""

# 黑名单关键词 (用于过滤充值记录)
BLACKLIST_KEYWORDS = [
    '充值', '圈存', '缴费', '补办', '校医院', '自助', '网费', 
    '存款', '退款', '补助', '财务', '领取'
]

# 图表字体配置
DARK_FONT_STYLE = dict(color='#3e2723', size=14, family='Noto Serif SC')


# ==========================================
# 🛠️ 辅助函数
# ==========================================

def ensure_light_theme() -> bool:
    """
    检查并创建 Streamlit 配置文件以强制开启浅色模式。
    返回: True 如果刚刚创建了文件 (需要重启), False 如果文件已存在。
    """
    config_path = os.path.join(CONFIG_DIR, CONFIG_FILE)
    if not os.path.exists(config_path):
        try:
            if not os.path.exists(CONFIG_DIR):
                os.makedirs(CONFIG_DIR)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(THEME_CONFIG_CONTENT)
            return True
        except OSError:
            pass
    return False

def decrypt_aes_ecb(encrypted_data: str) -> str:
    """
    解密校园卡 API 返回的 AES 加密数据。
    """
    try:
        # key 位于字符串的前 16 位
        key = encrypted_data[:16].encode('utf-8')
        content = encrypted_data[16:]
        content_bytes = base64.b64decode(content)
        
        cipher = AES.new(key, AES.MODE_ECB)
        decrypted_bytes = unpad(cipher.decrypt(content_bytes), AES.block_size)
        return decrypted_bytes.decode('utf-8')
    except Exception:
        return "{}"

def get_meal_type(hour: int) -> str:
    """根据小时数判断用餐时段。"""
    if 5 <= hour < 10:
        return '早餐 🥛'
    elif 10 <= hour < 16:
        return '午餐 🍖'
    elif 16 <= hour < 21:
        return '晚餐 🍎'
    else:
        return '夜宵 🌙'

def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """在 DataFrame 中查找存在的列名（处理 API 字段名变更）。"""
    for col in candidates:
        if col in df.columns:
            return col
    return None


# ==========================================
# 🚀 主程序逻辑
# ==========================================

def main():
    # 1. 主题初始化检查
    just_created = ensure_light_theme()
    st.set_page_config(page_title="贤狼的账本", page_icon="🐺", layout="wide")

    if just_created:
        st.warning("⚠️ 第一次运行检测：已生成颜色配置文件。")
        st.error("👉 请按 Ctrl+C 停止程序并重新运行，以确保最佳视觉体验。")
        st.stop()

    st.markdown(SPICE_THEME_CSS, unsafe_allow_html=True)

    # 2. 侧边栏：输入与设置
    with st.sidebar:
        st.header("🌾 商行登记")
        # st.info("💡 赫萝提示：本账本现已启用【智能审计】，自动剔除充值记录，保留真实消费。")
        
        idserial = st.text_input("商人编号 (学号)", help="请输入您的学号").strip()
        servicehall = st.text_input("通关文牒 (ServiceHall)", type="password", help="请从 userselftrade 请求的 Cookie 中获取").strip()
        
        st.markdown("---")
        st.header("📅 核算周期")
        today = datetime.date.today()
        # 默认设置为当前年份
        default_start = datetime.date(today.year, 1, 1)
        default_end = datetime.date(today.year, 12, 31)
        
        start_date = st.date_input("起始", default_start)
        end_date = st.date_input("终止", default_end)
        
        run_btn = st.button("开始核算账目 💰")

    # 3. 主界面标题
    st.title("🌾 贤狼赫萝的年度干饭账本")

    # 4. 业务处理
    if run_btn:
        if not idserial or not servicehall:
            st.warning("⚠️ 请完整输入 学号 和 通关文牒 (ServiceHall)")
            st.stop()

        with st.spinner('赫萝正在仔细核对每一笔金币...'):
            # 构造请求
            api_url = f"https://card.tsinghua.edu.cn/business/querySelfTradeList?pageNumber=0&pageSize=5000&starttime={start_date}&endtime={end_date}&idserial={idserial}&tradetype=-1"
            cookie = {"servicehall": servicehall}
            
            try:
                response = requests.post(api_url, cookies=cookie)
                response.raise_for_status()
                
                # 尝试解析 JSON
                try:
                    res_json = json.loads(response.text)
                except json.JSONDecodeError:
                    st.error("API 响应格式错误，请检查网络连接或 ServiceHall 是否过期。")
                    st.stop()
                
                # 检查 API 返回状态
                if "data" not in res_json or not res_json["data"]:
                    msg = res_json.get('msg', '无错误信息')
                    st.warning(f"账本为空 (API Msg: {msg})。请确认 ServiceHall 是否有效。")
                    st.stop()

                # 解密数据
                encrypted_str = res_json["data"]
                decrypted_str = decrypt_aes_ecb(encrypted_str)
                raw_data = json.loads(decrypted_str)
                
                if "resultData" in raw_data and "rows" in raw_data["resultData"]:
                    df = pd.DataFrame(raw_data["resultData"]["rows"])
                    
                    # 4.1 数据预处理
                    time_col = find_column(df, ['txdate', 'occtime', 'consmtime', 'transtime', 'opdt', 'regdate'])
                    if not time_col:
                        st.error(f"❌ 无法识别时间字段。现有字段: {list(df.columns)}")
                        st.stop()
                    
                    # 类型转换
                    df['datetime'] = pd.to_datetime(df[time_col])
                    df['month'] = df['datetime'].dt.strftime('%Y-%m') 
                    df['hour'] = df['datetime'].dt.hour
                    df['meal'] = df['hour'].apply(get_meal_type)
                    df['txamt'] = df['txamt'] / 100 
                    df['mername'] = df['mername'].astype(str)

                    # 4.2 智能过滤逻辑
                    # 优先使用交易类型字段
                    type_col = find_column(df, ['txname', 'trandescname', 'trantype'])
                    
                    if type_col:
                        mask_type = df[type_col].astype(str).str.contains('消费|扣款', case=False, na=False)
                        mask_not_recharge = ~df[type_col].astype(str).str.contains('充值|圈存|补助|发卡', case=False, na=False)
                        df_step1 = df[mask_type & mask_not_recharge]
                    else:
                        df_step1 = df

                    # 使用关键词黑名单过滤商户名
                    mask_clean_mer = ~df_step1['mername'].str.contains('|'.join(BLACKLIST_KEYWORDS), case=False)
                    # 确保金额大于0
                    mask_positive = df_step1['txamt'] > 0
                    
                    # 获取最终消费数据
                    df_exp = df_step1[mask_clean_mer & mask_positive].copy()
                    
                    if df_exp.empty:
                        st.warning("😱 剔除充值记录后，未发现消费记录。")
                        st.stop()

                    # 4.3 核心指标展示
                    total_spent = df_exp['txamt'].sum()
                    total_count = len(df_exp)
                    top_place = df_exp.groupby('mername')['txamt'].sum().idxmax()
                    max_single = df_exp['txamt'].max()

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("💰 年度总消费", f"¥{total_spent:,.2f}")
                    col2.metric("🐺 进食次数", f"{total_count} 次")
                    col3.metric("🏆 最爱去的食堂", top_place)
                    col4.metric("🍎 单次最高消费", f"¥{max_single}")
                    
                    st.divider()

                    # 4.4 可视化图表
                    c1, c2 = st.columns([2, 1])
                    
                    # 趋势图
                    with c1:
                        st.subheader("📈 消费趋势")
                        monthly_trend = df_exp.groupby('month')['txamt'].sum().reset_index()
                        fig_line = px.line(
                            monthly_trend, x='month', y='txamt', markers=True, 
                            template="plotly_white",
                            color_discrete_sequence=['#bf360c']
                        )
                        fig_line.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            font=DARK_FONT_STYLE,
                            xaxis_title="", yaxis_title="金币 (元)"
                        )
                        st.plotly_chart(fig_line, use_container_width=True)
                    
                    # 饼图
                    with c2:
                        st.subheader("🍽️ 饮食习惯")
                        meal_dist = df_exp.groupby('meal')['txamt'].sum().reset_index()
                        fig_pie = px.pie(
                            meal_dist, values='txamt', names='meal', 
                            template="plotly_white",
                            color_discrete_sequence=['#ffca28', '#ef6c00', '#8d6e63', '#33691e'],
                            hole=0.4
                        )
                        fig_pie.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            font=DARK_FONT_STYLE,
                            showlegend=False,
                            margin=dict(t=0, b=0, l=0, r=0)
                        )
                        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig_pie, use_container_width=True)

                    # 条形图
                    st.subheader("🏦 消费地点排行 (Top 15)")
                    place_rank = df_exp.groupby('mername')['txamt'].sum().reset_index().sort_values('txamt', ascending=False).head(15)
                    fig_bar = px.bar(
                        place_rank, x='txamt', y='mername', orientation='h', 
                        text_auto='.0f',
                        template="plotly_white",
                        color='txamt', color_continuous_scale='Oranges'
                    )
                    fig_bar.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font=DARK_FONT_STYLE,
                        yaxis=dict(categoryorder='total ascending', title="", tickfont=dict(color='#3e2723')), 
                        xaxis=dict(title="消费总额 (元)", tickfont=dict(color='#3e2723')), 
                        coloraxis_showscale=False
                    )
                    fig_bar.update_traces(textposition='outside', textfont_color='#3e2723')
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # 4.5 详细数据表
                    st.divider()
                    st.subheader("📜 详细交易卷轴")
                    
                    cols = ['datetime', 'mername', 'txamt', 'meal']
                    if type_col:
                        cols.append(type_col)
                    
                    df_display = df_exp[cols].sort_values('datetime', ascending=False).copy()
                    
                    st.data_editor(
                        df_display,
                        column_config={
                            "datetime": st.column_config.DatetimeColumn("时间", format="MM-DD HH:mm"),
                            "mername": st.column_config.TextColumn("商铺", width="large"),
                            "txamt": st.column_config.ProgressColumn(
                                "金额", format="¥%.2f", min_value=0, max_value=float(max_single),
                            ),
                            "meal": st.column_config.TextColumn("时段"),
                            type_col: st.column_config.TextColumn("类型") if type_col else None
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )

            except Exception as e:
                st.error(f"赫萝遇到了无法处理的异常：{str(e)}")
    else:
        # 欢迎页状态
        st.markdown("""
        <div style="text-align: center; margin-top: 50px;">
            <h1 style="color: #3e2723;">🍎 欢迎回来，旅行商人</h1>
            <p style="font-size: 1.2rem; color: #5d4037;">在左侧登记商行信息，开始核算您的年度账目。</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()