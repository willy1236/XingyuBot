import re
import socket
import unicodedata
import ssl
import dns.resolver
import certifi

import requests
import whois
from urllib.parse import urlparse

def check_url_format(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    regex = re.compile(
        r"^(?:http|ftp)s?://"
        r"(?:[\w.-]+)"
        r"(?:\.[a-zA-Z]{2,})+"
        r"(?:[/?#].*)?$",
        re.IGNORECASE,
    )
    if re.match(regex, url):
        return url
    return None


def parse_url_redirects(url: str) -> list[str] | None:
    try:
        resp = requests.head(url, allow_redirects=True, timeout=5)
    except Exception:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=5)
        except Exception as e:
            return None
    redirect_urls = [url]
    for resp in resp.history:
        redirect_urls.append(resp.headers.get("Location"))
    return redirect_urls


def parse_domain(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.netloc.split(":")[0]  # 移除 port


def get_whois(domain):
    try:
        w = whois.whois(domain)
        return {
            "domain_name": w.domain_name,
            "registrar": w.registrar,
            "registrar_url": w.registrar_url,
            "creation_date": w.creation_date,
            "updated_date": w.updated_date,
            "expiration_date": w.expiration_date,
            "name": w.name,  # registrant name
            "org": w.org,  # registrant organization (可能為 None)
            "emails": w.emails,
        }
    except Exception as e:
        return {"error": str(e)}


def check_suspicious_pattern(domain: str) -> bool:
    return bool(domain.count(".") > 3 or re.search(r"\d{5,}", domain))


def get_ssl_subject(domain, port=443):
    """
    取得 SSL 憑證的 subject 欄位（美化輸出）
    Args:
        domain (str): 要查詢的網域名稱
        port (int): 連線埠（預設 443）
    Returns:
        dict: 包含憑證主要資訊或錯誤訊息
    """
    result = {"domain": domain}
    try:
        ctx_verify = ssl.create_default_context(cafile=certifi.where())
        with socket.create_connection((domain, port), timeout=5) as sock:
            with ctx_verify.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

                subject_data = {}
                for item in cert.get("subject", []):
                    for key, value in item:
                        subject_data[key] = value

                issuer_data = {}
                for item in cert.get("issuer", []):
                    for key, value in item:
                        issuer_data[key] = value

                result.update(
                    {
                        "subject": subject_data,
                        "issuer": issuer_data,
                        "version": cert.get("version"),
                        "serialNumber": cert.get("serialNumber"),
                        "notBefore": cert.get("notBefore"),
                        "notAfter": cert.get("notAfter"),
                    }
                )
                return result
    except socket.timeout:
        return {"domain": domain, "error": "連線逾時"}
    except socket.gaierror:
        return {"domain": domain, "error": "無法解析網域名稱"}
    except ssl.SSLError as e:
        return {"domain": domain, "error": f"SSL 錯誤: {str(e)}"}
    except Exception as e:
        return {"domain": domain, "error": str(e)}


def get_dns_records(domain):
    res = {}
    try:
        q = dns.resolver.resolve(domain, "NS")
        res["NS"] = [r.to_text() for r in q]
    except Exception as e:
        res["NS_error"] = str(e)
    try:
        q = dns.resolver.resolve(domain, "MX")
        res["MX"] = [r.exchange.to_text() for r in q]
    except Exception as e:
        res["MX_error"] = str(e)
    try:
        q = dns.resolver.resolve(domain, "TXT")
        res["TXT"] = [r.to_text() for r in q]
    except Exception as e:
        res["TXT_error"] = str(e)
    return res


def check_url_with_dns_whois(url_text: str) -> dict:
    """
    驗證網址，包含：
    - 縮網址展開
    - DNS 查詢
    - Whois 查詢

    參數:
        url: 要檢查的網址

    回傳: dict
    """
    url = check_url_format(url_text)
    result = {
        "original_url": url,
        "redirect_urls": [
            url,
        ],
        "final_url": None,
        "format_valid": False,
        "domain": None,
        "resolved_ip": None,
        "suspicious_pattern": False,
        "whois_info": None,
    }

    # Step 1: 格式檢查
    regex = re.compile(
        r"^(?:http|ftp)s?://"
        r"(?:[\w.-]+)"
        r"(?:\.[a-zA-Z]{2,})+"
        r"(?:[/?#].*)?$",
        re.IGNORECASE,
    )
    if not re.match(regex, url):
        return result  # 格式錯誤

    result["format_valid"] = True

    # Step 2: 縮網址展開
    try:
        resp = requests.head(url, allow_redirects=True, timeout=5)
    except Exception:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=5)
        except Exception as e:
            result["final_url"] = None
            return result

    final_url = resp.url
    for resp in resp.history:
        result["redirect_urls"].append(resp.headers.get("Location"))
    result["final_url"] = final_url

    # Step 3: 網域提取
    parsed = urlparse(result["final_url"])
    domain = parsed.netloc.split(":")[0]  # 移除 port
    result["domain"] = domain

    # Step 4: DNS 查詢
    try:
        ip_addr = socket.gethostbyname(domain)
        result["resolved_ip"] = ip_addr
    except Exception as e:
        result["resolved_ip"] = f"DNS 查詢失敗: {e}"

    # Step 5: Whois 查詢
    try:
        w = whois.whois(domain)
        result["whois_info"] = w
    except Exception as e:
        result["whois_info"] = f"Whois 查詢失敗"

    # Step 6: 可疑檢查
    if domain.count(".") > 3 or re.search(r"\d{5,}", domain):
        result["suspicious_pattern"] = True

    # SSL 憑證檢查（嘗試）
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(3)
            s.connect((domain, 443))
            cert = s.getpeercert()
            result["ssl_cert_subject"] = cert.get("subject")
            result["ssl_cert_issuer"] = cert.get("issuer")
    except Exception as e:
        result["ssl_error"] = f"TLS/SSL check failed: {e}"

    result["contains_confusable_unicode"] = contains_confusable_unicode(domain)

    return result

