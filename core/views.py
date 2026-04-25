import time
import requests
from bs4 import BeautifulSoup

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core.tasks import scrape_report

from .models import Report, LinkResult


# ─── Páginas HTML ─────────────────────────────────────────────────────────────

def index(request):
    reports = Report.objects.filter(owner=request.user).order_by('-created_at')[:10] if request.user.is_authenticated else []
    return render(request, 'index.html', {'reports': reports})


def report_detail(request, pk):
    report = get_object_or_404(Report, pk=pk)
    return render(request, 'report.html', {'report': report})


# ─── API ──────────────────────────────────────────────────────────────────────

@require_POST
def create_report(request):

    raw_urls = request.POST.get('urls', '')
    title    = request.POST.get('title', '').strip()

    urls = [u.strip() for u in raw_urls.splitlines() if u.strip()]

    if not urls:
        return JsonResponse({'error': 'Nenhuma URL informada.'}, status=400)

    if len(urls) > 50:
        return JsonResponse({'error': 'Máximo de 50 URLs por relatório.'}, status=400)

    report = Report.objects.create(
        title=title or f'Report — {len(urls)} links',
        status=Report.Status.RUNNING,
        owner=request.user if request.user.is_authenticated else None,
    )

    link_results = LinkResult.objects.bulk_create([
        LinkResult(report=report, url=url) for url in urls
    ])
    
    from .tasks import scrape_report
    scrape_report.delay(str(report.id))

    return JsonResponse({'report_id': str(report.id)}, status=201)
    


def report_status(request, pk):
    report = get_object_or_404(Report, pk=pk)
    done   = report.results.exclude(checked_at=None).count()
    total  = report.total_links

    return JsonResponse({
        'status':   report.status,
        'done':     done,
        'total':    total,
        'percent':  round(done / total * 100) if total else 0,
    })



def _generate_pdf(report):
    """Gera o PDF e retorna os bytes."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    results = report.results.all()
    doc    = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40,
                                topMargin=60, bottomMargin=40)
    styles = getSampleStyleSheet()
    story  = []

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=4)
    meta_style  = ParagraphStyle('Meta', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#888888'), spaceAfter=16)

    story.append(Paragraph(report.title or 'Link Report', title_style))
    story.append(Paragraph(
        f'Generated {report.updated_at.strftime("%m/%d/%Y %H:%M")} · '
        f'{report.ok_count} OK · {report.error_count} errors · {report.total_links} total',
        meta_style,
    ))
    story.append(Spacer(1, 8))

    header = ['URL', 'Status', 'Page Title', 'Time (ms)']
    rows   = [header]
    for r in results:
        rows.append([
            Paragraph(r.url, styles['Normal']),
            str(r.status_code or r.error_msg or '—'),
            Paragraph(r.page_title or '—', styles['Normal']),
            str(r.response_ms or '—'),
        ])

    table = Table(rows, colWidths=[260, 55, 160, 55])
    table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#6c63ff')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING',    (0, 0), (-1, 0), 8),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('TOPPADDING',    (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
        ('GRID',          (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def download_pdf(request, pk):
    report   = get_object_or_404(Report, pk=pk)
    pdf_file = _generate_pdf(report)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="report-{str(report.id)[:8]}.pdf"'
    return response



def _scrape_report(report: Report, link_results: list[LinkResult]) -> None:
    """
    Percorre cada LinkResult, faz a requisição HTTP,
    extrai título e meta description, e salva no banco.
    """
    session = requests.Session()
    session.headers.update({'User-Agent': settings.SCRAPER_USER_AGENT})
    timeout = settings.SCRAPER_TIMEOUT

    for lr in link_results:
        start = time.monotonic()
        try:
            resp = session.get(lr.url, timeout=timeout, allow_redirects=True)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            lr.status_code = resp.status_code
            lr.response_ms = elapsed_ms

            # Extrai título e descrição apenas para respostas HTML com sucesso
            if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type', ''):
                soup = BeautifulSoup(resp.text, 'html.parser')

                if soup.title:
                    lr.page_title = soup.title.string.strip()[:512]

                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc and meta_desc.get('content'):
                    lr.description = meta_desc['content'].strip()[:1000]

        except requests.exceptions.Timeout:
            lr.error_msg = 'Timeout'
        except requests.exceptions.ConnectionError:
            lr.error_msg = 'Erro de conexão'
        except requests.exceptions.RequestException as e:
            lr.error_msg = str(e)[:512]

        lr.checked_at = timezone.now()
        lr.save()

    has_error = link_results and all(lr.error_msg for lr in link_results)
    report.status = Report.Status.ERROR if has_error else Report.Status.DONE
    report.save()

import logging
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect

logger = logging.getLogger('core')


def register(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        email    = request.POST.get('email', '').strip()

        if not username or not password:
            return JsonResponse({'error': 'Username and password are required.'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already taken.'}, status=400)

        user = User.objects.create_user(username=username, password=password, email=email)
        logger.info(f'New user registered: {username}')
        return JsonResponse({'message': 'User created successfully.'}, status=201)

    return render(request, 'register.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            logger.info(f'User logged in: {username}')
            return redirect('index')
        return render(request, 'login.html', {'error': 'Invalid credentials.'})
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')

def landing(request):
    if request.user.is_authenticated:
        return redirect('index')
    return render(request, 'landing.html')