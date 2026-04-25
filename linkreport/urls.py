from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('reports/', views.create_report, name='create_report'),
    path('reports/<uuid:pk>/', views.report_detail, name='report_detail'),
    path('reports/<uuid:pk>/status/', views.report_status, name='report_status'),
    path('reports/<uuid:pk>/pdf/', views.download_pdf, name='download_pdf'),

    # Auth pages
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Auth API (JWT)
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]