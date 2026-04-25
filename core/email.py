import logging
import requests
from django.conf import settings

logger = logging.getLogger('core')


def send_report_ready_email(user, report):
    if not user.email or not settings.SENDGRID_API_KEY:
        return

    body_html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 520px; margin: 0 auto; padding: 2rem;">
      <h2 style="font-size: 1.3rem; font-weight: 700; color: #0a0a0f; margin-bottom: 0.5rem;">
        Your report is ready ✓
      </h2>
      <p style="color: #6b6b80; margin-bottom: 1.5rem;">
        <strong>{report.title}</strong> finished processing.
      </p>
      <div style="background: #f8f8f8; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 6px 0; color: #6b6b80; font-size: 0.85rem;">Total URLs</td>
            <td style="text-align: right; font-weight: 600;">{report.total_links}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #6b6b80; font-size: 0.85rem;">OK (2xx)</td>
            <td style="text-align: right; font-weight: 600; color: #22c55e;">{report.ok_count}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #6b6b80; font-size: 0.85rem;">Errors</td>
            <td style="text-align: right; font-weight: 600; color: #ef4444;">{report.error_count}</td>
          </tr>
        </table>
      </div>
      <a href="https://linkreport-production.up.railway.app/reports/{report.id}/"
         style="display: inline-block; background: #6c63ff; color: white; padding: 12px 24px;
                border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.9rem;">
        View full report →
      </a>
      <p style="margin-top: 2rem; font-size: 0.75rem; color: #aaa;">
        LinkReport · You're receiving this because you created a report.
      </p>
    </div>
    """

    payload = {
        "personalizations": [{"to": [{"email": user.email}]}],
        "from": {"email": settings.DEFAULT_FROM_EMAIL, "name": "LinkReport"},
        "subject": f"✓ Report ready: {report.title}",
        "content": [{"type": "text/html", "value": body_html}],
    }

    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            verify=False,
            timeout=10,
        )
        if response.status_code == 202:
            logger.info(f'Email sent to {user.email}')
        else:
            logger.error(f'SendGrid error {response.status_code}: {response.text}')
    except Exception as e:
        logger.error(f'Failed to send email to {user.email}: {e}')