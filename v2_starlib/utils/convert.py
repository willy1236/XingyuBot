import base64
from io import BytesIO


def base64_to_buffer(base64_string: str) -> BytesIO:
    """
    將 Base64 字串轉換為 BufferedIO 物件

    Args:
        base64_string (str): Base64 編碼的字串

    Returns:
        BufferedIO: 包含解碼資料的 BufferedIO 物件

    Raises:
        ValueError: 當 Base64 解碼失敗時
    """
    try:
        # 移除可能的 Base64 前綴 (如 "data:image/png;base64,")
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        # 解碼 Base64 字串
        binary_data = base64.b64decode(base64_string)

        # 創建 BytesIO 物件並返回
        buffer = BytesIO(binary_data)
        return buffer
    except Exception as e:
        raise ValueError(f"Base64 解碼失敗: {str(e)}")
