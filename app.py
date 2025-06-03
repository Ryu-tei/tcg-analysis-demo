import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time

# --- Google Sheets 読み込み設定 ---
SPREADSHEET_URL = st.secrets["sheet_url"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
worksheet = sh.sheet1

# --- 既存データ取得 + DataFrame 化 ---
existing_data = pd.DataFrame(worksheet.get_all_records())

# --- データ前処理: 日付変換 + win_flag 作成など ---
df = existing_data.copy()
if "日付" in df.columns:
    df["日付"] = pd.to_datetime(df["日付"]).dt.date
if "win_flag" not in df.columns and "勝敗" in df.columns:
    df["win_flag"] = df["勝敗"].map({"勝ち": 1, "負け": 0})
if "win_flag" in df.columns:
    df["勝敗表記"] = df["win_flag"].map({1: "勝ち", 0: "負け"})
if "編集用URL" in df.columns:
    df["編集リンク"] = df["編集用URL"].apply(
        lambda x: f'<a href="{x}" target="_blank">編集</a>'
    )

# --- 向き無視かつ先攻後攻・勝敗反転を反映した正規化 ---
rows = []
for _, row in df.iterrows():
    name = str(row.get("氏名", ""))
    opp = str(row.get("相手プレイヤ", ""))
    deck = str(row.get("使用デッキ", ""))
    opp_deck = str(row.get("相手デッキ", ""))
    # 順序付け
    if name <= opp:
        rows.append(row)
    else:
        new_row = row.copy()
        new_row["氏名"] = opp
        new_row["相手プレイヤ"] = name
        new_row["使用デッキ"] = opp_deck
        new_row["相手デッキ"] = deck
        if row.get("先手後手") == "先攻":
            new_row["先手後手"] = "後攻"
        elif row.get("先手後手") == "後攻":
            new_row["先手後手"] = "先攻"
        if row.get("win_flag") == 1:
            new_row["win_flag"] = 0
            new_row["勝敗表記"] = "負け"
        elif row.get("win_flag") == 0:
            new_row["win_flag"] = 1
            new_row["勝敗表記"] = "勝ち"
        rows.append(new_row)
normalized_df = pd.DataFrame(rows)

# ペアキー作成して重複除去

def make_pair_key(row):
    date_str = row.get("日付").strftime("%Y%m%d") if pd.notna(row.get("日付")) else ""
    event = row.get("イベント名", "")
    name = row.get("氏名", "")
    opp = row.get("相手プレイヤ", "")
    deck = row.get("使用デッキ", "")
    opp_deck = row.get("相手デッキ", "")
    return f"{date_str}_{event}_{name}_{opp}_{deck}_{opp_deck}"

normalized_df["pair_key"] = normalized_df.apply(make_pair_key, axis=1)
normalized_df = normalized_df.drop_duplicates(subset="pair_key", keep="first").reset_index(drop=True)

df = normalized_df.copy()

# --- サイドバー: データ数表示 & フィルタリング機能 ---
st.sidebar.title("フィルター設定")
# 総データ数表示
total_count = len(df)
st.sidebar.markdown(f"**総データ数**: {total_count} 件")

# 1. 日付レンジ選択
def_min_date = df["日付"].min()
def_max_date = df["日付"].max()
date_range = st.sidebar.date_input(
    "日付範囲", [def_min_date, def_max_date], key="date_range"
)
filtered = df[(df["日付"] >= date_range[0]) & (df["日付"] <= date_range[1])]

# 2. イベント名選択
if "イベント名" in filtered.columns:
    event_options = ["All"] + sorted(filtered["イベント名"].dropna().unique())
    selected_event = st.sidebar.selectbox("イベント名", event_options, key="event_select")
    if selected_event != "All":
        filtered = filtered[filtered["イベント名"] == selected_event]

# 3. 氏名選択 (氏名 or 相手プレイヤ 両方から選択可能)
names = set(filtered.get("氏名", []).dropna().unique()) | set(filtered.get("相手プレイヤ", []).dropna().unique())
player_options = ["All"] + sorted(names)
selected_player = st.sidebar.selectbox("氏名選択", player_options, key="player_select")
if selected_player != "All":
    filtered = filtered[(filtered["氏名"] == selected_player) | (filtered["相手プレイヤ"] == selected_player)]

# 4. デッキ選択
 deck_opts = ["All"] + sorted(filtered["使用デッキ"].dropna().unique())
 selected_deck = st.sidebar.selectbox("デッキ選択", deck_opts, key="deck_select")

# 5. 相手デッキ選択
 opp_deck_opts = ["All"] + sorted(filtered["相手デッキ"].dropna().unique())
 selected_opp_deck = st.sidebar.selectbox("相手のデッキ", opp_deck_opts, key="opp_deck_select")

# 6. 先攻/後攻 フィルタ
hand_options = ["All"] + sorted(filtered["先手後手"].dropna().unique())
selected_hand = st.sidebar.selectbox("先手/後攻", hand_options, key="hand_select")
if selected_hand != "All":
    filtered = filtered[filtered["先手後手"] == selected_hand]

# 7. 勝敗フィルタ
win_options = ["All", "勝ち", "負け"]
selected_win = st.sidebar.selectbox("勝敗", win_options, key="win_select")
if selected_win != "All":
    filtered = filtered[filtered["勝敗表記"] == selected_win]

# 8. 環境選択フィルタ
env_options = ["All"] + sorted(filtered["環境"].dropna().unique())
selected_env = st.sidebar.selectbox("環境選択", env_options, key="env_select")
if selected_env != "All":
    filtered = filtered[filtered["環境"] == selected_env]

# 9. メモ検索
if "メモ" in filtered.columns:
    memo_query = st.sidebar.text_input("メモ検索", key="memo_search")
    if memo_query:
        filtered = filtered[filtered["メモ"].str.contains(memo_query, case=False, na=False)]

# デッキフィルタ：使用 or 相手
df_tmp = filtered
if selected_deck != "All" and selected_opp_deck != "All" and selected_deck == selected_opp_deck:
    filtered = df_tmp[(df_tmp["使用デッキ"] == selected_deck) & (df_tmp["相手デッキ"] == selected_deck)]
elif selected_deck != "All":
    filtered = df_tmp[(df_tmp["使用デッキ"] == selected_deck) | (df_tmp["相手デッキ"] == selected_deck)]
elif selected_opp_deck != "All":
    filtered = df_tmp[(df_tmp["相手デッキ"] == selected_opp_deck) | (df_tmp["使用デッキ"] == selected_opp_deck)]

# --- メイン: グラフ・テーブル表示 ---
st.title("TCG 対戦データ分析ダッシュボード")

# 先攻 vs 後攻 の勝率比較
st.subheader("先攻 / 後攻 勝率比較")
if filtered.empty:
    st.write("該当データなし")
else:
    first_count = len(filtered[filtered["先手後手"] == "先攻"])
    second_count = len(filtered[filtered["先手後手"] == "後攻"])
    first_win = len(filtered[(filtered["先手後手"] == "先攻") & (filtered["win_flag"] == 1)])
    second_win = len(filtered[(filtered["先手後手"] == "後攻") & (filtered["win_flag"] == 1)])
    rates = [first_win / first_count if first_count else 0, second_win / second_count if second_count else 0]
    labels = ["先攻勝率", "後攻勝率"]
    fig_turn = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=rates,
                text=[f"{r:.1%}" for r in rates],
                textposition='auto',
                marker_color=["#4CAF50", "#F44336"]
            )
        ]
    )
    fig_turn.update_layout(
        yaxis=dict(range=[0, 1], tickformat=".0%", tickfont=dict(size=14)),
        xaxis=dict(tickfont=dict(size=14)),
        title_font=dict(size=16)
    )
    st.plotly_chart(fig_turn, use_container_width=True, config={"staticPlot": True})

