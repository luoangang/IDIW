from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


app = create_app(SETTINGS, PlatformStore(SETTINGS))
