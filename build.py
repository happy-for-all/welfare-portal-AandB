import os
import json
import sys
import zipfile
import io
import re
import pandas as pd

# ==========================================
# 👑 福祉ポータル(AandB): 複数サービス横断・自動ビルドエンジン (Ver 1.4.2 決定版)
# 開発者: ちゃろ ＆ AIバディ
# ==========================================

SERVICE_DEFINITIONS = [
    {
        "zip_file": "sfkopendata_202603_45.zip",
        "service_name": "就労継続支援Ａ型",
        "output_key": "shuro_a",
    },
    {
        "zip_file": "sfkopendata_202603_46.zip",
        "service_name": "就労継続支援Ｂ型",
        "output_key": "shuro_b",
    },
    {
        "zip_file": "sfkopendata_202603_65.zip",
        "service_name": "放課後等デイサービス",
        "output_key": "houdei",
    },
]

MUNICIPAL_COORDS = {
    "大阪市": {"lat": 34.6937, "lon": 135.5022},
    "堺市": {"lat": 34.5714, "lon": 135.4807},
    "東大阪市": {"lat": 34.6793, "lon": 135.5999},
    "豊中市": {"lat": 34.7816, "lon": 135.4698},
    "枚方市": {"lat": 34.8162, "lon": 135.6500},
    "吹田市": {"lat": 34.7649, "lon": 135.5140},
    "高槻市": {"lat": 34.8486, "lon": 135.6175},
    "八尾市": {"lat": 34.6293, "lon": 135.6022},
    "寝屋川市": {"lat": 34.7644, "lon": 135.6262},
    "岸和田市": {"lat": 34.4619, "lon": 135.3750},
    "和泉市": {"lat": 34.4883, "lon": 135.4241},
    "守口市": {"lat": 34.7344, "lon": 135.5620},
    "門真市": {"lat": 34.7410, "lon": 135.5911},
    "箕面市": {"lat": 34.8271, "lon": 135.4704},
    "大東市": {"lat": 34.7121, "lon": 135.6224},
    "松原市": {"lat": 34.5772, "lon": 135.5562},
    "富田林市": {"lat": 34.5009, "lon": 135.6019},
    "羽曳野市": {"lat": 34.5583, "lon": 135.6075},
    "河内長野市": {"lat": 34.4536, "lon": 135.5658},
    "池田市": {"lat": 34.8258, "lon": 135.4294},
    "泉佐野市": {"lat": 34.4103, "lon": 135.3262},
    "貝塚市": {"lat": 34.4372, "lon": 135.3589},
    "摂津市": {"lat": 34.7516, "lon": 135.5619},
    "交野市": {"lat": 34.7850, "lon": 135.6811},
    "四條畷市": {"lat": 34.7291, "lon": 135.6413},
    "柏原市": {"lat": 34.5802, "lon": 135.6258},
    "藤井寺市": {"lat": 34.5750, "lon": 135.5969},
    "泉大津市": {"lat": 34.5022, "lon": 135.4058},
    "高石市": {"lat": 34.5219, "lon": 135.4380},
    "大阪狭山市": {"lat": 34.5036, "lon": 135.5519},
    "阪南市": {"lat": 34.3592, "lon": 135.2442},
    "泉南市": {"lat": 34.3725, "lon": 135.2758},
    "フェイルセーフ大阪府庁": {"lat": 34.6862, "lon": 135.5201},
    "フェイルセーフ東京都庁": {"lat": 35.6895, "lon": 139.6917} # 👑 追加
}

def safe_get(row, possible_keys):
    for key in possible_keys:
        if key in row:
            value = str(row[key]).strip()
            if value.lower() == "nan":
                return ""
            return value
    return ""

