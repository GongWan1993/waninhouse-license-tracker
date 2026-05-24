"""
新店 + 文山 建築使用執照追蹤 v3
========================================
v3:深層解析 XML — 把每個 Data 內所有層級的文字都抓出來
"""

import json
import os
import sys
import time
from datetime import datetime

import requests
import xml.etree.ElementTree as ET

XINDIAN_KEYWORDS = ['新店區', '新店市']
WENSHAN_KEYWORDS = ['文山區']

NEWTAIPEI_DATASET_ID = 'c1487d7b-fff1-43d3-a2ce-4716eab4d286'
NEWTAIPEI_API_URL = f'https://data.ntpc.gov.tw/api/datasets/{NEWTAIPEI_DATASET_ID}/json'
TAIPEI_HISTORICAL_URL = 'https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=0f3f9675-8356-4f1a-9908-1ce8892012fa'  # 歷年(每年更新)
TAIPEI_CURRENT_URL = 'https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=74a8b311-906e-44c4-91fb-7f413842d4e1'  # 115 年度(每月更新)
# 為了相容舊變數名(可能其他地方有用)
TAIPEI_DOWNLOAD_URL = TAIPEI_HISTORICAL_URL

OUTPUT_DIR = 'data'

# ===== 新北市(維持不變)=====

def fetch_newtaipei_data():
    print('=' * 60)
    print('開始抓取新北市建築使用執照...')
    print('=' * 60)
    all_records = []
    page = 0
    size = 1000
    while True:
        try:
            print(f'  抓取第 {page + 1} 頁...', end='', flush=True)
            r = requests.get(NEWTAIPEI_API_URL, params={'page': page, 'size': size}, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f' ❌ 失敗: {e}')
            break
        if not data:
            print(' (空,結束)')
            break
        page_count = len(data)
        xindian = [r for r in data if any(kw in (r.get('building_site') or '') for kw in XINDIAN_KEYWORDS)]
        all_records.extend(xindian)
        print(f' 取得 {page_count} 筆 (新店 {len(xindian)})')
        if page_count < size:
            break
        page += 1
        time.sleep(0.5)
    print(f'\n✅ 新北市完成:新店區 {len(all_records)} 筆')
    return all_records


