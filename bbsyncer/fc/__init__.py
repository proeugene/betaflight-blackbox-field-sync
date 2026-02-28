"""FC detection package."""

from .detector import (
    FCBlackboxEmpty,
    FCDetectionError,
    FCInfo,
    FCNotBetaflight,
    FCSDCardBlackbox,
    detect_fc,
)

__all__ = [
    'FCInfo',
    'FCDetectionError',
    'FCNotBetaflight',
    'FCSDCardBlackbox',
    'FCBlackboxEmpty',
    'detect_fc',
]
