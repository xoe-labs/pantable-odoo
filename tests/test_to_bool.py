#!/usr/bin/env python3
"""

"""
from .context import to_bool


def test_to_bool():
    assert to_bool("true")
    assert to_bool("false") is False
    assert to_bool("yes")
    assert to_bool("no") is False
    assert to_bool("NO") is False
    return