def transform_newtaipei(records):
    out = []
    for r in records:
        out.append({
            'city': '新北市', 'district': '新店區',
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

# ===== 台北市 v4:同時抓「歷年」+「當年度」兩個資料集 =====

def fetch_taipei_dataset(url, label):
    """抓單一台北市 XML 資料集"""
    print(f'\n  📥 抓取 [{label}] ...')
    try:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        content = b''
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                content += chunk
        print(f'     下載完成,{len(content) / 1024 / 1024:.2f} MB')
    except Exception as e:
        print(f'  ❌ [{label}] 下載失敗: {e}')
        return []

    try:
        root = ET.fromstring(content)
    except Exception as e:
        print(f'  ❌ [{label}] XML 解析失敗: {e}')
        return []

    total = len(list(root))
    print(f'     XML 共 {total} 筆,逐筆搜尋文山...')

    wenshan = []
    for data_elem in list(root):
        full_text = ET.tostring(data_elem, encoding='unicode')
        if any(kw in full_text for kw in WENSHAN_KEYWORDS):
            item = extract_deep(data_elem)
            wenshan.append(item)

    print(f'     ✅ [{label}] 文山區 {len(wenshan)} 筆 (從 {total} 筆中)')
    return wenshan


def fetch_taipei_data():
    """v4:同時抓歷年 + 當年度,合併去重後回傳"""
    print()
    print('=' * 60)
    print('開始抓取台北市建築使用執照 v4 (歷年 + 當年度)...')
    print('=' * 60)

    # 抓歷年資料 (每年更新一次,2025 前)
    historical = fetch_taipei_dataset(TAIPEI_HISTORICAL_URL, '歷年使照摘要')

    # 抓當年度資料 (每月更新,2026)
    current = fetch_taipei_dataset(TAIPEI_CURRENT_URL, '115 年度使照摘要')

    # 合併:用「執照號碼」當 unique key 去重
    # 因為歷年資料可能跟當年度有部分重疊(政府資料更新時間差)
    merged = {}
    for item in historical + current:
        license_no = item.get('執照號碼', '')
        if license_no:
            merged[license_no] = item
        else:
            # 沒執照號碼的用 id 隨機
            merged[f'_no_id_{len(merged)}'] = item

    wenshan_records = list(merged.values())

    print(f'\n✅ 台北市彙整完成:')
    print(f'   - 歷年:    {len(historical)} 筆')
    print(f'   - 當年度:  {len(current)} 筆')
    print(f'   - 合併去重後: {len(wenshan_records)} 筆')

    # 印出第一筆當年度資料(如果有的話)供確認
    if current:
        print(f'\n  最新一筆(115 年度)的所有欄位:')
        for k, v in list(current[0].items())[:30]:
            v_preview = str(v)[:60] if v else ''
            print(f'    {k}: {v_preview}')

    return wenshan_records


def extract_deep(elem, prefix=''):
    """
    把一個 XML 元素的所有層級展開成 flat dict。
    例如 <a><b>text1</b><c><d>text2</d></c></a>
    會變成 {'b': 'text1', 'd': 'text2'}
    """
    result = {}
    for child in elem:
        tag = child.tag
        text = (child.text or '').strip()
        children = list(child)
        if children:
            # 有子元素,遞迴
            sub = extract_deep(child)
            result.update(sub)
            if text:
                result[tag] = text
        else:
            # 葉子節點
            if text:
                # 如果已有同名 key,把舊值加上 _2、_3 ...
                k = tag
                idx = 2
                while k in result:
                    k = f'{tag}_{idx}'
                    idx += 1
                result[k] = text
    return result


def transform_taipei(records):
    out = []
    for r in records:
        def get(*keys):
            for k in keys:
                if k in r and r[k]:
                    return r[k]
                # 模糊比對
                for actual in r:
                    if k in actual and r[actual]:
                        return r[actual]
            return ''

        out.append({
            'city': '台北市', 'district': '文山區',
            'license_number': get('執照號碼', '使照號碼'),
            'permit_date': get('發照日期'),
            'issue_date': get('發照日期'),
            'proprietor': '',
            'address': get('地址', '建築地點'),
            'building_site': get('建築地點', '地址'),
            'land_use': get('使用分區'),
            'building_use': get('用途', '建築物用途'),
            'households': get('戶數'),
            'floors_above': get('地上層數'),
            'floors_below': get('地下層數'),
            'height': get('建物高度', '建築物高度'),
            'total_floor_area': get('總樓地板面積', '建物面積'),
            'building_area': get('建築面積'),
            'designer': get('設計人'),
            'supervisor': get('監造人'),
            'constructor': get('承造人'),
            'parking_legal': '',
            'parking_award': '',
            'parking_own': '',
            'commencement_date': get('開工日期'),
            'completion_date': get('竣工日期'),
            'project_cost': get('工程金額'),
            'source_url': 'https://data.taipei/dataset/detail?id=c876ff02-af2e-4eb8-bd33-d444f5052733',
        })
    return out


def main():
    print()
    print('🏠 新店 + 文山 建築使用執照資料更新工具 v3')
    print(f'   執行時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    nt_data = transform_newtaipei(fetch_newtaipei_data())
    tp_data = transform_taipei(fetch_taipei_data())

    all_data = nt_data + tp_data
    all_data.sort(key=lambda r: r.get('issue_date', '') or r.get('permit_date', ''), reverse=True)

    output = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(all_data),
        'xindian_count': len(nt_data),
        'wenshan_count': len(tp_data),
        'records': all_data
    }

    with open(os.path.join(OUTPUT_DIR, 'licenses.json'), 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUTPUT_DIR, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(f'最後更新: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'新店區: {len(nt_data)} 筆\n')
        f.write(f'文山區: {len(tp_data)} 筆\n')
        f.write(f'合計:   {len(all_data)} 筆\n')

    print()
    print('=' * 60)
    print(f'✅ 完成! 新店 {len(nt_data)} | 文山 {len(tp_data)} | 合計 {len(all_data)}')
    print('=' * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\n❌ 執行錯誤: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
