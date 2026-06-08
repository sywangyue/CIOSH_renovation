"""
163 SMTP 邮件发送：standalone，无 Flask 依赖。
"""

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

from config import get_config


def send_report(subject: str, html_body: str) -> bool:
    """
    发送 HTML 日报/周报邮件。
    收件人从 config.MAIL_TO 读取，抄送从 config.MAIL_CC 读取（可为空）。
    DRY_RUN=1 时仅打印预览，不实际发送。
    返回是否成功。
    """
    cfg = get_config()
    cc = cfg.MAIL_CC.strip() if cfg.MAIL_CC else ""

    if os.getenv("DRY_RUN", "0") == "1":
        print("【DRY_RUN=1】跳过真实发送。")
        print(f"  收件人：{cfg.MAIL_TO}")
        if cc:
            print(f"  抄送：{cc}")
        print(f"  主题：{subject}")
        print(f"  HTML 长度：{len(html_body)} 字符")
        return True

    if not all([cfg.SMTP_USER, cfg.SMTP_PASSWORD, cfg.MAIL_TO]):
        print("SMTP 配置不完整（SMTP_USER / SMTP_PASSWORD / MAIL_TO），跳过发送")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.SMTP_USER
    msg["To"] = cfg.MAIL_TO
    if cc:
        msg["Cc"] = cc
    msg.set_content(f"请使用支持 HTML 的邮件客户端查看本邮件。\n\n{subject}")
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT) as server:
            server.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"邮件发送成功：{subject}（To: {cfg.MAIL_TO}" + (f"  Cc: {cc}" if cc else "") + "）")
        return True
    except Exception as e:
        print(f"邮件发送失败：{e}")
        return False
