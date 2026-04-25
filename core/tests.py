import pytest
from django.urls import reverse
from core.models import Report, LinkResult


@pytest.mark.django_db
class TestReportModel:

    def test_create_report(self):
        report = Report.objects.create(title='Teste')
        assert report.status == Report.Status.PENDING
        assert report.total_links == 0

    def test_report_ok_count(self):
        report = Report.objects.create(title='Teste')
        LinkResult.objects.create(report=report, url='https://google.com', status_code=200)
        LinkResult.objects.create(report=report, url='https://broken.com', status_code=404)
        assert report.ok_count == 1
        assert report.error_count == 1

    def test_report_str(self):
        report = Report.objects.create(title='Meu relatório')
        assert 'Meu relatório' in str(report)


@pytest.mark.django_db
class TestReportViews:

    def test_index_returns_200(self, client):
        response = client.get(reverse('index'))
        assert response.status_code == 200

    def test_create_report_empty_urls(self, client):
        response = client.post(reverse('create_report'), {'urls': '', 'title': 'teste'})
        assert response.status_code == 400

    def test_create_report_too_many_urls(self, client):
        urls = '\n'.join([f'https://site{i}.com' for i in range(51)])
        response = client.post(reverse('create_report'), {'urls': urls, 'title': 'teste'})
        assert response.status_code == 400


@pytest.mark.django_db
class TestLinkResultModel:

    def test_is_ok_true(self):
        report = Report.objects.create(title='Teste')
        lr = LinkResult.objects.create(report=report, url='https://google.com', status_code=200)
        assert lr.is_ok is True

    def test_is_ok_false_for_404(self):
        report = Report.objects.create(title='Teste')
        lr = LinkResult.objects.create(report=report, url='https://broken.com', status_code=404)
        assert lr.is_ok is False

    def test_status_label_with_error(self):
        report = Report.objects.create(title='Teste')
        lr = LinkResult.objects.create(report=report, url='https://broken.com', error_msg='Timeout')
        assert lr.status_label == 'Erro de conexão'

from unittest.mock import patch, MagicMock
from django.urls import reverse
from core.tasks import scrape_report


@pytest.mark.django_db
class TestScrapeTask:

    @patch('core.tasks.requests.Session')
    def test_scrape_success(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.text = '<html><head><title>Test Page</title><meta name="description" content="Test desc"></head></html>'
        mock_session.return_value.get.return_value = mock_resp

        report = Report.objects.create(title='Scrape test', status=Report.Status.RUNNING)
        LinkResult.objects.create(report=report, url='https://test.com')

        scrape_report(str(report.id))

        report.refresh_from_db()
        lr = report.results.first()
        assert report.status == Report.Status.DONE
        assert lr.status_code == 200
        assert lr.page_title == 'Test Page'
        assert lr.description == 'Test desc'

    @patch('core.tasks.requests.Session')
    def test_scrape_timeout(self, mock_session):
        import requests as req
        mock_session.return_value.get.side_effect = req.exceptions.Timeout

        report = Report.objects.create(title='Timeout test', status=Report.Status.RUNNING)
        LinkResult.objects.create(report=report, url='https://slow.com')

        scrape_report(str(report.id))

        lr = report.results.first()
        lr.refresh_from_db()
        assert lr.error_msg == 'Timeout'

    @patch('core.tasks.requests.Session')
    def test_scrape_connection_error(self, mock_session):
        import requests as req
        mock_session.return_value.get.side_effect = req.exceptions.ConnectionError

        report = Report.objects.create(title='Connection test', status=Report.Status.RUNNING)
        LinkResult.objects.create(report=report, url='https://broken.com')

        scrape_report(str(report.id))

        lr = report.results.first()
        lr.refresh_from_db()
        assert lr.error_msg == 'Erro de conexão'

    @patch('core.tasks.requests.Session')
    def test_scrape_404(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_session.return_value.get.return_value = mock_resp

        report = Report.objects.create(title='404 test', status=Report.Status.RUNNING)
        LinkResult.objects.create(report=report, url='https://notfound.com')

        scrape_report(str(report.id))

        report.refresh_from_db()
        assert report.status == Report.Status.DONE


@pytest.mark.django_db
class TestReportViewsExtended:

    def test_report_detail_returns_200(self, client):
        report = Report.objects.create(title='Detail test', status=Report.Status.DONE)
        response = client.get(reverse('report_detail', args=[report.id]))
        assert response.status_code == 200

    def test_report_status_endpoint(self, client):
        report = Report.objects.create(title='Status test', status=Report.Status.DONE)
        response = client.get(reverse('report_status', args=[report.id]))
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        assert 'percent' in data

    def test_download_pdf_returns_pdf(self, client):
        report = Report.objects.create(title='PDF test', status=Report.Status.DONE)
        LinkResult.objects.create(report=report, url='https://test.com', status_code=200)
        response = client.get(reverse('download_pdf', args=[report.id]))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'

    def test_create_report_valid(self, client):
        with patch('core.views.scrape_report') as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(reverse('create_report'), {
                'urls': 'https://google.com\nhttps://github.com',
                'title': 'Valid test'
            })
            assert response.status_code == 201
            data = response.json()
            assert 'report_id' in data