import asyncio
import atexit
import time

import discord
import truststore

from sentry_bootstrap import init_sentry

truststore.inject_into_ssl()

init_sentry(service="main")


async def main():
    pass


if __name__ == "__main__":
    asyncio.run(main())
