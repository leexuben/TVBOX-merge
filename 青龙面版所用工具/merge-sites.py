import json
import requests
import os
import time
import re
import string

# ======================
# 配置
# ======================
SOURCES_JSON_PATH = '/ql/data/scripts/tvbox/config/sources.json'
TARGET_JSON_PATH = '/ql/data/scripts/tvbox/青龙.json'

# 如需提交到子目录，例如 bingo-tv/青龙.json，请使用：
# TARGET_PATH_ON_GITHUB = 'bingo-tv/青龙.json'
TARGET_PATH_ON_GITHUB = 'https://${GITHUB_TOKEN}@github.com/leexuben/TVBOX-merge/main/青龙.json'

# 请求头（可加 User-Agent 避免部分站点拦截）
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; TVBoxMerge/1.0)'
}

# 连续字符匹配阈值（≥3 个连续相同字符视为重复）
MIN_CONSECUTIVE_CHARS = 3


# ======================
# 工具：清洗 key（去空格、不可见控制字符、全角空格）
# ======================
def clean_key(key: str) -> str:
    # 去除 ASCII 控制字符（除 \t \n \r），替换全角空格/不间断空格等为普通空格
    s = ''.join(ch for ch in key if ch in string.printable or ch in '\u00a0\u3000')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ======================
# 工具：从 URL 获取 sites
# ======================
def get_sites_from_url(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            content = resp.text
            try:
                data = json.loads(content)
                if isinstance(data, dict) and 'sites' in data:
                    return data['sites']
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                # 兜底：尝试提取最外层 {} 的 JSON
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    data = json.loads(content[start:end])
                    if isinstance(data, dict) and 'sites' in data:
                        return data['sites']
        return []
    except Exception as e:
        print(f"[请求失败] {url} | {e}")
        return []


# ======================
# 工具：判断两个 key 是否“相似”（任意一方包含 >=3 个连续相同字符即视为重复）
# ======================
def is_similar_key(key1: str, key2: str) -> bool:
    """
    只要 key1 的任意连续子串在 key2 中出现（长度>=MIN_CONSECUTIVE_CHARS），或反之，即返回 True。
    """
    def has_n_consecutive(s: str, n: int) -> set[str]:
        if len(s) < n:
            return set()
        # 使用集合记录所有长度为 n 的子串，提升多 key 场景命中率
        return {s[i:i + n] for i in range(len(s) - n + 1)}

    key1 = clean_key(key1)
    key2 = clean_key(key2)
    if not key1 or not key2:
        return False

    # 任一方的子串在另一方中出现，即视为相似
    subs1 = has_n_consecutive(key1, MIN_CONSECUTIVE_CHARS)
    subs2 = has_n_consecutive(key2, MIN_CONSECUTIVE_CHARS)
    return bool(subs1 & subs2)  # 集合交集非空


# ======================
# 工具：修复路径与 jar
# ======================
def fix_site_paths(site, base_url, jar_url):
    """
    修复 api/ext 相对路径；jar 保持原值（已在主流程去除了末尾 /）
    """
    if 'jar' not in site:
        site['jar'] = jar_url  # 已在主流程中 rstrip('/')
    base_url = base_url.rstrip('/') + '/'
    for k in ['api', 'ext']:
        if k in site and isinstance(site[k], str) and site[k].startswith('./'):
            site[k] = base_url + site[k][2:]
    return site


# ======================
# 主流程
# ======================
def main():
    if not os.path.exists(SOURCES_JSON_PATH):
        print(f"[错误] 找不到源配置：{SOURCES_JSON_PATH}")
        return

    # 读取源
    try:
        with open(SOURCES_JSON_PATH, 'r', encoding='utf-8') as f:
            sources = json.load(f)
    except Exception as e:
        print(f"[错误] 读取 sources.json 失败：{e}")
        return

    # 读取目标
    if os.path.exists(TARGET_JSON_PATH):
        try:
            with open(TARGET_JSON_PATH, 'r', encoding='utf-8') as f:
                target_data = json.load(f)
        except Exception as e:
            print(f"[警告] 读取目标文件失败，将新建：{e}")
            target_data = {}
    else:
        target_data = {}

    # 确保根结构存在
    if not isinstance(target_data, dict):
        target_data = {}
    if 'sites' not in target_data:
        target_data['sites'] = []

    # 【关键】先清空 sites，避免重复叠加
    target_data['sites'] = []

    # 去重索引：用集合记录已加入站点的 key（已去除首尾空格）
    added_keys = set()

    # 遍历每个源
    for src in sources:
        url = src.get('url')
        jar = src.get('jar') or ''
        base = src.get('base') or ''
        if not url:
            continue
        print(f"[拉取] {url}")
        sites = get_sites_from_url(url)
        forin sites:
            try:
                # 修复路径与 jar
                fixed = fix_site_paths(s, base.rstrip('/') + '/', jar.rstrip('/'))
                key = fixed.get('key', '').strip()
                if not key:
                    continue

                key = clean_key(key)

                # 模糊去重：与已加入的任一站点 key 有 >=3 连续相同字符即视为重复
                duplicate = False
                for existing_key in added_keys:
                    if is_similar_key(key, existing_key):
                        duplicate = True
                        break

                if not duplicate:
                    target_data['sites'].append(fixed)
                    added_keys.add(key)
            except Exception as e:
                print(f"[跳过站点] 数据异常：{e}")

    # 写出
    try:
        with open(TARGET_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(target_data, f, ensure_ascii=False, indent=2)
        print(f"[完成] 已生成：{TARGET_JSON_PATH}，共 {len(target_data['sites'])} 个站点")
    except Exception as e:
        print(f"[错误] 写出文件失败：{e}")


if __name__ == '__main__':
    main()
