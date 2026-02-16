from __future__ import annotations

import asyncio
import difflib
import json
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum

import discord
import feedparser
import pandas as pd
import requests
from googleapiclient.discovery import build
from pydantic import AliasPath, BaseModel, ConfigDict, Field

from starlib import *
from starlib.database import SQLRepository
from starlib.providers import *

if __name__ == "__main__":
    pass
