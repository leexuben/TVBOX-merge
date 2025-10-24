# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import requests

# ======================
# 配置区
# ======================
# 本地源配置文件路径（包含多个数据源的 JSON 列表或对象）
SOURCES_JSON_PATH = '/ql/data/scripts/tvbox/config/sources.json'

# 合并后写入的本地目标文件路径（青龙面板使用的 TVBox 配置）
TARGET_JSON_PATH = '/ql/data/scripts/tvbox/QLTV.json'

# 远程目标文件地址（GitHub RAW 链接，使用 GITHUB_TOKEN 进行鉴权推送）
# 注意：实际运行时需确保环境变量 GITHUB_TOKEN 已设置且具备写入权限
TARGET_PATH_ON_GITHUB = 'https://${GITHUB_TOKEN}@github.com/leexuben/TVBOX-merge/main/QLTV.json'

# 请求头（模拟浏览器访问，降低被拦截概率）
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; TVBoxMerge/1.0)'
}

# ======================
# 工具函数：从 URL 获取 sites 列表
# ======================
def get_sites_from_url(url):
    """
    从给定 URL 获取 JSON 数据，并尝试提取其中的 'sites' 数组；
    若不是标准结构或解析失败，尝试容错提取最外层 {} 后再取 'sites'；
    若仍失败则返回空列表。
    """
    try:
        # 发起 GET 请求，设置超时 15 秒
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            content = resp.text
            try:
                # 尝试直接解析为 JSON
                data = json.loads(content)
                # 若是字典且包含 'sites' 键，则返回其值
                if isinstance(data, dict) and 'sites' in data:
                    return data['sites']
                # 若本身就是数组，则直接返回
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                # 容错：尝试截取第一个 '{' 到最后一个 '}' 之间的内容
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    data = json.loads(content[start:end])
                    if isinstance(data, dict) and 'sites' in data:
                        return data['sites']
        # 状态码非 200 或解析失败时返回空列表
        return []
    except Exception as e:
        # 捕获所有异常（如网络错误、超时等），打印错误并返回空列表
        print(f"[请求失败] {url} | {e}")
        return []

# ======================
# 工具函数：修复站点路径与 jar
# ======================
def fix_site_paths(site, base_url, jar_url):
    """
    对单个站点字典进行路径修复：
    1. 只要值是字符串且以 "./" 开头，就用 base_url 拼接（对所有字段生效）。
    2. 仅当站点没有 "jar" 键时才新增；若 jar_url 为空或仅空白则不新增。
    """
    base = base_url.rstrip('/')  # 去掉尾部斜杠，避免出现 //

    # 遍历站点所有键值，统一处理：只要值是字符串且以 "./" 开头，就拼接 base
    for k, v in site.items():
        if isinstance(v, str) and v.startswith('./'):
            site[k] = base + '/' + v[2:]  # 去掉 "./" 再拼接

    # 仅当没有 "jar" 键时才补充；若 jar_url 为空白也不新增
    if 'jar' not in site and jar_url and jar_url.strip():
        site['jar'] = jar_url.rstrip('/')

    return site

# ======================
# 主流程
# ======================
def main():
    # 检查本地源配置文件是否存在
    if not os.path.exists(SOURCES_JSON_PATH):
        print(f"[错误] 找不到源配置：{SOURCES_JSON_PATH}")
        return

    # 读取本地源配置文件（JSON 数组：[{url:, jar:, base:}, ...]）
    try:
        with open(SOURCES_JSON_PATH, 'r', encoding='utf-8') as f:
            sources = json.load(f)
    except Exception as e:
        print(f"[错误] 读取 sources.json 失败：{e}")
        return

    # 读取本地目标文件（若存在），用于去重合并
    if os.path.exists(TARGET_JSON_PATH):
        try:
            with open(TARGET_JSON_PATH, 'r', encoding='utf-8') as f:
                target_data = json.load(f)
        except Exception as e:
            print(f"[警告] 读取目标文件失败，将新建：{e}")
            target_data = {}
    else:
        # 目标文件不存在时，初始化一个空字典
        target_data = {}

    # 确保目标数据中包含 'sites' 键，且其值为列表
    if 'sites' not in target_data:
        target_data['sites'] = []

    # 使用集合记录已存在的 key，避免重复添加（提升去重性能）
    existing_keys = {s.get('key', '').strip() forin target_data['sites'] if s.get('key')}

    # 遍历每一个数据源（每个源包含 url、jar、base 等信息）
    for src in sources:
        url = src.get('url')      # 必需：远程 JSON 地址
        jar = src.get('jar') or ''  # 可选：默认 jar 包地址
        base = src.get('base') or ''  # 可选：基础路径，用于修复相对路径

        # 跳过没有 url 的源
        if not url:
            continue

        print(f"[拉取] {url}")
        # 从当前源 URL 获取站点列表
        sites = get_sites_from_url(url)
        forin sites:
            # 修复当前站点的路径与 jar
            fixed = fix_site_paths(s, base.rstrip('/') + '/', jar.rstrip('/'))
            key = fixed.get('key', '').strip()  # 站点的唯一标识

            # 若 key 存在且未在目标中存在，则添加到目标列表并记录 key
            if key and key not in existing_keys:
                target_data['sites'].append(fixed)
                existing_keys.add(key)

    # ======================
    # 写出文件：每个顶层集合各占一行，集合内每个元素各占一行
    # ======================
    try:
        with open(TARGET_JSON_PATH, 'w', encoding='utf-8') as f:
            # 写入左大括号
            f.write('{\n')
            items = []
            # 按键名排序，便于 Git 差异对比（可读性更好）
            for k in sorted(target_data.keys()):
                v = target_data[k]
                if isinstance(v, list):
                    if not v:  # 空数组也保留为一行
                        items.append(f'  "{k}": []')
                    else:
                        # 将列表中的每个元素转为紧凑型 JSON 字符串
                        lines = [json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in v]
                        # 用逗号连接并在前后加上换行与缩进，形成多行块
                        joined = ',\n'.join(lines)
                        items.append(f'  "{k}": [\n{joined}\n  ]')
            # 将所有顶层键值对用逗号连接，并写入文件
            f.write(',\n'.join(items))
            f.write('\n}\n')  # 写入右大括号并换行

        # 打印完成信息（包含站点总数）
        print(f"[完成] 已生成：{TARGET_JSON_PATH}，共 {len(target_data.get('sites', []))} 个站点")
    except Exception as e:
        # 捕获写出过程中的异常（如权限不足、磁盘满等）
        print(f"[错误] 写出文件失败：{e}")

# ======================
# 程序入口
# ======================
if __name__ == '__main__':
    # 当脚本被直接运行时，执行 main 函数
    main()
