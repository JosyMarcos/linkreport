from django.contrib import admin
from .models import Report, LinkResult

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'total_links', 'created_at']
    list_filter = ['status']

@admin.register(LinkResult)
class LinkResultAdmin(admin.ModelAdmin):
    list_display = ['url', 'status_code', 'response_ms', 'report']