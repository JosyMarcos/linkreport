from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core import views
from core.api import RegisterAPIView, MeAPIView, ReportViewSet, LinkResultViewSet

router = DefaultRouter()
router.register(r'reports', ReportViewSet, basename='api-reports')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # HTML pages
    path('', views.landing, name='landing'),
    path('app/', views.index, name='index'),
    path('reports/', views.create_report, name='create_report'),
    path('app/report/<uuid:pk>/', views.report_detail, name='report_detail'),
    path('reports/<uuid:pk>/status/', views.report_status, name='report_status'),
    path('reports/<uuid:pk>/pdf/', views.download_pdf, name='download_pdf'),
    path('reports/<uuid:pk>/csv/', views.download_csv, name='download_csv'),
    # Auth pages
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # API v1
    path('api/v1/', include(router.urls)),
    path('api/v1/reports/<uuid:report_pk>/results/', LinkResultViewSet.as_view({'get': 'list'}), name='api-results'),

    # Auth API
    path('api/v1/auth/register/', RegisterAPIView.as_view(), name='api-register'),
    path('api/v1/auth/me/', MeAPIView.as_view(), name='api-me'),
    path('api/v1/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Swagger docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]handler404 = 'core.views.custom_404'
