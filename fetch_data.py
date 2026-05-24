"""
新店 + 文山 建築使用執照追蹤
========================================
v2: 修正台北市 XML 解析邏輯
"""

import json
import os
import sys
import time
from datetime import datetime

import requests
import xml.etree.ElementTree as ET

# ===== 設定 =====
XINDIAN_KEYWORDS = ['新店區', '新店市']
WENSHAN_KEYWORDS = ['文山區']

NEWTAIPEI_DATASET_ID = 'c1487d7b-fff1-43d3-a2ce-4716eab4d286'
NEWTAIPEI_API_URL = f'https://data.ntpc.gov.tw/api/datasets/{NEWTAIPEI_DATASET_ID}/json'
TAIPEI_DOWNLOAD_URL = 'https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=0f3f9675-8356-4f1a-9908-1ce8892012fa'

OUTPUT_DIR = 'data'

# ===== 新北市 =====

def fetch_newtaipei_data():
    print('=' * 60)
    print('開始抓取新北市建築使用執照...')
    print('=' * 60)

    all_records = []
    page = 0
    size = 1000

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

        page_count = len(data)
        xindian_in_page = [
            r for r in data
            if any(kw in (r.get('building_site') or '') for kw in XINDIAN_KEYWORDS)
        ]
        all_records.extend(xindian_in_page)
        print(f' 取得 {page_count} 筆 (其中新店 {len(xindian_in_page)} 筆,累計 {len(all_records)} 筆)')

        if page_count < size:
            break

        page += 1
        time.sleep(0.5)

    print(f'\n✅ 新北市完成:新店區共 {len(all_records)} 筆')
    return all_records


def transform_newtaipei(records):
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

# ===== 台北市 =====

def fetch_taipei_data():
    """
    v2:更通用的 XML 解析,印出實際結構供除錯
    """
    print()
    print('=' * 60)
    print('開始抓取台北市建築使用執照...')
    print('=' * 60)
    print(f'  下載 XML 檔案 (約 65 MB)...')

    try:
        r = requests.get(TAIPEI_DOWNLOAD_URL, timeout=300, stream=True)
        r.raise_for_status()
        content = b''
        downloaded = 0
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                content += chunk
                downloaded += len(chunk)
                if downloaded % (5 * 1024 * 1024) < 1024 * 1024:  # 每 5 MB 提示一次
                    print(f'\r  下載中: {downloaded / 1024 / 1024:.1f} MB', end='', flush=True)
        print(f'\r  下載完成,總計 {len(content) / 1024 / 1024:.1f} MB')
    except Exception as e:
        print(f'❌ 下載失敗: {e}')
        return []

    # 🔍 除錯:印出 XML 開頭 2000 字
    print()
    print('  ===== XML 開頭預覽(供除錯)=====')
    try:
        preview = content[:2000].decode('utf-8', errors='replace')
        print(preview)
    except Exception as e:
        print(f'  無法預覽: {e}')
    print('  ===== 預覽結束 =====')
    print()

    # 解析 XML
    print('  開始解析 XML...')
    try:
        root = ET.fromstring(content)
    except Exception as e:
        print(f'❌ XML 解析失敗: {e}')
        return []

    print(f'  根元素標籤: <{root.tag}>')
    print(f'  根元素的子元素數量: {len(list(root))}')

    # 看看第一層子元素的標籤是什麼
    if len(list(root)) > 0:
        first_child = list(root)[0]
        print(f'  第一個子元素標籤: <{first_child.tag}>')
        print(f'  第一個子元素內的標籤(前 10 個):')
        for i, sub in enumerate(list(first_child)[:10]):
            text_preview = (sub.text or '')[:30]
            print(f'    <{sub.tag}>: {text_preview}')

    # v2:用更通用的方法 — 把所有「直接子元素」當成記錄
    all_items = []
    for record_elem in list(root):
        item = {}
        for child in record_elem:
            tag = child.tag
            text = (child.text or '').strip()
            item[tag] = text
        if item:
            all_items.append(item)

    print(f'  解析出 {len(all_items)} 筆記錄')

    if not all_items:
        return []

    # 看一下第一筆的所有欄位
    print(f'\n  第一筆記錄的欄位 (供確認):')
    for k, v in list(all_items[0].items())[:20]:
        v_preview = v[:50] if v else ''
        print(f'    {k}: {v_preview}')

    # 篩選文山區
    wenshan_records = []
    for item in all_items:
        # 把所有欄位值串起來搜尋
        all_text = ' '.join(str(v) for v in item.values())
        if any(kw in all_text for kw in WENSHAN_KEYWORDS):
            wenshan_records.append(item)

    print(f'\n✅ 台北市完成:文山區共 {len(wenshan_records)} 筆(從 {len(all_items)} 筆總資料中篩出)')
    return wenshan_records


def transform_taipei(records):
    """彈性對應台北市欄位"""
    out = []
    for r in records:
        def get(*keys):
            for k in keys:
                if k in r:
                    return r[k]
                # 模糊比對(欄位名包含關鍵字)
                for actual in r:
                    if k in actual:
                        return r[actual]
            return ''

        out.append({
            'city': '台北市',
            'district': '文山區',
            'license_number': get('執照號碼', '使照號碼', 'licenseNumber'),
            'permit_date': get('發照日期', 'permitDate'),
            'issue_date': get('發照日期', 'permitDate'),
            'proprietor': '',
            'address': get('地址', 'address'),
            'building_site': get('地址', 'address'),
            'land_use': get('使用分區'),
            'building_use': get('使用'),
            'households': get('戶數', 'households'),
            'floors_above': get('地上層數'),
            'floors_below': get('地下層數'),
            'height': get('建物高度', '建築物高度'),
            'total_floor_area': get('總樓地板面積'),
            'building_area': get('建築面積'),
            'designer': get('設計人'),
            'supervisor': get('監造人'),
            'constructor': get('承造人'),
            'parking_legal': '',
            'parking_award': '',
            'parking_own': '',
            'commencement_date': get('開工日期', '開工'),
            'completion_date': get('竣工日期', '竣工'),
            'project_cost': get('工程金額'),
            'source_url': 'https://data.taipei/dataset/detail?id=c876ff02-af2e-4eb8-bd33-d444f5052733',
        })
    return out

# ===== 主程式 =====

def main():
    print()
    print('🏠 新店 + 文山 建築使用執照資料更新工具 v2')
    print(f'   執行時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    nt_raw = fetch_newtaipei_data()
    nt_data = transform_newtaipei(nt_raw)

    tp_raw = fetch_taipei_data()
    tp_data = transform_taipei(tp_raw)

    all_data = nt_data + tp_data

    def sort_key(r):
        return r.get('issue_date', '') or r.get('permit_date', '')
    all_data.sort(key=sort_key, reverse=True)

    output = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(all_data),
        'xindian_count': len(nt_data),
        'wenshan_count': len(tp_data),
        'records': all_data
    }

    output_path = os.path.join(OUTPUT_DIR, 'licenses.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    summary_path = os.path.join(OUTPUT_DIR, 'summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f'最後更新: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'新店區: {len(nt_data)} 筆\n')
        f.write(f'文山區: {len(tp_data)} 筆\n')
        f.write(f'合計:   {len(all_data)} 筆\n')

    print()
    print('=' * 60)
    print(f'✅ 全部完成!')
    print(f'   新店區: {len(nt_data)} 筆')
    print(f'   文山區: {len(tp_data)} 筆')
    print(f'   合計:   {len(all_data)} 筆')
    print('=' * 60)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\n❌ 執行錯誤: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
