import asyncio
from datetime import datetime

import pytest

from src.wechat.publisher import WeChatPublisher


def test_mass_send_requires_explicit_confirmation():
    publisher = WeChatPublisher()

    with pytest.raises(RuntimeError, match="confirm_mass_send=True"):
        asyncio.run(publisher.publish_draft_via_mass_send())


def test_schedule_mass_send_requires_explicit_confirmation():
    publisher = WeChatPublisher()

    with pytest.raises(RuntimeError, match="confirm_schedule=True"):
        asyncio.run(publisher.schedule_mass_send(datetime(2026, 1, 1, 12, 0)))