def contains_confusable_unicode(domain: str) -> bool:
    """
    偵測 domain 是否包含非 ASCII 且可能為同形字攻擊（簡單 heuristics）
    - 若 domain 包含非 ASCII 字元或混合腳本（Latin + Cyrillic），回傳 True
    """
    has_non_ascii = any(ord(ch) > 127 for ch in domain)
    if not has_non_ascii:
        return False
    # 檢查是否混合腳本（例如既有 Latin 又有 Cyrillic）
    scripts = set()
    for ch in domain:
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if "CYRILLIC" in name:
            scripts.add("CYRILLIC")
        elif "GREEK" in name:
            scripts.add("GREEK")
        elif "LATIN" in name:
            scripts.add("LATIN")
        else:
            scripts.add("OTHER")
    # 若存在 LATIN 且存在其他非 LATIN 腳本 -> 可疑
    return ("LATIN" in scripts and len(scripts) > 1) or ("CYRILLIC" in scripts and "GREEK" in scripts) or True

def generate_url_report(url_text: str) -> list[str]:
    # data = check_url_with_dns_whois(url_text)
    text = []

    # 網址網域檢查
    url = check_url_format(url_text)
    if not url:
        text.append(f"{url_text} 不是正確的網址格式")
        return text

    url_redirects = parse_url_redirects(url)
    if url_redirects is None:
        text.append(f"無法取得網址的重定向資訊")
        return text
    url = url_redirects[-1] if url_redirects else url
    text.append(f"網址：{'\n-> '.join(url_redirects)}")

    domain = parse_domain(url)
    text.append(f"網域：{domain}")

    # whois 資訊
    whois_info = get_whois(domain)
    if whois_info.get("error"):
        text.append("取得 whois 資訊失敗")
    else:
        text.append(f"註冊地：{whois_info.get('country', '未知')}")

        if whois_info["org"]:
            if whois_info["org"] == "REDACTED FOR PRIVACY":
                text.append(f"註冊單位：受隱私保護")
            else:
                text.append(f"註冊單位：{whois_info['org']}")

        if whois_info["creation_date"]:
            if isinstance(whois_info["creation_date"], list):
                creation_date = whois_info["creation_date"][0]
            else:
                creation_date = whois_info["creation_date"]

        text.append(f"註冊時間：{creation_date if creation_date else '未知'}")

    # SSL 憑證檢查
    ssl_subject = get_ssl_subject(domain)
    assert ssl_subject is not None, "SSL 憑證資訊取得失敗"
    if not ssl_subject.get("error"):
        if not ssl_subject.get("certificate_valid", True):
            text.append("⚠️ SSL 證書驗證失敗")

        text.append(f"SSL 證書資訊：")
        text.append(f"  組織名稱：{ssl_subject['subject'].get('organizationName', '未知')}")
        text.append(f"  國家代碼：{ssl_subject['subject'].get('countryName', '未知')}")
        text.append(f"  統一編號/組織註冊編號：{ssl_subject['subject'].get('serialNumber', '未知')}")
        text.append(f"  主要網域名稱：{ssl_subject['subject'].get('commonName', '未知')}")
        text.append(f"  地址：{ssl_subject['subject'].get('streetAddress', '未知')}")

        text.append(f"SSL 證書發行者：")
        text.append(f"  組織名稱：{ssl_subject['issuer'].get('organizationName', '未知')}")
        text.append(f"  國家代碼：{ssl_subject['issuer'].get('countryName', '未知')}")
    else:
        text.append(f"無法取得 SSL 證書資訊: {ssl_subject['error']}")

    # # DNS 紀錄
    # dns_records = get_dns_records(domain)
    # if dns_records.get("NS"):
    #     text.append(f"DNS NS 紀錄：{', '.join(dns_records['NS'])}")
    # if dns_records.get("MX"):
    #     text.append(f"DNS MX 紀錄：{', '.join(dns_records['MX'])}")
    # if dns_records.get("TXT"):
    #     text.append(f"DNS TXT 紀錄：{', '.join(dns_records['TXT'])}")

    # 可疑檢查
    if check_suspicious_pattern(domain):
        text.append("警告：網址格式與常見釣魚網站相似")

    if contains_confusable_unicode(domain):
        text.append("警告：網址包含可疑的 Unicode 字元，可能為同形字攻擊")

    return text


# def search_uri(uri: str, threat_type: webrisk_v1.ThreatType.MALWARE) -> SearchUrisResponse:
#     """Checks whether a URI is on a given threatList.

#     Multiple threatLists may be searched in a single query. The response will list all
#     requested threatLists the URI was found to match. If the URI is not
#     found on any of the requested ThreatList an empty response will be returned.

#     Args:
#         uri: The URI to be checked for matches
#             Example: "http://testsafebrowsing.appspot.com/s/malware.html"
#         threat_type: The ThreatLists to search in. Multiple ThreatLists may be specified.
#             Example: threat_type = webrisk_v1.ThreatType.MALWARE

#     Returns:
#         SearchUrisResponse that contains a threat_type if the URI is present in the threatList.
#     """
#     api_key = sqldb.get_bot_token(APIType.Google, token_seq=1).access_token
#     webrisk_client = webrisk_v1.WebRiskServiceClient(client_options={"api_key": api_key})

#     request = webrisk_v1.SearchUrisRequest()
#     request.threat_types = [threat_type]
#     request.uri = uri

#     response = webrisk_client.search_uris(request)
#     if response.threat.threat_types:
#         print(f"The URI has the following threat: {response}")
#     else:
#         print("The URL is safe!")
#     return response
