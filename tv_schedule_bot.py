import os
import urllib.request
import urllib.parse
import json
import datetime
import time

# ⚙️ 設定情報（GitHub Secrets から取得）
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
MESSAGE_SIZE_LIMIT = 1900  # Discordの文字数制限に合わせた安全な分割サイズ

# 対象のチャンネルID（地デジ7局 + BS無料各局 + BSJ:COM）
TARGET_CHANNELS = [
    # --- 福岡地上波 ---
    "2_56336_31874", "2_56328_31873", "2_56320_31872", "2_56344_31875",
    "2_56352_31876", "2_56360_31877", "2_56368_31878",
    
    # --- BS無料局・NHK・BSJ:COM ---
    "3_101_4",   # NHK BS
    "3_103_4",   # NHK BSプレミアム4K
    "3_141_4",   # BS日テレ
    "3_151_4",   # BS朝日
    "3_161_4",   # BS-TBS
    "3_171_4",   # BSテレ東
    "3_181_4",   # BSフジ
    "3_200_4",   # BS10 (旧スターチャンネル)
    "3_211_4",   # BS11
    "3_222_4",   # BS12
    "3_260_4"    # BSJ:COM
]

# 🎯 抽出ジャンル
TARGET_GENRES = {
    "3": "ドラマ",
    "6": "映画",
    "7": "アニメ"
}

# ❌ 除外キーワード
IGNORE_KEYWORDS = [
    "韓ドラ",
    "韓国ドラマ",
    "中国ドラマ",
    "韓国時代劇",
    "中国時代劇",
    "韓国◇",
    "中国◇",
    "連続テレビ小説"
]

def get_tv_schedule(target_date):
    """指定された日付（datetime.date型）の厳選番組表を文字列で返す"""
    date_str = target_date.strftime("%Y%m%d")
    channels_with_date = [f"{ch}_{date_str}" for ch in TARGET_CHANNELS]
    channels_param = ",".join(channels_with_date)
    
    base_url = "https://tvguide.myjcom.jp/api/getEpgInfo/"
    params = {"channels": channels_param, "rectime": "", "rec4k": ""}
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    max_retries = 4
    retry_interval = 30
    data = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"📡 APIにリクエスト送信中... (日付: {date_str}) [{attempt}/{max_retries}回目]")
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                print("  ✅ APIデータ取得完了")
                break
        except Exception as e:
            print(f"  ⚠️ APIエラーが発生しました: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_interval}秒後にリトライします...")
                time.sleep(retry_interval)
            else:
                print("  ❌ 最大リトライ回数を超えました。")
                return f"❌ データ取得エラー (最大リトライ失敗): {e}\n"

    result_str = ""
    start_target = datetime.datetime.combine(target_date, datetime.time.min)
    end_target = datetime.datetime.combine(target_date, datetime.time.max)
    
    for ch_key in channels_with_date:
        programs = data.get(ch_key)
        if not programs or not isinstance(programs, list):
            continue
        
        channel_name = programs[0].get('channelName', '不明なチャンネル')
        printed_channel_header = False
        
        for prog in programs:
            genre_code = str(prog.get('sortGenre', ''))
            genre_main = genre_code[0] if len(genre_code) == 2 else (genre_code[:2] if len(genre_code) == 3 else "")
            
            if genre_main not in TARGET_GENRES:
                continue
                
            genre_label = TARGET_GENRES[genre_main]
            title = prog.get('title', 'タイトルなし')
            
            if any(kwd in title for kwd in IGNORE_KEYWORDS):
                continue
            
            p_start_raw = prog.get('programStart')
            p_end_raw = prog.get('programEnd')
            if not p_start_raw or not p_end_raw:
                continue
                
            try:
                prog_start = datetime.datetime.strptime(str(p_start_raw), "%Y%m%d%H%M%S")
                prog_end = datetime.datetime.strptime(str(p_end_raw), "%Y%m%d%H%M%S")
            except Exception:
                continue
            
            if (prog_end - prog_start).total_seconds() < 3600:
                continue
            
            if prog_start <= end_target and prog_end >= start_target:
                if not printed_channel_header:
                    result_str += f"\n📺 【{channel_name}】\n"
                    printed_channel_header = True
                    
                start_str = prog_start.strftime("%H:%M")
                end_str = prog_end.strftime("%H:%M")
                result_str += f"  [{genre_label}] {start_str} - {end_str} : {title}\n"
                
    return result_str

def post_discord(long_message: str):
    """Discordへ文字数制限を考慮して安全に分割送信する"""
    if not WEBHOOK_URL:
        print("⚠️ 錯誤: DISCORD_WEBHOOK_URL が設定されていません。")
        return

    if not long_message.strip():
        return

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (private use) Python-urllib/3.10",
    }

    message_length = len(long_message)
    i = 0
    while message_length > 0:
        buf = long_message[MESSAGE_SIZE_LIMIT * i : MESSAGE_SIZE_LIMIT * (i + 1)]
        i += 1
        message_length -= MESSAGE_SIZE_LIMIT

        data = {"content": buf}
        request = urllib.request.Request(
            WEBHOOK_URL,
            data=json.dumps(data).encode(),
            headers=headers,
        )

        try:
            with urllib.request.urlopen(request) as res:
                assert res.getcode() == 204
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Discord送信エラー: {e}")

def main():
    print("🚀 番組表自動取得ジョブを開始します...")
    now = datetime.datetime.now()
    
    # 1. 今日の番組表を取得
    today_date = now.date()
    today_title = f"━━━━━━━━━━━━━━━━━━━━━━━━━\n📅 今日 {today_date.strftime('%Y/%m/%d')} の厳選番組表\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    today_schedule = get_tv_schedule(today_date)
    
    # 2. 明日の番組表を取得
    tomorrow_date = today_date + datetime.timedelta(days=1)
    tomorrow_title = f"━━━━━━━━━━━━━━━━━━━━━━━━━\n📅 明日 {tomorrow_date.strftime('%Y/%m/%d')} の厳選番組表\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    tomorrow_schedule = get_tv_schedule(tomorrow_date)
    
    # 3. メッセージを結合して送信
    full_message = today_title + (today_schedule if today_schedule.strip() else "  (対象番組はありませんでした)\n")
    full_message += "\n" + tomorrow_title + (tomorrow_schedule if tomorrow_schedule.strip() else "  (対象番組はありませんでした)\n")
    
    post_discord(full_message)
    print("📬 Discordへの処理が完了しました。")

if __name__ == "__main__":
    main()