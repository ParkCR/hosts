#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import dns.resolver
import platform
import subprocess
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# ====================== 配置区域 ======================
RELIABLE_DNS_SERVERS = [
    '8.8.8.8',      # Google DNS
    '1.1.1.1',      # Cloudflare DNS
]

#     '223.5.5.5',    # 阿里DNS
#     '119.29.29.29'  # 腾讯DNS

PING_TIMEOUT = 2
MAX_WORKERS = 10
IP_PADDING = 24  # IP地址对齐宽度

# 自定义Update URL模板
UPDATE_URL_TEMPLATE = "https://raw.githubusercontent.com/ParkCR/hosts/main/hosts_{}"

# ====================== 工具函数 ======================
def get_bj_time_str():
    utc_dt = datetime.now(timezone.utc)
    bj_dt = utc_dt.astimezone(timezone(timedelta(hours=8)))
    return bj_dt.strftime("%Y-%m-%d %H:%M:%S")

def write_to_file(contents, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(contents)
        print(f"[OK] 成功写入 {filename}")
    except Exception as e:
        print(f"[Error] 写入 {filename} 失败: {str(e)}")

def is_ip_reachable(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', '-W', str(PING_TIMEOUT), ip]
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except:
        return False

def format_hosts_entry(ip, domain):
    """格式化hosts条目，确保美观对齐"""
    return f"{ip.ljust(IP_PADDING)}{domain}"

def dns_lookup(domain):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3
    
    for dns_server in RELIABLE_DNS_SERVERS:
        resolver.nameservers = [dns_server]
        try:
            answers = resolver.resolve(domain, "A")
            ips = [str(answer) for answer in answers]
            
            for ip in ips:
                if is_ip_reachable(ip):
                    return [ip]
            
            return ips[:1] if ips else []
            
        except dns.resolver.NXDOMAIN:
            print(f"[DNS] 域名不存在: {domain}")
            return []
        except dns.resolver.Timeout:
            print(f"[DNS] 查询超时: {domain} @ {dns_server}")
            continue
        except Exception as e:
            print(f"[DNS] {domain} @ {dns_server} 错误: {str(e)}")
            continue
    
    print(f"[Critical] {domain} 在所有DNS服务器上均解析失败")
    return []

def load_domain_data(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("JSON格式错误：顶层必须是字典")
            return data
    except FileNotFoundError:
        print(f"[Error] 文件不存在: {filename}")
        return {}
    except json.JSONDecodeError:
        print(f"[Error] JSON格式错误: {filename}")
        return {}
    except Exception as e:
        print(f"[Error] 加载 {filename} 失败: {str(e)}")
        return {}

# ====================== 主逻辑 ======================
def generate_hosts_content(domain_data):
    resolved_domains = {}
    update_time = get_bj_time_str()
    
    print(f"[Start] 开始解析 {len(domain_data)} 个分类的域名...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for category, domains in domain_data.items():
            if not domains:
                print(f"[Warning] 分类 '{category}' 没有域名，跳过")
                continue
                
            print(f"[Processing] 正在处理: {category} ({len(domains)}个域名)")
            
            future_to_domain = {
                domain: executor.submit(dns_lookup, domain)
                for domain in domains
            }
            
            resolved_ips = {}
            for domain, future in future_to_domain.items():
                result = future.result()
                resolved_ips[domain] = result if result else ["#"]
            
            resolved_domains[category] = resolved_ips
    
    # 生成文件内容
    key_content = {}
    hosts_content = f"""# ============================================
# Auto-generated hosts file
# Update: {update_time} (UTC+8)
# ============================================

"""
    
    # 简洁版hosts内容（无统计信息）
    clean_hosts_content = hosts_content
    
    for category, domains_ips in resolved_domains.items():
        category_lower = category.lower()
        category_header = f"# {category} Hosts Start"
        category_footer = f"# {category} Hosts End"
        
        # 完整版内容（带统计信息）
        full_content_lines = [category_header]
        valid_count = 0
        
        # 简洁版内容
        clean_content_lines = [category_header]
        
        for domain, ips in domains_ips.items():
            if ips and ips[0] != "#":
                entry = format_hosts_entry(ips[0], domain)
                full_content_lines.append(entry)
                clean_content_lines.append(entry)
                valid_count += 1
            else:
                entry = f"# {domain.ljust(IP_PADDING-2)}解析失败"
                full_content_lines.append(entry)
                clean_content_lines.append(entry)
        
        # 完整版添加统计信息
        update_url = UPDATE_URL_TEMPLATE.format(category_lower)
        full_content_lines.extend([
            f"# 有效记录: {valid_count}/{len(domains_ips)}",
            f"# Update Time: {update_time}",
            f"# Update URL: {update_url}",
            category_footer
        ])
        
        # 简洁版只保留必要信息
        clean_content_lines.append(category_footer)
        
        key_content[category] = "\n".join(full_content_lines)
        hosts_content += "\n".join(full_content_lines) + "\n\n"
        clean_hosts_content += "\n".join(clean_content_lines) + "\n\n"
    
    # 添加总文件的统计信息
    clean_hosts_content += f"# 总分类数: {len(resolved_domains)}\n"
    clean_hosts_content += f"# 最后更新: {update_time}\n"
    clean_hosts_content += f"# Update URL: https://raw.githubusercontent.com/ParkCR/hosts/main/hosts\n"
    
    return key_content, clean_hosts_content

def main():
    domain_file = os.path.join(os.getcwd(), "domain.json")
    if not os.path.exists(domain_file):
        print(f"[Error] 请创建 domain.json 文件")
        return
    
    domain_data = load_domain_data(domain_file)
    if not domain_data:
        print("[Error] 没有有效的域名数据")
        return
    
    key_content, hosts_content = generate_hosts_content(domain_data)
    
    # 写入各分类文件（完整版）
    for category, content in key_content.items():
        write_to_file(content, f'hosts_{category.lower()}')
    
    # 写入总hosts文件（简洁版）
    write_to_file(hosts_content, 'hosts')
    print("[Success] 所有处理完成！")

if __name__ == '__main__':
    main()
