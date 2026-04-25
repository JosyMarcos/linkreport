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