def run_build():
    print("==========================================")
    print(f"🌸 福祉ポータル(AandB) 複数サービス自動ビルド開始")
    print("==========================================")

    target_dir = os.path.join("dist", "welfare-portal-AandB")
    os.makedirs(target_dir, exist_ok=True)
    
    summary_logs = []

    for srv_def in SERVICE_DEFINITIONS:
        zip_file_path = srv_def["zip_file"]
        service_name = srv_def["service_name"]
        output_key = srv_def["output_key"]
        
        print(f"\n📡 処理開始: 【{service_name}】 (ファイル: {zip_file_path})")

        if not os.path.exists(zip_file_path):
            print(f"⚠️ [警告] 『{zip_file_path}』が見つかりません。スキップします。")
            continue

        try:
            zip_file = zipfile.ZipFile(zip_file_path)
            csv_filename = [f for f in zip_file.namelist() if f.endswith('.csv')][0]
        except Exception as e:
            print(f"❌ ZIP解凍エラー ({service_name}): {e}")
            continue

        df = None
        encodings = ["utf-8-sig", "shift_jis", "cp932", "utf-8"]
        for enc in encodings:
            try:
                with zip_file.open(csv_filename) as f:
                    df = pd.read_csv(f, encoding=enc, dtype=str)
                break
            except Exception:
                continue

        if df is None:
            print(f"❌ CSV読込失敗 ({service_name})。スキップします。")
            continue

        # 👑 【バグ修正】法人住所のすり抜けを防止するため、必ず「事業所」の市区町村列を狙い撃ちでターゲットにします
        target_col = "事業所住所（市区町村）"
        # 表記揺れ（半角括弧）にも100%対応する安全ガード
        if "事業所住所（市区町村）" not in df.columns and "事業所住所(市区町村)" in df.columns:
            target_col = "事業所住所(市区町村)"
        
        if target_col not in df.columns:
            print(f"❌ 事業所住所（市区町村）列が見つかりません ({service_name})。")
            continue

        df_filtered = df[df[target_col].str.startswith(("大阪府", "東京都"), na=False)].copy()
        
        facilities = []
        
        for _, row in df_filtered.iterrows():
            name = safe_get(row, ["事業所の名称", "事業所名称"])
            city = safe_get(row, ["事業所住所（市区町村）", "事業所住所(市区町村)", target_col])
            address_detail = safe_get(row, ["事業所住所（番地以降）", "事業所住所(番地以降)"])
            
            if not re.search(r'[0-9０-９]', address_detail) or len(address_detail) <= 2:
                address_detail = ""
            address = city + address_detail
            
            raw_tel = safe_get(row, ["事業所電話番号", "事業所連絡先", "電話番号"])
            tel_clean = re.sub(r'[^0-9\-]', '', raw_tel.translate(str.maketrans('０１２３４５６７８９', '0123456789')))

            raw_lat = safe_get(row, ["事業所緯度", "緯度"])
            raw_lon = safe_get(row, ["事業所経度", "経度"])
            
            lat, lon = None, None
            is_approximate = False
            
            try:
                if raw_lat: lat = float(raw_lat)
                if raw_lon: lon = float(raw_lon)
            except Exception:
                pass
                
            if lat is None or lon is None:
                is_approximate = True
                detected_city = None
                for key in MUNICIPAL_COORDS.keys():
                    if key in city and (city.index(key) == 3 or city.index(key) == 0):
                        detected_city = key
                        break
                if detected_city:
                    lat = MUNICIPAL_COORDS[detected_city]["lat"]
                    lon = MUNICIPAL_COORDS[detected_city]["lon"]
                else:       
                    if city.startswith("東京都"):
                        lat = MUNICIPAL_COORDS["フェイルセーフ東京都庁"]["lat"]
                        lon = MUNICIPAL_COORDS["フェイルセーフ東京都庁"]["lon"]
                    else:            
                        lat = MUNICIPAL_COORDS["フェイルセーフ大阪府庁"]["lat"]
                        lon = MUNICIPAL_COORDS["フェイルセーフ大阪府庁"]["lon"]

            facilities.append({
                "name": name,
                "service_type": service_name,   
                "address": address,
                "tel": raw_tel,
                "tel_clean": tel_clean,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "is_approximate": is_approximate
            })

        output_path = os.path.join(target_dir, f"data_{output_key}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(facilities, f, ensure_ascii=False, indent=2)
            
        summary_logs.append(f" - {service_name}: {len(facilities)}件 生成完了")

    # 👑 【修正】不要な data.json の重複上書きブロックの削除報告注記を、
    # 実行効率向上のためループの外側（出力完了ログの前）に移動しました。
    os.system(f"cp index.html {target_dir}/")
    
    print("\n==========================================")
    for log in summary_logs: print(log)
    print("==========================================")

if __name__ == "__main__":
    try:
        run_build()
    except Exception as e:
        sys.exit(1)
