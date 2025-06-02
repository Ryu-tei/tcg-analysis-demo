import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# -----------------------------------------
# 1. Google Sheets 読み込み設定（シークレット利用）
# -----------------------------------------
SPREADSHEET_URL = st.secrets["sheet_url"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
worksheet = sh.sheet1

# -----------------------------------------
# 2. 既存データから「候補リスト」を取得
# -----------------------------------------
existing_data = pd.DataFrame(worksheet.get_all_records())

def get_unique_list(df, col_name):
    if col_name in df.columns:
        return sorted(df[col_name].dropna().unique().tolist())
    else:
        return []

name_list     = get_unique_list(existing_data, "氏名")
own_deck_list = get_unique_list(existing_data, "使用デッキ")
opp_deck_list = get_unique_list(existing_data, "相手デッキ")
env_list      = get_unique_list(existing_data, "環境")
event_list    = get_unique_list(existing_data, "イベント名")

# ひらがな変換ヘルパー

def katakana_to_hiragana(s: str) -> str:
    result = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return "".join(result)

def build_display_options(candidates: list[str]) -> list[str]:
    display = []
    for orig in candidates:
        hira = katakana_to_hiragana(orig)
        if hira and hira != orig:
            display.append(f"{orig} ({hira})")
        else:
            display.append(orig)
    return display

name_display     = build_display_options(name_list)
own_deck_display = build_display_options(own_deck_list)
opp_deck_display = build_display_options(opp_deck_list)
env_display      = build_display_options(env_list)
event_display    = build_display_options(event_list)

# -----------------------------------------
# 3. Streamlit フォーム描画
# -----------------------------------------
st.title("TCG 対戦データ 追加フォーム")

with st.form(key="add_match_form"):
    # (1) 日付
    match_date = st.date_input(
        "日付",
        value=datetime.today().date(),
        key="match_date"
    )

    # (2) イベント名: 新規入力 or 候補選択
    event_input = st.text_input(
        "イベント名（新規入力）",
        placeholder="必要なら新規イベント名を入力",
        key="event_input"
    )
    selected_event = st.selectbox(
        label="イベント名（候補から選択）",
        options=[""] + event_display,
        index=0,
        key="event_selectbox"
    )
    event_name = selected_event.split(" (")[0] if selected_event else event_input

    # (3) 氏名: 新規入力 or 候補選択
    player_input = st.text_input(
        "氏名（新規入力）",
        placeholder="新規に氏名を入力",
        key="player_input"
    )
    selected_player = st.selectbox(
        label="氏名（候補から選択）",
        options=[""] + name_display,
        index=0,
        key="player_selectbox"
    )
    player_name = selected_player.split(" (")[0] if selected_player else player_input

    # (4) 使用デッキ: 新規入力 or 候補選択
    own_deck_input = st.text_input(
        "使用デッキ（新規入力）",
        placeholder="新規にデッキ名を入力",
        key="own_deck_input"
    )
    selected_own_deck = st.selectbox(
        label="使用デッキ（候補から選択）",
        options=[""] + own_deck_display,
        index=0,
        key="own_deck_selectbox"
    )
    own_deck = selected_own_deck.split(" (")[0] if selected_own_deck else own_deck_input

    # (5) 先手/後攻 (ラジオボタン)
    turn_order = st.radio(
        "先手 / 後攻",
        options=["先攻", "後攻"],
        index=0,
        key="turn_order"
    )

    # (6) 相手デッキ: 新規入力 or 候補選択
    opp_deck_input = st.text_input(
        "相手デッキ（新規入力）",
        placeholder="新規に相手デッキ名を入力",
        key="opp_deck_input"
    )
    selected_opp_deck = st.selectbox(
        label="相手デッキ（候補から選択）",
        options=[""] + opp_deck_display,
        index=0,
        key="opp_deck_selectbox"
    )
    opp_deck = selected_opp_deck.split(" (")[0] if selected_opp_deck else opp_deck_input

    # (7) 相手プレイヤ: 新規入力 or 候補選択 (氏名候補再利用)
    opp_player_input = st.text_input(
        "相手プレイヤ（新規入力）",
        placeholder="新規に相手プレイヤを入力",
        key="opp_player_input"
    )
    selected_opp_player = st.selectbox(
        label="相手プレイヤ（候補から選択）",
        options=[""] + name_display,
        index=0,
        key="opp_player_selectbox"
    )
    opp_player = selected_opp_player.split(" (")[0] if selected_opp_player else opp_player_input

    # (8) 勝敗 (ラジオボタン)
    result = st.radio(
        "勝敗",
        options=["勝ち", "負け"],
        index=0,
        key="result"
    )

    # (9) 環境: 新規入力 or 候補選択
    env_input = st.text_input(
        "環境（新規入力）",
        placeholder="新規に環境を入力",
        key="env_input"
    )
    selected_env = st.selectbox(
        label="環境（候補から選択）",
        options=[""] + env_display,
        index=0,
        key="env_selectbox"
    )
    env = selected_env.split(" (")[0] if selected_env else env_input

    # (10) メモ (任意テキスト)
    note = st.text_input(
        "メモ（任意）",
        placeholder="必要があれば入力してください",
        key="note"
    )

    # (11) フォーム送信
    submitted = st.form_submit_button(label="データ追加")

    # ---------------------------------------------------
    # 4. 送信処理: 必須チェック → Google シート追記 → 8秒待機
    # ---------------------------------------------------
    if submitted:
        if not player_name or not own_deck or not opp_deck or not opp_player or not env:
            st.error("「氏名」「使用デッキ」「相手デッキ」「相手プレイヤ」「環境」は必須です。すべて入力してください。")
        else:
            next_row_index = len(existing_data) + 2
            edit_link = f"https://docs.google.com/spreadsheets/d/{sh.id}/edit#gid=0&range=A{next_row_index}"
            new_row = [
                edit_link,
                match_date.strftime("%Y/%m/%d"),
                event_name,
                player_name,
                own_deck,
                turn_order,
                opp_deck,
                opp_player,
                result,
                env,
                note
            ]
            worksheet.append_row(new_row, value_input_option="USER_ENTERED")
            st.success("データをスプレッドシートに追加しました！ 8秒後に次の送信が可能です.")
            time.sleep(8)
