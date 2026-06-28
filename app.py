import streamlit as st
import sqlite3
import pandas as pd
import datetime
import random
import string
import smtplib
from email.mime.text import MIMEText
import urllib.request
import urllib.parse
import re
import time
from youtubesearchpython import VideosSearch
import os

# ページ設定
st.set_page_config(page_title="DJ Request App", page_icon="🎵", layout="centered")

# CSSでStreamlit特有のUIを隠す
hide_st_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stApp [data-testid="stHeader"] {
    display: none;
}
/* モバイル対応など、全体的にパディングを調整 */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

DB_FILE = "requests.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle_name TEXT,
            song_name TEXT,
            artist_name TEXT,
            comment TEXT,
            youtube_url TEXT,
            status TEXT,
            created_at TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS ng_words (
            word TEXT PRIMARY KEY
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin_auth (
            date TEXT PRIMARY KEY,
            full_password TEXT,
            pin_code TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_today_str():
    # 日本時間などを考慮してシステム時間を取得
    return datetime.datetime.now().strftime("%Y-%m-%d")

def generate_daily_password():
    today = get_today_str()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT pin_code, full_password FROM admin_auth WHERE date = ?", (today,))
    row = c.fetchone()
    
    if row:
        pin, full_pass = row
        conn.close()
        return pin, full_pass
    
    # 未生成の場合は新しく生成
    pin = f"{random.randint(0, 9999):04d}"
    chars = ''.join(random.choices(string.ascii_letters, k=6))
    full_pass = pin + chars
    
    c.execute("INSERT INTO admin_auth (date, full_password, pin_code) VALUES (?, ?, ?)", (today, full_pass, pin))
    conn.commit()
    conn.close()
    
    # メール送信（Secretsが設定されていれば）
    try:
        if "email" in st.secrets:
            email_user = st.secrets["email"]["user"]
            email_pass = st.secrets["email"]["password"]
            email_to = st.secrets["email"].get("to", email_user) # 宛先が指定されていればそれを使用、なければ送信元と同じ
            
            if email_user and email_pass:
                msg = MIMEText(f"本日のDJパネル用PINコードは {pin} です。\n(フルパスワード: {full_pass})")
                msg['Subject'] = f"【DJ Request App】本日のPINコード ({today})"
                msg['From'] = email_user
                msg['To'] = email_to
                
                server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                server.login(email_user, email_pass)
                server.send_message(msg)
                server.quit()
    except Exception as e:
        # Secretsエラーなどはアプリをクラッシュさせない
        pass
    
    return pin, full_pass

def check_ng_words(text):
    if not text:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT word FROM ng_words")
    words = [row[0] for row in c.fetchall()]
    conn.close()
    for w in words:
        if w in text:
            return True
    return False

def search_youtube(query):
    try:
        videosSearch = VideosSearch(query, limit = 1)
        result = videosSearch.result()
        if result and len(result['result']) > 0:
            return result['result'][0]['link']
    except:
        pass
    
    # フォールバック (urllib)
    try:
        query_string = urllib.parse.urlencode({"search_query": query})
        html = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        if video_ids:
            return f"https://www.youtube.com/watch?v={video_ids[0]}"
    except:
        pass
    
    return ""

def main():
    init_db()
    pin, _ = generate_daily_password()
    
    st.title("🎵 DJ Song Request")
    st.write("聴きたい曲をリクエストしよう！")
    
    # --- ユーザー画面（リクエストフォーム） ---
    with st.form("request_form"):
        handle_name = st.text_input("ハンドルネーム（必須）", max_chars=50)
        song_name = st.text_input("曲名（必須）", max_chars=100)
        artist_name = st.text_input("アーティスト名（任意）", max_chars=100)
        comment = st.text_area("コメント（任意・120文字以内）", max_chars=120)
        
        submitted = st.form_submit_button("リクエストを送信")
        
        if submitted:
            if not handle_name or not song_name:
                st.error("ハンドルネームと曲名は必須です。")
            else:
                combined_text = f"{handle_name} {song_name} {artist_name} {comment}"
                if check_ng_words(combined_text):
                    st.error("入力内容に不適切な単語が含まれているため送信できません。")
                else:
                    with st.spinner("検索中..."):
                        search_q = f"{song_name} {artist_name}".strip()
                        yt_url = search_youtube(search_q)
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO requests (handle_name, song_name, artist_name, comment, youtube_url, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (handle_name, song_name, artist_name, comment, yt_url, 'new', datetime.datetime.now()))
                        conn.commit()
                        conn.close()
                    
                    st.success("リクエストを送信しました！")

    # --- 管理者エリア (URLに ?admin=777 がある場合のみ表示) ---
    query_params = st.query_params
    if query_params.get("admin") == "777":
        st.write("---")
        with st.expander("DJ Login", expanded=False):
            if "admin_logged_in" not in st.session_state:
                st.session_state.admin_logged_in = False
            if "lockout_time" not in st.session_state:
                st.session_state.lockout_time = 0
            if "attempts" not in st.session_state:
                st.session_state.attempts = 0
            
            # ロックアウト判定
            current_time = time.time()
            if st.session_state.lockout_time > current_time:
                remain = int(st.session_state.lockout_time - current_time)
                st.error(f"ロックアウト中です。あと {remain} 秒お待ちください。")
            elif st.session_state.admin_logged_in:
                # ログイン成功時のダッシュボード
                st.success("DJ Panelにログインしています。")
                if st.button("ログアウト"):
                    st.session_state.admin_logged_in = False
                    st.rerun()
                
                st.header("💿 DJ Dashboard")
                
                # タブで機能分割
                tab1, tab2, tab3 = st.tabs(["リクエスト一覧", "NGワード設定", "ダウンロード"])
                
                with tab1:
                    conn = sqlite3.connect(DB_FILE)
                    df = pd.read_sql_query("SELECT id, handle_name, song_name, artist_name, comment, status, youtube_url, created_at FROM requests ORDER BY id DESC", conn)
                    conn.close()
                    
                    st.subheader("未再生リクエスト")
                    new_df = df[df["status"] == "new"]
                    for idx, row in new_df.iterrows():
                        with st.container():
                            st.markdown(f"**{row['song_name']}** / {row['artist_name']} (Req: {row['handle_name']})")
                            st.write(f"💬 {row['comment']}")
                            if row['youtube_url']:
                                with st.expander("YouTubeで試聴"):
                                    st.video(row['youtube_url'])
                            else:
                                st.write("YouTubeのURLが見つかりませんでした。")
                            
                            if st.button("再生済みにする", key=f"btn_play_{row['id']}"):
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("UPDATE requests SET status = 'played' WHERE id = ?", (row['id'],))
                                conn.commit()
                                conn.close()
                                st.rerun()
                        st.write("---")
                    
                    st.subheader("再生済みリスト")
                    played_df = df[df["status"] == "played"]
                    st.dataframe(played_df[["id", "song_name", "artist_name", "handle_name", "created_at"]], use_container_width=True)

                with tab2:
                    st.subheader("NGワード設定")
                    with st.form("ng_word_form"):
                        new_ng_word = st.text_input("追加するNGワード")
                        submit_ng = st.form_submit_button("追加")
                        if submit_ng and new_ng_word:
                            conn = sqlite3.connect(DB_FILE)
                            try:
                                conn.execute("INSERT INTO ng_words (word) VALUES (?)", (new_ng_word,))
                                conn.commit()
                                st.success("追加しました")
                            except sqlite3.IntegrityError:
                                st.warning("すでに登録されています")
                            conn.close()
                            st.rerun()
                            
                    conn = sqlite3.connect(DB_FILE)
                    ng_df = pd.read_sql_query("SELECT word FROM ng_words", conn)
                    conn.close()
                    
                    if not ng_df.empty:
                        for idx, row in ng_df.iterrows():
                            col1, col2 = st.columns([3, 1])
                            col1.write(row['word'])
                            if col2.button("削除", key=f"del_ng_{idx}"):
                                conn = sqlite3.connect(DB_FILE)
                                conn.execute("DELETE FROM ng_words WHERE word = ?", (row['word'],))
                                conn.commit()
                                conn.close()
                                st.rerun()

                with tab3:
                    st.subheader("データとマニュアルのダウンロード")
                    
                    # CSVダウンロード
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    today_csv = datetime.datetime.now().strftime("%Y%m%d")
                    st.download_button(
                        label="履歴CSVをダウンロード",
                        data=csv,
                        file_name=f"{today_csv}REQ.csv",
                        mime="text/csv",
                    )
                    
                    # マニュアルダウンロード
                    manual_path = "DJリクエストシステム_マニュアル.txt"
                    if os.path.exists(manual_path):
                        with open(manual_path, "rb") as f:
                            manual_data = f.read()
                        st.download_button(
                            label="マニュアルをダウンロード",
                            data=manual_data,
                            file_name="DJリクエストシステム_マニュアル.txt",
                            mime="text/plain",
                        )
                    else:
                        st.write("マニュアルファイルが見つかりません。")
                        
            else:
                # PINコード入力フォーム
                input_pin = st.text_input("PINコードを入力してください", type="password")
                if st.button("ログイン"):
                    if input_pin == pin:
                        st.session_state.admin_logged_in = True
                        st.session_state.attempts = 0
                        st.rerun()
                    else:
                        st.session_state.attempts += 1
                        left = 3 - st.session_state.attempts
                        if left > 0:
                            st.error(f"PINコードが間違っています。残り {left} 回でロックされます。")
                        else:
                            st.session_state.lockout_time = time.time() + 60
                            st.session_state.attempts = 0
                            st.error("3回間違えました。1分間ロックアウトします。")
                            st.rerun()

if __name__ == "__main__":
    main()
