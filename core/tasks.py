import time
import requests
from bs4 import BeautifulSoup
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from .models import Report, LinkResult

@shared_task
def scrape_report(report_id):
    report = Report.objects.get(id=report_id)
    link_results = list(report.results.all())

    session = requests.Session()
    session.headers.update({'User-Agent': settings.SCRAPER_USER_AGENT})

    for lr in link_results:
        start = time.monotonic()
        try:
            resp = session.get(lr.url, timeout=settings.SCRAPER_TIMEOUT, allow_redirects=True)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            lr.status_code = resp.status_code
            lr.response_ms = elapsed_ms

            if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type', ''):
                soup = BeautifulSoup(resp.text, 'html.parser')
                if soup.title:
                    lr.page_title = soup.title.string.strip()[:512]
                meta = soup.find('meta', attrs={'name': 'description'})
                if meta and meta.get('content'):
                    lr.description = meta['content'].strip()[:1000]

        except requests.exceptions.Timeout:
            lr.error_msg = 'Timeout'
        except requests.exceptions.ConnectionError:
            lr.error_msg = 'Erro de conexão'
        except requests.exceptions.RequestException as e:
            lr.error_msg = str(e)[:512]

        lr.checked_at = timezone.now()
        lr.save()

    has_error = all(lr.error_msg for lr in link_results)
    report.status = Report.Status.ERROR if has_error else Report.Status.DONE
    report.save()