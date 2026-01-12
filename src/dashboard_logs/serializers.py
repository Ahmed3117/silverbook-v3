import json

from rest_framework import serializers

from dashboard_logs.models import DashboardRequestLog


class DashboardRequestLogSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    request_body = serializers.SerializerMethodField()
    response_body = serializers.SerializerMethodField()

    def _parse_json_text(self, value):
        if value is None:
            return None
        if value == '':
            return None

        # First parse
        try:
            parsed = json.loads(value)
        except Exception:
            return {'raw': value}

        # Handle legacy: JSON string that itself contains JSON
        if isinstance(parsed, str):
            s = parsed.strip()
            if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
                try:
                    return json.loads(s)
                except Exception:
                    return {'raw': parsed}

        return parsed

    def get_request_body(self, obj):
        return self._parse_json_text(obj.request_body)

    def get_response_body(self, obj):
        return self._parse_json_text(obj.response_body)

    class Meta:
        model = DashboardRequestLog
        fields = [
            'id',
            'requested_at',
            'method',
            'path',
            'request_body',
            'response_status',
            'response_body',
            'user_id',
            'username',
        ]
        read_only_fields = fields
