"""
Email service for Chronos Engine - HTML/Text emails with templates
Simple and secure email sending with template support
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import re
import json
import asyncio
from pathlib import Path

from src.core.schema_extensions import EmailTemplateDB, EmailLogDB


@dataclass
class EmailAddress:
    """Email address with optional display name"""
    email: str
    name: Optional[str] = None

    def __str__(self):
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email


@dataclass
class EmailAttachment:
    """Email attachment"""
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass
class EmailMessage:
    """Email message model"""
    to: List[EmailAddress]
    subject: str
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    cc: List[EmailAddress] = field(default_factory=list)
    bcc: List[EmailAddress] = field(default_factory=list)
    reply_to: Optional[EmailAddress] = None
    attachments: List[EmailAttachment] = field(default_factory=list)
    priority: str = "normal"  # low, normal, high
    template_id: Optional[int] = None
    template_variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SMTPConfig:
    """SMTP configuration"""
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30
    from_email: str = ""
    from_name: Optional[str] = None


@dataclass
class EmailTemplate:
    """Email template domain model"""
    id: Optional[int] = None
    name: str = ""
    subject_template: str = ""
    html_body_template: Optional[str] = None
    text_body_template: Optional[str] = None
    variables: List[str] = field(default_factory=list)
    category: str = "general"
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    def to_db_model(self) -> EmailTemplateDB:
        """Convert to database model"""
        return EmailTemplateDB(
            id=self.id,
            name=self.name,
            subject_template=self.subject_template,
            html_body_template=self.html_body_template,
            text_body_template=self.text_body_template,
            variables=self.variables,
            category=self.category,
            enabled=self.enabled,
            created_at=self.created_at,
            updated_at=self.updated_at,
            created_by=self.created_by
        )


class TemplateEngine:
    """Simple template engine for email templates"""

    def __init__(self):
        self.variable_pattern = re.compile(r'\{\{(\w+(?:\.\w+)*)\}\}')

    def render(self, template: str, variables: Dict[str, Any]) -> str:
        """Render template with variables"""
        def replace_var(match):
            var_path = match.group(1)
            value = self._get_nested_value(variables, var_path)
            return str(value) if value is not None else match.group(0)

        return self.variable_pattern.sub(replace_var, template)

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dictionary using dot notation"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def extract_variables(self, template: str) -> List[str]:
        """Extract variable names from template"""
        return list(set(match.group(1) for match in self.variable_pattern.finditer(template)))


class EmailService:
    """Email service with template support"""

    def __init__(self, smtp_config: SMTPConfig, db_session_factory=None):
        self.smtp_config = smtp_config
        self.db_session_factory = db_session_factory
        self.template_engine = TemplateEngine()

    async def send_email(self, message: EmailMessage) -> bool:
        """Send email message"""
        try:
            # Resolve template if specified
            if message.template_id and self.db_session_factory:
                template = await self._get_template(message.template_id)
                if template:
                    message = await self._apply_template(message, template)

            # Send email
            success = await self._send_smtp(message)

            # Log email
            if self.db_session_factory:
                await self._log_email(message, "sent" if success else "failed")

            return success

        except Exception as e:
            if self.db_session_factory:
                await self._log_email(message, "failed", str(e))
            raise

    async def send_template_email(self, template_id: int, to: List[Union[str, EmailAddress]],
                                 variables: Dict[str, Any], **kwargs) -> bool:
        """Send email using template"""
        # Convert string emails to EmailAddress objects
        to_addresses = []
        for addr in to:
            if isinstance(addr, str):
                to_addresses.append(EmailAddress(email=addr))
            else:
                to_addresses.append(addr)

        message = EmailMessage(
            to=to_addresses,
            subject="",  # Will be filled from template
            template_id=template_id,
            template_variables=variables,
            **kwargs
        )

        return await self.send_email(message)

    async def test_connection(self) -> bool:
        """Test SMTP connection"""
        try:
            await asyncio.to_thread(self._test_smtp_connection)
            return True
        except Exception:
            return False

    def _test_smtp_connection(self):
        """Test SMTP connection (synchronous)"""
        if self.smtp_config.use_ssl:
            server = smtplib.SMTP_SSL(self.smtp_config.host, self.smtp_config.port,
                                    timeout=self.smtp_config.timeout)
        else:
            server = smtplib.SMTP(self.smtp_config.host, self.smtp_config.port,
                                timeout=self.smtp_config.timeout)

        try:
            if self.smtp_config.use_tls and not self.smtp_config.use_ssl:
                server.starttls(context=ssl.create_default_context())

            if self.smtp_config.username and self.smtp_config.password:
                server.login(self.smtp_config.username, self.smtp_config.password)

            server.quit()
        except Exception:
            server.quit()
            raise

    async def _send_smtp(self, message: EmailMessage) -> bool:
        """Send email via SMTP (asynchronous wrapper)"""
        return await asyncio.to_thread(self._send_smtp_sync, message)

    def _send_smtp_sync(self, message: EmailMessage) -> bool:
        """Send email via SMTP (synchronous)"""
        # Create MIME message
        mime_msg = MIMEMultipart('alternative')
        mime_msg['Subject'] = message.subject
        mime_msg['From'] = f"{self.smtp_config.from_name} <{self.smtp_config.from_email}>" if self.smtp_config.from_name else self.smtp_config.from_email
        mime_msg['To'] = ", ".join(str(addr) for addr in message.to)

        if message.cc:
            mime_msg['Cc'] = ", ".join(str(addr) for addr in message.cc)

        if message.reply_to:
            mime_msg['Reply-To'] = str(message.reply_to)

        # Set priority
        if message.priority == "high":
            mime_msg['X-Priority'] = '1'
            mime_msg['X-MSMail-Priority'] = 'High'
        elif message.priority == "low":
            mime_msg['X-Priority'] = '5'
            mime_msg['X-MSMail-Priority'] = 'Low'

        # Add text body
        if message.text_body:
            text_part = MIMEText(message.text_body, 'plain', 'utf-8')
            mime_msg.attach(text_part)

        # Add HTML body
        if message.html_body:
            html_part = MIMEText(message.html_body, 'html', 'utf-8')
            mime_msg.attach(html_part)

        # Add attachments
        for attachment in message.attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {attachment.filename}'
            )
            mime_msg.attach(part)

        # Connect and send
        if self.smtp_config.use_ssl:
            server = smtplib.SMTP_SSL(self.smtp_config.host, self.smtp_config.port,
                                    timeout=self.smtp_config.timeout)
        else:
            server = smtplib.SMTP(self.smtp_config.host, self.smtp_config.port,
                                timeout=self.smtp_config.timeout)

        try:
            if self.smtp_config.use_tls and not self.smtp_config.use_ssl:
                server.starttls(context=ssl.create_default_context())

            if self.smtp_config.username and self.smtp_config.password:
                server.login(self.smtp_config.username, self.smtp_config.password)

            # Get all recipients
            recipients = [addr.email for addr in message.to]
            recipients.extend([addr.email for addr in message.cc])
            recipients.extend([addr.email for addr in message.bcc])

            server.send_message(mime_msg, to_addrs=recipients)
            server.quit()
            return True

        except Exception:
            server.quit()
            raise

    async def _get_template(self, template_id: int) -> Optional[EmailTemplate]:
        """Get email template from database"""
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            result = await session.execute(
                select(EmailTemplateDB).where(
                    EmailTemplateDB.id == template_id,
                    EmailTemplateDB.enabled == True
                )
            )
            db_template = result.scalar_one_or_none()
            if not db_template:
                return None

            return EmailTemplate(
                id=db_template.id,
                name=db_template.name,
                subject_template=db_template.subject_template,
                html_body_template=db_template.html_body_template,
                text_body_template=db_template.text_body_template,
                variables=db_template.variables or [],
                category=db_template.category,
                enabled=db_template.enabled,
                created_at=db_template.created_at,
                updated_at=db_template.updated_at,
                created_by=db_template.created_by
            )

    async def _apply_template(self, message: EmailMessage, template: EmailTemplate) -> EmailMessage:
        """Apply template to message"""
        variables = message.template_variables

        # Render subject
        message.subject = self.template_engine.render(template.subject_template, variables)

        # Render bodies
        if template.html_body_template:
            message.html_body = self.template_engine.render(template.html_body_template, variables)

        if template.text_body_template:
            message.text_body = self.template_engine.render(template.text_body_template, variables)

        return message

    async def _log_email(self, message: EmailMessage, status: str, error_message: Optional[str] = None):
        """Log email sending to database"""
        for recipient in message.to:
            log_entry = EmailLogDB(
                recipient=recipient.email,
                subject=message.subject,
                template_id=message.template_id,
                status=status,
                error_message=error_message,
                sent_at=datetime.utcnow()
            )

            async with self.db_session_factory() as session:
                session.add(log_entry)
                await session.commit()

    # Template management methods

    async def create_template(self, template: EmailTemplate) -> int:
        """Create email template"""
        async with self.db_session_factory() as session:
            db_template = template.to_db_model()
            session.add(db_template)
            await session.commit()
            await session.refresh(db_template)
            return db_template.id

    async def get_templates(self, category: Optional[str] = None) -> List[EmailTemplate]:
        """Get email templates"""
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            query = select(EmailTemplateDB).where(EmailTemplateDB.enabled == True)
            if category:
                query = query.where(EmailTemplateDB.category == category)

            result = await session.execute(query.order_by(EmailTemplateDB.name))
            db_templates = result.scalars().all()

            return [self._db_to_template(template) for template in db_templates]

    async def preview_template(self, template_id: int, variables: Dict[str, Any]) -> Dict[str, str]:
        """Preview rendered template"""
        template = await self._get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        preview = {
            'subject': self.template_engine.render(template.subject_template, variables)
        }

        if template.html_body_template:
            preview['html_body'] = self.template_engine.render(template.html_body_template, variables)

        if template.text_body_template:
            preview['text_body'] = self.template_engine.render(template.text_body_template, variables)

        return preview

    def _db_to_template(self, db_template: EmailTemplateDB) -> EmailTemplate:
        """Convert database model to domain model"""
        return EmailTemplate(
            id=db_template.id,
            name=db_template.name,
            subject_template=db_template.subject_template,
            html_body_template=db_template.html_body_template,
            text_body_template=db_template.text_body_template,
            variables=db_template.variables or [],
            category=db_template.category,
            enabled=db_template.enabled,
            created_at=db_template.created_at,
            updated_at=db_template.updated_at,
            created_by=db_template.created_by
        )


# Email configuration loader
def load_smtp_config_from_env() -> SMTPConfig:
    """Load SMTP configuration from environment variables"""
    import os

    return SMTPConfig(
        host=os.getenv('SMTP_HOST', 'localhost'),
        port=int(os.getenv('SMTP_PORT', '587')),
        username=os.getenv('SMTP_USERNAME', ''),
        password=os.getenv('SMTP_PASSWORD', ''),
        use_tls=os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
        use_ssl=os.getenv('SMTP_USE_SSL', 'false').lower() == 'true',
        from_email=os.getenv('SMTP_FROM_EMAIL', 'noreply@chronos.local'),
        from_name=os.getenv('SMTP_FROM_NAME', 'Chronos Engine')
    )


# Default template for notifications
DEFAULT_NOTIFICATION_TEMPLATE = {
    'name': 'Default Notification',
    'subject_template': 'Chronos Notification: {{title}}',
    'html_body_template': '''
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #ff6d5a;">{{title}}</h2>
        <p>{{message}}</p>

        {{#if event.title}}
        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
            <h3>Event Details:</h3>
            <p><strong>Title:</strong> {{event.title}}</p>
            {{#if event.start_time}}<p><strong>Start:</strong> {{event.start_time}}</p>{{/if}}
            {{#if event.location}}<p><strong>Location:</strong> {{event.location}}</p>{{/if}}
        </div>
        {{/if}}

        <hr style="margin: 20px 0;">
        <p style="color: #666; font-size: 12px;">
            This email was sent by Chronos Engine.<br>
            Time: {{timestamp}}
        </p>
    </body>
    </html>
    ''',
    'text_body_template': '''
    {{title}}

    {{message}}

    {{#if event.title}}
    Event Details:
    - Title: {{event.title}}
    {{#if event.start_time}}- Start: {{event.start_time}}{{/if}}
    {{#if event.location}}- Location: {{event.location}}{{/if}}
    {{/if}}

    ---
    Sent by Chronos Engine at {{timestamp}}
    ''',
    'category': 'notification'
}
