import logging
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from .models import Report, LinkResult
from .serializers import (
    CreateReportSerializer, LinkResultSerializer,
    RegisterSerializer, ReportListSerializer,
    ReportSerializer, UserSerializer,
)
from .tasks import scrape_report
from .views import _generate_pdf

logger = logging.getLogger('core')


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserSerializer},
        summary='Register a new user',
        tags=['auth'],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info(f'New user registered via API: {user.username}')
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: UserSerializer},
        summary='Get current user info',
        tags=['auth'],
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ─── Reports ─────────────────────────────────────────────────────────────────

class ReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Report.objects.filter(owner=self.request.user).prefetch_related('results')

    def get_serializer_class(self):
        if self.action == 'list':
            return ReportListSerializer
        return ReportSerializer

    @extend_schema(
        responses={200: ReportListSerializer(many=True)},
        summary='List all reports for the current user',
        tags=['reports'],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: ReportSerializer},
        summary='Get a report with all results',
        tags=['reports'],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        responses={204: None},
        summary='Delete a report',
        tags=['reports'],
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        request=CreateReportSerializer,
        responses={
            201: ReportSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
        summary='Create a new report and start URL checking',
        tags=['reports'],
    )
    @action(detail=False, methods=['post'], url_path='create')
    def create_report(self, request):
        serializer = CreateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_urls = serializer.validated_data['urls']
        title    = serializer.validated_data.get('title', '')
        urls     = [u.strip() for u in raw_urls.splitlines() if u.strip()]

        report = Report.objects.create(
            title=title or f'Report — {len(urls)} links',
            status=Report.Status.RUNNING,
            owner=request.user,
        )

        LinkResult.objects.bulk_create([
            LinkResult(report=report, url=url) for url in urls
        ])

        scrape_report.delay(str(report.id))
        logger.info(f'Report {report.id} created by {request.user.username} with {len(urls)} URLs')

        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: OpenApiResponse(description='Report status and progress')},
        summary='Get report processing status',
        tags=['reports'],
    )
    @action(detail=True, methods=['get'], url_path='status')
    def report_status(self, request, pk=None):
        report = self.get_object()
        done   = report.results.exclude(checked_at=None).count()
        total  = report.total_links
        return Response({
            'status':  report.status,
            'done':    done,
            'total':   total,
            'percent': round(done / total * 100) if total else 0,
        })

    @extend_schema(
        responses={200: OpenApiResponse(description='PDF file download')},
        summary='Download report as PDF',
        tags=['reports'],
    )
    @action(detail=True, methods=['get'], url_path='pdf')
    def download_pdf(self, request, pk=None):
        report   = self.get_object()
        pdf_file = _generate_pdf(report)
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report-{str(report.id)[:8]}.pdf"'
        return response


# ─── Link Results ─────────────────────────────────────────────────────────────

class LinkResultViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LinkResultSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: LinkResultSerializer(many=True)},
        summary='List all results for a specific report',
        tags=['results'],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        report = get_object_or_404(
            Report,
            pk=self.kwargs['report_pk'],
            owner=self.request.user,
        )
        return LinkResult.objects.filter(report=report)
