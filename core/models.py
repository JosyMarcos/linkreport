import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class Report(models.Model):
    """
    Representa um relatório gerado pelo usuário.
    Cada relatório agrupa N URLs enviadas de uma vez.
    """

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Aguardando'
        RUNNING  = 'running',  'Processando'
        DONE     = 'done',     'Concluído'
        ERROR    = 'error',    'Erro'
      
    owner      = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='reports', null=True, blank=True
    )
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title      = models.CharField(max_length=120, blank=True, default='')
    status     = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Relatório'
        verbose_name_plural = 'Relatórios'

    def __str__(self):
        label = self.title or str(self.id)[:8]
        return f'[{self.get_status_display()}] {label}'

    @property
    def total_links(self):
        return self.results.count()

    @property
    def ok_count(self):
        return self.results.filter(status_code__gte=200, status_code__lt=300).count()

    @property
    def error_count(self):
        return self.results.exclude(status_code__gte=200, status_code__lt=300).count()


class LinkResult(models.Model):
    """
    Resultado da verificação de uma URL individual dentro de um Report.
    """

    report      = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='results')
    url         = models.URLField(max_length=2048)
    status_code = models.IntegerField(null=True, blank=True)
    page_title  = models.CharField(max_length=512, blank=True, default='')
    description = models.TextField(blank=True, default='')
    error_msg   = models.CharField(max_length=512, blank=True, default='')
    response_ms = models.IntegerField(null=True, blank=True, help_text='Tempo de resposta em ms')
    checked_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Resultado'
        verbose_name_plural = 'Resultados'

    def __str__(self):
        return f'{self.status_code} — {self.url[:60]}'

    @property
    def is_ok(self):
        return self.status_code is not None and 200 <= self.status_code < 300

    @property
    def status_label(self):
        if self.error_msg:
            return 'Erro de conexão'
        if self.status_code is None:
            return 'Não verificado'
        return str(self.status_code)