st.markdown("---")

# 勝敗円グラフ
st.subheader("勝敗円グラフ")
if filtered.empty:
    st.info("該当データがありません。")
else:
    overall_counts = filtered["win_flag"].value_counts()
    labels_pie = ["勝ち", "負け"]
    values_pie = [overall_counts.get(1, 0), overall_counts.get(0, 0)]
    fig_overall = go.Figure(
        data=[
            go.Pie(
                labels=labels_pie,
                values=values_pie,
                hole=0.4,
                textinfo="label+percent"
            )
        ]
    )
    st.plotly_chart(fig_overall, use_container_width=True, key="overall_chart")

st.markdown("---")

# 環境別勝率と相手デッキ別勝率
col1, col2 = st.columns(2)

with col1:
    st.subheader("環境別勝率")
    if filtered.empty:
        st.write("該当データなし")
    else:
        group_env = filtered.groupby("環境")["win_flag"].mean().reset_index()
        group_env["勝率"] = group_env["win_flag"].map(lambda x: f"{x:.1%}")
        fig_env = go.Figure(
            data=[
                go.Bar(
                    x=group_env["環境"],
                    y=group_env["win_flag"],
                    text=group_env["勝率"],
                    textposition="auto",
                    marker_color="#2196F3",
                )
            ]
        )
        fig_env.update_layout(
            yaxis=dict(range=[0, 1], tickformat=".0%", tickfont=dict(size=14)),
            xaxis=dict(tickangle=-45, tickfont=dict(size=14)),
            title_font=dict(size=16),
        )
        st.plotly_chart(fig_env, use_container_width=True, key="env_chart", config={"staticPlot": True})

