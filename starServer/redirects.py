from urllib.parse import urlsplit


def is_allowed_return_url(url: str, base_domain: str) -> bool:
    """登入完成後是否可以導回這個網址。

    只接受 base_domain 本身或其子網域的絕對網址，避免登入流程被拿來導向外部網站（open redirect）。
    除了本機開發（base_domain 為 localhost）以外一律要求 https。
    """
    # 反斜線與控制字元在不同瀏覽器的解析方式不一致，直接拒絕
    if any(ch == "\\" or ord(ch) < 0x20 for ch in url):
        return False

    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if not host:
        return False

    allowed_schemes = {"https", "http"} if base_domain == "localhost" else {"https"}
    if parts.scheme not in allowed_schemes:
        return False

    host = host.lower()
    base_domain = base_domain.lower()
    return host == base_domain or host.endswith(f".{base_domain}")
