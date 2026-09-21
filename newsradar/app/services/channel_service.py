# coding=utf-8
"""投递渠道业务服务"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery_channel import DeliveryChannel
from app.services.crypto import decrypt_credential, encrypt_credential


async def list_channels(db: AsyncSession, user_id: int) -> list[DeliveryChannel]:
    stmt = (
        select(DeliveryChannel)
        .where(DeliveryChannel.user_id == user_id)
        .order_by(DeliveryChannel.priority.desc(), DeliveryChannel.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_channel(
    db: AsyncSession, user_id: int,
    channel: str, label: str | None, credential: dict[str, Any],
    priority: int = 0,
) -> DeliveryChannel:
    enc = encrypt_credential(credential)
    ch = DeliveryChannel(
        user_id=user_id, channel=channel, label=label,
        credential_encrypted=enc, priority=priority, enabled=True,
    )
    db.add(ch)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("渠道创建失败")
    await db.refresh(ch)
    return ch


async def update_channel(
    db: AsyncSession, user_id: int, channel_id: int,
    label: str | None = None, credential: dict[str, Any] | None = None,
    priority: int | None = None, enabled: bool | None = None,
) -> DeliveryChannel:
    ch = await db.get(DeliveryChannel, channel_id)
    if not ch or ch.user_id != user_id:
        raise ValueError("渠道不存在")
    if label is not None:
        ch.label = label
    if credential is not None:
        ch.credential_encrypted = encrypt_credential(credential)
    if priority is not None:
        ch.priority = priority
    if enabled is not None:
        ch.enabled = enabled
    await db.flush()
    await db.refresh(ch)
    return ch


async def delete_channel(db: AsyncSession, user_id: int, channel_id: int) -> bool:
    stmt = (
        delete(DeliveryChannel)
        .where(DeliveryChannel.id == channel_id, DeliveryChannel.user_id == user_id)
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def get_decrypted_channel(
    db: AsyncSession, user_id: int, channel_id: int,
) -> tuple[DeliveryChannel, dict[str, Any]] | None:
    """取渠道并解密凭证(给投递用)"""
    ch = await db.get(DeliveryChannel, channel_id)
    if not ch or ch.user_id != user_id:
        return None
    return ch, decrypt_credential(ch.credential_encrypted)


async def test_channel(
    db: AsyncSession, user_id: int, channel_id: int,
) -> dict[str, Any]:
    """发送一条测试消息,返回结果

    复用 trendradar 的 senders:
    - feishu: send_to_feishu(webhook_url, ...)
    - email:  走全局 SMTP 配置或渠道自带 smtp_user/pass
    """
    pair = await get_decrypted_channel(db, user_id, channel_id)
    if not pair:
        return {"success": False, "message": "渠道不存在", "sent_at": datetime.now(timezone.utc)}
    ch, cred = pair
    sent_at = datetime.now(timezone.utc)

    try:
        if ch.channel == "feishu":
            return await _test_feishu(cred, sent_at)
        elif ch.channel == "email":
            return await _test_email(cred, sent_at)
        elif ch.channel == "telegram":
            return await _test_telegram(cred, sent_at)
        elif ch.channel == "webhook":
            return await _test_webhook(cred, sent_at)
        else:
            return {"success": False, "message": f"暂不支持 {ch.channel} 渠道测试",
                    "sent_at": sent_at}
    except Exception as e:
        return {"success": False, "message": f"{type(e).__name__}: {e}", "sent_at": sent_at}


async def _test_feishu(cred: dict, sent_at: datetime) -> dict:
    """飞书测试:发送一张简单卡片"""
    import requests

    webhook_url = cred["webhook_url"]
    payload = {
        "msg_type": "interactive",
        "card": {
            "elements": [
                {"tag": "div", "text": {
                    "content": "NewsRadar 测试卡片 ✓\n该渠道工作正常。",
                    "tag": "lark_md",
                }},
            ],
            "header": {
                "title": {"content": "NewsRadar 测试", "tag": "plain_text"},
                "template": "blue",
            },
        },
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code != 200:
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "sent_at": sent_at}
    data = resp.json()
    if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
        return {"success": False, "message": f"飞书返回: {data}", "sent_at": sent_at}
    return {"success": True, "message": "飞书测试卡片已送达", "sent_at": sent_at}


async def _test_email(cred: dict, sent_at: datetime) -> dict:
    """邮件测试:MVP 阶段简化,使用全局 SMTP"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from app.config import get_settings
    settings = get_settings()
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        return {"success": False, "message": "未配置全局 SMTP(SMTP_HOST/SMTP_USER)",
                "sent_at": sent_at}

    to_email = cred["to_email"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "NewsRadar 测试邮件"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText("NewsRadar 渠道测试 ✓\n该邮箱可正常接收推送。", "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            s.sendmail(msg["From"], [to_email], msg.as_string())
        return {"success": True, "message": f"测试邮件已发送到 {to_email}",
                "sent_at": sent_at}
    except Exception as e:
        return {"success": False, "message": f"SMTP 错误: {e}", "sent_at": sent_at}


async def _test_telegram(cred: dict, sent_at: datetime) -> dict:
    import requests
    token, chat_id = cred["bot_token"], cred["chat_id"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": "NewsRadar 渠道测试 ✓",
    }, timeout=10)
    if resp.status_code != 200:
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "sent_at": sent_at}
    return {"success": True, "message": "Telegram 测试消息已送达", "sent_at": sent_at}


async def _test_webhook(cred: dict, sent_at: datetime) -> dict:
    import requests
    resp = requests.request(
        method=cred.get("method", "POST"),
        url=cred["url"],
        json={"test": True, "source": "newsradar"},
        timeout=10,
    )
    return {"success": resp.status_code < 400,
            "message": f"HTTP {resp.status_code}", "sent_at": sent_at}
