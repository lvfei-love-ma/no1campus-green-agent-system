import random
import smtplib
from email.mime.text import MIMEText
from utils.config import smtp_host, smtp_port, smtp_user, smtp_password


class EmailService:
    def __init__(self):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password

    def generate_code(self) -> str:
        return "".join(random.choices("0123456789", k=6))

    def send_vcode(self, to_email: str, code: str) -> bool:
        try:
            text_content = f"您好！您的验证码是：{code}"
            msg = MIMEText(text_content, "plain", "utf-8")
            msg["Subject"] = "邮箱验证码"
            msg["From"] = self.smtp_user
            msg["To"] = to_email
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [to_email], msg.as_string())
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False
