import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- Google Sheets 読み込み設定 ---
SPREADSHEET_URL = st.secrets['sheet_url']
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
worksheet = sh.sheet1
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# --- データ前処理 ---
# 日付を日付型に変換（時間部分を削除）
df["日付"] = pd.to_datetime(df["日付"]).dt.date

# win_flag 列が存在しない場合は、勝敗列から作成（勝ち=1, 負け=0）
if "win_flag" not in df.columns and "勝敗" in df.columns:
    df["win_flag"] = df["勝敗"].map({"勝ち": 1, "負け": 0})

# 勝敗表示用の列（数値を文字列に変換）
df["勝敗表記"] = df["win_flag"].map({1: "勝ち", 0: "負け"})

# 編集用URL をハイパーリンク化
if "編集用URL" in df.columns:
    df["編集リンク"] = df["編集用URL"].apply(lambda x: f'<a href="{x}" target="_blank">編集</a>')

# -------------------------------------
# サイドバー: フィルタリング機能
# -------------------------------------
st.sidebar.title("フィルター設定")

# 1. 日付レンジ選択
def_min_date = df["日付"].min()
def_max_date = df["日付"].max()
date_range = st.sidebar.date_input("日付範囲", [def_min_date, def_max_date], key="date_range")
df = df[(df["日付"] >= date_range[0]) & (df["日付"] <= date_range[1])]

# 2. イベント名選択
if "イベント名" in df.columns:
    event_options = ["All"] + sorted(df["イベント名"].dropna().unique())
    selected_event = st.sidebar.selectbox("イベント名", event_options, key="event_select")
    if selected_event != "All":
        df = df[df["イベント名"] == selected_event]
else:
    selected_event = "All"

# 3. 氏名選択
player_options = ["All"] + sorted(df["氏名"].dropna().unique())
selected_player = st.sidebar.selectbox("氏名選択", player_options, key="player_select")
if selected_player != "All":
    df = df[df["氏名"] == selected_player]

# 4. デッキ選択 (使用または相手を対象, "All"対応)
deck_options = ["All"] + sorted(df["使用デッキ"].dropna().unique())
selected_deck = st.sidebar.selectbox("デッキ選択", deck_options, key="deck_select")

# 5. 相手デッキ選択 (使用または相手を対象, "All"対応)
opponent_deck_options = ["All"] + sorted(df["相手デッキ"].dropna().unique())
selected_opponent_deck = st.sidebar.selectbox("相手のデッキ", opponent_deck_options, key="opp_deck_select")

# 6. 先攻/後攻 フィルタ
hand_options = ["All"] + sorted(df["先手後手"].dropna().unique())
selected_hand = st.sidebar.selectbox("先手/後攻", hand_options, key="hand_select")
if selected_hand != "All":
    df = df[df["先手後手"] == selected_hand]

# 7. 環境選択フィルタ
env_options = ["All"] + sorted(df["環境"].dropna().unique())
selected_env = st.sidebar.selectbox("環境選択", env_options, key="env_select")
if selected_env != "All":
    df = df[df["環境"] == selected_env]

# 8. メモ検索
if "メモ" in df.columns:
    memo_query = st.sidebar.text_input("メモ検索", key="memo_search")
    if memo_query:
        df = df[df["メモ"].str.contains(memo_query, case=False, na=False)]
else:
    memo_query = ""

# デッキフィルタロジック（氏名選択時優先）
if selected_player != "All" and selected_deck != "All":
    df = df[(df["氏名"] == selected_player) & (df["使用デッキ"] == selected_deck)]
elif selected_deck != "All" and selected_opponent_deck != "All" and selected_deck == selected_opponent_deck:
    df = df[(df["使用デッキ"] == selected_deck) & (df["相手デッキ"] == selected_deck)]
elif selected_deck != "All":
    df = df[(df["使用デッキ"] == selected_deck) | (df["相手デッキ"] == selected_deck)]
elif selected_opponent_deck != "All":
    df = df[(df["相手デッキ"] == selected_opponent_deck) | (df["使用デッキ"] == selected_opponent_deck)]

# -------------------------------------
# メイン: グラフ・テーブル表示
# -------------------------------------
st.title("TCG 対戦データ分析ダッシュボード")

# 勝率円グラフ（全体）
st.subheader("勝率円グラフ")
if df.empty:
    st.info("該当データがありません。")
else:
    overall_counts = df["win_flag"].value_counts()
    labels = ["勝ち", "負け"]
    values = [overall_counts.get(1, 0), overall_counts.get(0, 0)]
    fig_overall = go.Figure(data=[
        go.Pie(labels=labels, values=values, hole=0.4, textinfo='label+percent')
    ])
    st.plotly_chart(fig_overall, use_container_width=True, key="overall_chart")

st.markdown("---")

# 環境別勝率と相手デッキ別勝率（数値追加）
col1, col2 = st.columns(2)

# 環境別勝率
with col1:
    st.subheader("環境別勝率")
    if df.empty:
        st.write("該当データなし")
    else:
        group_env = df.groupby("環境")["win_flag"].mean().reset_index()
        group_env["勝率"] = group_env["win_flag"].map(lambda x: f"{x:.1%}")
        fig_env = go.Figure(
            data=[
                go.Bar(x=group_env["環境"], y=group_env["win_flag"], text=group_env["勝率"], textposition='auto', marker_color="#2196F3")
            ]
        )
        fig_env.update_layout(yaxis=dict(range=[0,1], tickformat=".0%"), xaxis_tickangle=-45)
        st.plotly_chart(fig_env, use_container_width=True, key="env_chart")

# 相手デッキ別勝率
with col2:
    st.subheader("相手デッキ別勝率")
    if df.empty:
        st.write("該当データなし")
    else:
        group_vs = df.groupby("相手デッキ")["win_flag"].mean().reset_index()
        group_vs["勝率"] = group_vs["win_flag"].map(lambda x: f"{x:.1%}")
        fig_vs = go.Figure(
            data=[
                go.Bar(x=group_vs["相手デッキ"], y=group_vs["win_flag"], text=group_vs["勝率"], textposition='auto', marker_color="#FFC107")
            ]
        )
        fig_vs.update_layout(yaxis=dict(range=[0,1], tickformat=".0%"), xaxis_tickangle=-45)
        st.plotly_chart(fig_vs, use_container_width=True, key="opp_chart")

st.markdown("---")

# 詳細テーブル表示
st.subheader("フィルタ結果: 詳細テーブル")
if df.empty:
    st.info("フィルタ条件に該当するデータがありません。")
else:
    display_cols = ["編集リンク", "日付", "イベント名", "氏名", "使用デッキ", "先手後手", "相手デッキ", "相手プレイヤ", "勝敗表記", "環境", "メモ"]
    # 「編集リンク」がない場合は元の編集用URLを表示
    if "編集リンク" not in df.columns:
        display_cols[0] = "編集用URL"
    html_table = df[display_cols].to_html(index=False, escape=False)
    st.markdown(html_table, unsafe_allow_html=True)

st.markdown("---")
st.caption("※ このダッシュボードは閲覧専用リンクで共有可能です。フィルタ操作やグラフ閲覧は誰でもできますが、スプレッドシート本体の編集はできません。")
