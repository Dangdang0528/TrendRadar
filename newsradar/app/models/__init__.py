# coding=utf-8
"""所有 ORM 模型集中导出

让 alembic env.py 只 import 这一个,即可触发所有表注册到 Base.metadata
"""

from app.models.ai_usage import AIUsage
from app.models.delivery_channel import DeliveryChannel
from app.models.notification_log import NotificationLog
from app.models.subscription import Subscription
from app.models.user import User
from app.models.user_schedule import UserSchedule

__all__ = [
    "User",
    "Subscription",
    "DeliveryChannel",
    "UserSchedule",
    "AIUsage",
    "NotificationLog",
]
