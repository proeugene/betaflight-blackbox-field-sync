"""FC detection package."""
from .detector import FCInfo, FCDetectionError, FCNotBetaflight, FCSDCardBlackbox, FCBlackboxEmpty, detect_fc

__all__ = [
    "FCInfo", "FCDetectionError", "FCNotBetaflight", "FCSDCardBlackbox",
    "FCBlackboxEmpty", "detect_fc",
]
