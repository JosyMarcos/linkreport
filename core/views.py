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

from .models import Report, LinkResult


# ─── Páginas HTML ─────────────────────────────────────────────────────────────

def index(request):
    """Página inicial com formulário para colar URLs."""
    reports = Report.objects.all()[:10]
    return render(request, 'index.html', {'reports': reports})


def report_detail(request, pk):
    """Página de detalhe de um relatório."""
    report = get_object_or_404(Report, pk=pk)
    return render(request, 'report.html', {'report': report})


# ─── API ──────────────────────────────────────────────────────────────────────

@require_POST
def create_report(request):
    """
    Recebe um POST com campo 'urls' (uma por linha) e 'title' opcional.
    Cria o Report, processa as URLs de forma síncrona por enquanto
    (depois vira task Celery) e retorna o ID do relatório.
    """
    raw_urls = request.POST.get('urls', '')
    title    = request.POST.get('title', '').strip()

    urls = [u.strip() for u in raw_urls.splitlines() if u.strip()]

    if not urls:
        return JsonResponse({'error': 'Nenhuma URL informada.'}, status=400)

    if len(urls) > 50:
        return JsonResponse({'error': 'Máximo de 50 URLs por relatório.'}, status=400)

    # Cria o relatório
    report = Report.objects.create(
        title=title or f'Relatório — {len(urls)} links',
        status=Report.Status.RUNNING,
    )

    # Cria os LinkResult em branco para cada URL
    link_results = LinkResult.objects.bulk_create([
        LinkResult(report=report, url=url) for url in urls
    ])

    # Processa cada URL (síncrono por ora — virar task Celery no próximo passo)
    _scrape_report(report, link_results)

    return JsonResponse({'report_id': str(report.id)}, status=201)


def report_status(request, pk):
    """Endpoint de polling: retorna status e progresso do relatório."""
    report = get_object_or_404(Report, pk=pk)
    done   = report.results.exclude(checked_at=None).count()
    total  = report.total_links

    return JsonResponse({
        'status':   report.status,
        'done':     done,
        'total':    total,
        'percent':  round(done / total * 100) if total else 0,
    })


# ─── Geração de PDF ───────────────────────────────────────────────────────────

def download_pdf(request, pk):
    """Gera e devolve o relatório em PDF usando ReportLab."""
    report  = get_object_or_404(Report, pk=pk)
    results = report.results.all()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="report-{str(report.id)[:8]}.pdf"'

    doc    = SimpleDocTemplate(response, pagesize=A4, rightMargin=40, leftMargin=40,
                                topMargin=60, bottomMargin=40)
    styles = getSampleStyleSheet()
    story  = []

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                  fontSize=18, spaceAfter=4)
    meta_style  = ParagraphStyle('Meta', parent=styles['Normal'],
                                  fontSize=10, textColor=colors.grey, spaceAfter=16)

    story.append(Paragraph(report.title or 'Relatório de Links', title_style))
    story.append(Paragraph(
        f'Gerado em {report.updated_at.strftime("%d/%m/%Y %H:%M")} · '
        f'{report.ok_count} OK · {report.error_count} com erro · {report.total_links} total',
        meta_style,
    ))
    story.append(Spacer(1, 8))

    # ── Tabela de resultados ──────────────────────────────────────────────────
    col_url    = 260
    col_status = 55
    col_title  = 160
    col_time   = 55

    header = ['URL', 'Status', 'Título da página', 'Tempo (ms)']
    rows   = [header]

    for r in results:
        rows.append([
            Paragraph(r.url, styles['Normal']),
            str(r.status_code or r.error_msg or '—'),
            Paragraph(r.page_title or '—', styles['Normal']),
            str(r.response_ms or '—'),
        ])

    table = Table(rows, colWidths=[col_url, col_status, col_title, col_time])
    table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING',    (0, 0), (-1, 0), 8),
        # Corpo
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('TOPPADDING',    (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
        # Bordas
        ('GRID',          (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))

    story.append(table)
    doc.build(story)
    return response


# ─── Scraping (síncrono — será movido para tasks.py com Celery) ───────────────

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

    # Atualiza status do relatório
    has_error = link_results and all(lr.error_msg for lr in link_results)
    report.status = Report.Status.ERROR if has_error else Report.Status.DONE
    report.save()
