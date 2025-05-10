import json
import os
import dns.resolver
import ping3  # pip install ping3
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# 强制使用的公共DNS服务器列表（按优先级排序）
RELIABLE_DNS_SERVERS = [
    '8.8.8.8',      # Google DNS
    '1.1.1.1'       # Cloudflare DNS
]

#     '223.5.5.5',    # 阿里DNS
#     '119.29.29.29'  # 腾讯DNS

# 更新时间修订北京时间
def get_bj_time_str():
    utc_dt = datetime.now(timezone.utc)
    bj_dt = utc_dt.astimezone(timezone(timedelta(hours=8)))
    return bj_dt.strftime("%Y-%m-%d %H:%M:%S")

# 写入文件
def write_to_file(contents, filename):
    with open(filename, 'w') as file:
        file.write(contents)
    print(f"[OK] {filename} 写入成功")

# 检查IP是否可Ping通
def is_ip_reachable(ip, timeout=2):
    try:
        return ping3.ping(ip, timeout=timeout) is not None
    except:
        return False

# DNS解析（强制使用可靠DNS + Ping检测）
def dns_lookup(domain):
    resolver = dns.resolver.Resolver()
    
    # 尝试所有DNS服务器直到成功
    for dns_server in RELIABLE_DNS_SERVERS:
        resolver.nameservers = [dns_server]
        try:
            answers = resolver.resolve(domain, "A")
            ips = [str(answer) for answer in answers]
            
            # 返回第一个能Ping通的IP（确保可用性）
            for ip in ips:
                if is_ip_reachable(ip):
                    return [ip]
            
            # 如果没有能Ping通的IP，返回第一个解析结果（标记为不可用）
            return ips[:1] if ips else []
            
        except Exception as e:
            print(f"[DNS Error] {domain} 通过 {dns_server} 解析失败: {str(e)}")
            continue
    
    print(f"[Critical] {domain} 在所有DNS服务器上均解析失败")
    return []

# 加载域名数据
def load_domain_data(filename):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("[Error] domain.json 文件不存在")
        return {}
    except json.JSONDecodeError:
        print("[Error] domain.json 格式错误")
        return {}

# 主程序
def main(filename):
    domain_data = load_domain_data(filename)
    if not domain_data:
        print("[Error] 未加载到有效域名数据")
        return

    resolved_domains = {}
    update_time = get_bj_time_str()

    print(f"[Start] 开始解析 {len(domain_data)} 个分类的域名...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        for category, domains in domain_data.items():
            print(f"[Processing] 正在处理分类: {category} ({len(domains)}个域名)")
            
            # 并发执行DNS解析
            future_to_domain = {domain: executor.submit(dns_lookup, domain) for domain in domains}
            resolved_ips = {
                domain: future.result() if future.result() else ["#"]
                for domain, future in future_to_domain.items()
            }
            resolved_domains[category] = resolved_ips

    # 生成文件内容
    key_content = {}
    hosts_content = "# Auto-generated hosts file\n# Updated: " + update_time + "\n\n"

    for category, domains_ips in resolved_domains.items():
        category_header = f"# {category} Hosts Start"
        category_footer = f"# {category} Hosts End"
        
        # 分类独立文件内容
        content = [category_header]
        valid_count = 0
        
        for domain, ips in domains_ips.items():
            if ips and ips[0] != "#":
                content.append(f"{ips[0]}\t\t{domain}")
                valid_count += 1
        
        content.append(f"# 有效记录: {valid_count}/{len(domains_ips)}")
        content.append(f"# Update: {update_time} (UTC+8)")
        content.append(f"# URL: https://example.com/hosts_{category.lower()}")
        content.append(category_footer)
        
        key_content[category] = "\n".join(content)
        
        # 合并到总hosts文件
        hosts_content += "\n".join(content) + "\n\n"

    # 写入文件
    for category, content in key_content.items():
        write_to_file(content, f'hosts_{category.lower()}')

    hosts_content += f"# Total: {len(resolved_domains)} categories\n"
    hosts_content += f"# Last Update: {update_time}\n"
    write_to_file(hosts_content, 'hosts')

    print(f"[Success] 所有域名处理完成！更新时间: {update_time}")

if __name__ == '__main__':
    domain_file = os.path.join(os.getcwd(), "domain.json")
    if not os.path.exists(domain_file):
        print(f"[Error] 请确保 {domain_file} 存在")
        exit(1)
        
    main(domain_file)
