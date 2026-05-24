"""
新店 + 文山 建築使用執照追蹤
========================================
此腳本每週自動執行,從政府開放資料抓取最新的建築使用執照資料,
篩選出新店區與文山區的部分,合併成統一格式輸出 JSON。

資料來源:
- 新北市政府工務局:新北市建築執照存查
  https://data.ntpc.gov.tw/datasets/c1487d7b-fff1-43d3-a2ce-4716eab4d286
- 台北市政府都發局:臺北市歷年使用執照摘要
  https://data.taipei/dataset/detail?id=c876ff02-af2e-4eb8-bd33-d444f5052733

執行環境:GitHub Actions (Python 3.10+)
作者:丸在房地產 (waninhouse.tw)
"""

import json
import os
import sys
import time
import zipfile
from datetime import datetime
from io import BytesIO

import requests
import xml.etree.ElementTree as ET

# ===== 設定 =====

# 新北市:新店區的關鍵字 (用於從「建築地點」欄位篩選)
XINDIAN_KEYWORDS = ['新店區', '新店市']  # 舊資料可能寫「新店市」

# 台北市:文山區的關鍵字
WENSHAN_KEYWORDS = ['文山區']

# 新北市 API
NEWTAIPEI_DATASET_ID = 'c1487d7b-fff1-43d3-a2ce-4716eab4d286'
NEWTAIPEI_API_URL = f'https://data.ntpc.gov.tw/api/datasets/{NEWTAIPEI_DATASET_ID}/json'

# 台北市資料下載點 (XML 大檔)
TAIPEI_DOWNLOAD_URL = 'https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=0f3f9675-8356-4f1a-9908-1ce8892012fa'

# 輸出資料夾
OUTPUT_DIR = 'data'

# ===== 抓取新北市資料 =====

def fetch_newtaipei_data():
    """
    從新北市資料平台,分頁抓取建築使用執照資料,
    並只保留「建築地點」包含「新店」的記錄。

    新北市 API 是分頁的,每次最多回傳 1000 筆。
    """
    print('=' * 60)
    print('開始抓取新北市建築使用執照...')
    print('=' * 60)

    all_records = []
    page = 0
    size = 1000  # 每頁筆數

    while True:
        params = {'page': page, 'size': size}
        try:
            print(f'  抓取第 {page + 1} 頁...', end='', flush=True)
            r = requests.get(NEWTAIPEI_API_URL, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f' ❌ 失敗: {e}')
            break

        if not data:
            print(' (空,結束分頁)')
            break

        # 篩選新店區
        page_count = len(data)
        xindian_in_page = [
            r for r in data
            if any(kw in (r.get('building_site') or '') for kw in XINDIAN_KEYWORDS)
        ]
        all_records.extend(xindian_in_page)
        print(f' 取得 {page_count} 筆 (其中新店 {len(xindian_in_page)} 筆,累計新店 {len(all_records)} 筆)')

        # 如果不滿一頁,代表是最後一頁
        if page_count < size:
            break

        page += 1
        time.sleep(0.5)  # 不要太密集,給政府平台喘口氣

    print(f'\n✅ 新北市抓取完成:新店區共 {len(all_records)} 筆使用執照')
    return all_records


def transform_newtaipei(records):
    """把新北市的原始欄位轉成統一格式"""
    out = []
    for r in records:
        out.append({
            'city': '新北市',
            'district': '新店區',
            'license_number': r.get('license_number', ''),
            'permit_date': r.get('date_the_permit', ''),
            'issue_date': r.get('date_licensing', ''),
            'proprietor': r.get('proprietor', ''),
            'address': r.get('house_address', '') or r.get('building_site', ''),
            'building_site': r.get('building_site', ''),
            'land_use': r.get('land_use_zoning', ''),
            'building_use': r.get('use_of_buildings', ''),
            'households': r.get('households', ''),
            'floors_above': r.get('number_of_stories', ''),
            'floors_below': r.get('ground_floor', ''),
            'height': r.get('building_height', ''),
            'total_floor_area': r.get('total_floor_area', ''),
            'building_area': r.get('building_area', ''),
            'designer': r.get('designer', ''),
            'supervisor': r.get('supervisor', ''),
            'constructor': r.get('constructor', ''),
            'parking_legal': r.get('statutory_number_of_vehic', ''),
            'parking_award': r.get('vehicles_parked_award', ''),
            'parking_own': r.get('vehicles_parked_own', ''),
            'commencement_date': r.get('commencement_date', ''),
            'completion_date': r.get('completion_date', ''),
            'project_cost': r.get('project_cost', ''),
            'source_url': f'https://data.ntpc.gov.tw/datasets/{NEWTAIPEI_DATASET_ID}',
        })
    return out

# ===== 抓取台北市資料 =====

