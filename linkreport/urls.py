from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('reports/', views.create_report, name='create_report'),
    path('reports/<uuid:pk>/', views.report_detail, name='report_detail'),
    path('reports/<uuid:pk>/status/', views.report_status, name='report_status'),
    path('reports/<uuid:pk>/pdf/', views.download_pdf, name='download_pdf'),
]