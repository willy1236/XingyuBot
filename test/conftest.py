def pytest_addoption(parser):
    parser.addoption(
        "--url",
        action="store",
        default=None,
        help="自訂擷取網址，供整合測試使用（支援 YouTube 單曲、歌單、Bilibili 等）",
    )