def fetch_taipei_data():
    """
    從台北市資料大平台下載歷年使照 XML (約 65 MB),
    解析後只保留「地址」包含「文山」的記錄。
    """
    print()
    print('=' * 60)
    print('開始抓取台北市建築使用執照...')
    print('=' * 60)
    print(f'  下載 XML 檔案 (約 65 MB,請耐心等候)...')

    try:
        r = requests.get(TAIPEI_DOWNLOAD_URL, timeout=300, stream=True)
        r.raise_for_status()
        content = b''
        downloaded = 0
        for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB 一塊
            if chunk:
                content += chunk
                downloaded += len(chunk)
                print(f'\r  下載中: {downloaded / 1024 / 1024:.1f} MB', end='', flush=True)
        print()
        print(f'  下載完成,總計 {len(content) / 1024 / 1024:.1f} MB')
    except Exception as e:
        print(f'❌ 下載失敗: {e}')
        return []

    # 解析 XML
    print('  開始解析 XML...')
    try:
        root = ET.fromstring(content)
    except Exception as e:
        print(f'❌ XML 解析失敗: {e}')
        return []

    # 找到所有「使用執照」記錄
    # 注意:政府 XML 的結構需要先看實際內容才知道,這裡先用通用方式試試
    all_items = []
    for elem in root.iter():
        tag = elem.tag
        # 看起來是「執照記錄」的元素(可能叫 record / row / item / 使照)
        if any(key in tag.lower() for key in ['record', 'row', 'item']) or '執照' in tag:
            item = {child.tag: (child.text or '').strip() for child in elem}
            if item:
                all_items.append(item)

    # 篩選文山區
    wenshan_records = []
    for item in all_items:
        addr = ''
        for key, value in item.items():
            if '地址' in key or 'address' in key.lower():
                addr = value
                break
        if any(kw in addr for kw in WENSHAN_KEYWORDS):
            wenshan_records.append(item)

    print(f'\n✅ 台北市抓取完成:文山區共 {len(wenshan_records)} 筆使用執照(從 {len(all_items)} 筆總資料中篩出)')

    # 如果一筆都沒抓到,可能 XML 結構跟我猜的不同,印一個樣本給除錯用
    if not wenshan_records and all_items:
        print('  ⚠️ 沒篩到文山資料,印出第一筆原始資料供除錯:')
        print(f'  欄位: {list(all_items[0].keys())[:10]}')

    return wenshan_records


def transform_taipei(records):
    """把台北市的原始欄位轉成統一格式"""
    out = []
    for r in records:
        # 台北市的欄位名稱是中文 + 英文混合,要彈性對應
        def get(*keys):
            for k in keys:
                for actual_key in r:
                    if k in actual_key or actual_key in k:
                        v = r[actual_key]
                        if v: return v
            return ''

        out.append({
            'city': '台北市',
            'district': '文山區',
            'license_number': get('執照號碼', 'license'),
            'permit_date': get('發照日期', 'permit_date', 'issue_date'),
            'issue_date': get('發照日期', 'issue_date'),
            'proprietor': get('起造人', 'proprietor'),  # 台北市可能沒有這欄
            'address': get('地址', 'address'),
            'building_site': get('地址', 'address'),
            'land_use': get('使用分區', 'land_use'),
            'building_use': get('使用', 'use'),
            'households': get('戶數', 'households'),
            'floors_above': get('地上層數', 'floors_above'),
            'floors_below': get('地下層數', 'floors_below'),
            'height': get('建物高度', '建築物高度', 'height'),
            'total_floor_area': get('總樓地板面積', 'total_floor'),
            'building_area': get('建築面積', 'building_area'),
            'designer': get('設計人', 'designer'),
            'supervisor': get('監造人', 'supervisor'),
            'constructor': get('承造人', 'constructor'),
            'parking_legal': '',
            'parking_award': '',
            'parking_own': '',
            'commencement_date': get('開工', 'commencement'),
            'completion_date': get('竣工', 'completion'),
            'project_cost': get('工程金額', 'project_cost'),
            'source_url': 'https://data.taipei/dataset/detail?id=c876ff02-af2e-4eb8-bd33-d444f5052733',
        })
    return out

# ===== 主程式 =====

def main():
    print()
    print('🏠 新店 + 文山 建築使用執照資料更新工具')
    print(f'   執行時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 第 1 步:抓新北市
    nt_raw = fetch_newtaipei_data()
    nt_data = transform_newtaipei(nt_raw)

    # 第 2 步:抓台北市
    tp_raw = fetch_taipei_data()
    tp_data = transform_taipei(tp_raw)

    # 第 3 步:合併輸出
    all_data = nt_data + tp_data

    # 依發照日期排序 (新到舊)
    def sort_key(r):
        d = r.get('issue_date', '') or r.get('permit_date', '')
        return d
    all_data.sort(key=sort_key, reverse=True)

    output = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(all_data),
        'xindian_count': len(nt_data),
        'wenshan_count': len(tp_data),
        'records': all_data
    }

    # 寫到 data/licenses.json
    output_path = os.path.join(OUTPUT_DIR, 'licenses.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print('=' * 60)
    print(f'✅ 全部完成!')
    print(f'   新店區: {len(nt_data)} 筆')
    print(f'   文山區: {len(tp_data)} 筆')
    print(f'   合計:   {len(all_data)} 筆')
    print(f'   輸出:   {output_path}')
    print('=' * 60)

    # 寫一個給 README 用的簡易摘要
    summary_path = os.path.join(OUTPUT_DIR, 'summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f'最後更新: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'新店區: {len(nt_data)} 筆\n')
        f.write(f'文山區: {len(tp_data)} 筆\n')
        f.write(f'合計:   {len(all_data)} 筆\n')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\n❌ 執行錯誤: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