with col2:
    st.subheader("相手デッキ別勝率")
    if filtered.empty:
        st.write("該当データなし")
    else:
        group_vs = filtered.groupby("相手デッキ")["win_flag"].mean().reset_index()
        group_vs["勝率"] = group_vs["win_flag"].map(lambda x: f"{x:.1%}")
        fig_vs = go.Figure(
            data=[
                go.Bar(
                    x=group_vs["相手デッキ"],
                    y=group_vs["win_flag"],
                    text=group_vs["勝率"],
                    textposition="auto",
                    marker_color="#FFC107",
                )
            ]
        )
        fig_vs.update_layout(
            yaxis=dict(range=[0, 1], tickformat=".0%", tickfont=dict(size=14)),
            xaxis=dict(tickangle=-45, tickfont=dict(size=14)),
            title_font=dict(size=16),
        )
        st.plotly_chart(fig_vs, use_container_width=True, key="opp_chart", config={"staticPlot": True})

st.markdown("---")

# 詳細テーブル表示
st.subheader("フィルタ結果: 詳細テーブル")
if filtered.empty:
    st.info("フィルタ条件に該当するデータがありません。")
else:
    display_cols = [
        "編集リンク", "日付", "イベント名", "氏名", "使用デッキ",
        "先手後手", "相手デッキ", "相手プレイヤ", "勝敗表記", "環境", "メモ"
    ]
    if "編集リンク" not in filtered.columns:
        display_cols[0] = "編集用URL"
    html_table = filtered[display_cols].to_html(index=False, escape=False)
    scroll_container = f"""
    <style>
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            white-space: normal;
            padding: 4px 8px;
            border: 1px solid #ddd;
            text-align: left;
            vertical-align: top;
            max-width: 300px;
            word-break: break-word;
        }}
    </style>
    <div style="max-height:400px; max-width:100%; overflow:auto; border:1px solid #ddd; padding:8px;">
        {html_table}
    </div>
    """
    st.markdown(scroll_container, unsafe_allow_html=True)
    st.caption(
        "※ このダッシュボードは閲覧専用リンクで共有可能です。"
        "フィルタ操作やグラフ閲覧は誰でもできますが、"
        "スプレッドシート本体の編集はできません。"
    )
