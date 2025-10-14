import re
import socket
import unicodedata
import ssl

import requests
import whois
from urllib.parse import urlparse


def check_url_with_dns_whois(url: str) -> dict:
    """
    驗證網址，包含：
    - 縮網址展開
    - DNS 查詢
    - Whois 查詢

    參數:
        url: 要檢查的網址

    回傳: dict
    """
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    result = {
        "original_url": url,
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
        final_url = resp.url
        result["final_url"] = final_url
    except Exception:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=5)
            final_url = resp.url
            result["final_url"] = final_url
        except Exception as e:
            result["final_url"] = f"展開失敗: {e}"
            return result

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
        result["whois_info"] = f"Whois 查詢失敗: {e}"

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
