from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Report, LinkResult


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LinkResultSerializer(serializers.ModelSerializer):
    is_ok = serializers.BooleanField(read_only=True)
    status_label = serializers.CharField(read_only=True)

    class Meta:
        model = LinkResult
        fields = [
            'id', 'url', 'status_code', 'page_title',
            'description', 'error_msg', 'response_ms',
            'checked_at', 'is_ok', 'status_label',
        ]
        read_only_fields = fields


class ReportSerializer(serializers.ModelSerializer):
    total_links = serializers.IntegerField(read_only=True)
    ok_count    = serializers.IntegerField(read_only=True)
    error_count = serializers.IntegerField(read_only=True)
    results     = LinkResultSerializer(many=True, read_only=True)
    owner       = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Report
        fields = [
            'id', 'title', 'status', 'owner',
            'created_at', 'updated_at',
            'total_links', 'ok_count', 'error_count',
            'results',
        ]
        read_only_fields = [
            'id', 'status', 'owner', 'created_at', 'updated_at',
            'total_links', 'ok_count', 'error_count', 'results',
        ]


class ReportListSerializer(serializers.ModelSerializer):
    """Serializer leve para listagem — sem os resultados."""
    total_links = serializers.IntegerField(read_only=True)
    ok_count    = serializers.IntegerField(read_only=True)
    error_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Report
        fields = [
            'id', 'title', 'status', 'created_at',
            'total_links', 'ok_count', 'error_count',
        ]


class CreateReportSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    urls  = serializers.CharField(
        help_text='One URL per line. Maximum 50 URLs.'
    )

    def validate_urls(self, value):
        urls = [u.strip() for u in value.splitlines() if u.strip()]
        if not urls:
            raise serializers.ValidationError('At least one URL is required.')
        if len(urls) > 50:
            raise serializers.ValidationError('Maximum 50 URLs per report.')
        return value
