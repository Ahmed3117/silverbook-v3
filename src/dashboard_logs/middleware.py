import json
import logging
from typing import Optional

from django.http import HttpRequest, HttpResponse

from rest_framework.settings import api_settings
from dashboard_logs.models import DashboardRequestLog

logger = logging.getLogger(__name__)


_MAX_BODY_CHARS = 20000


def _safe_decode_bytes(data: bytes) -> str:
    if not data:
        return ''
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return data.decode('utf-8', errors='replace')
        except Exception:
            return repr(data)


def _truncate(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= _MAX_BODY_CHARS:
        return text
    return text[:_MAX_BODY_CHARS] + '...<truncated>'


def _scrub_sensitive_obj(obj):
    if isinstance(obj, dict):
        scrub_keys = {
            'password',
            'pass',
            'token',
            'authorization',
            'auth',
            'secret',
            'refresh',
            'access',
        }
        scrubbed = {}
        for k, v in obj.items():
            if str(k).lower() in scrub_keys:
                scrubbed[k] = '<redacted>'
            else:
                scrubbed[k] = _scrub_sensitive_obj(v)
        return scrubbed

    if isinstance(obj, list):
        return [_scrub_sensitive_obj(v) for v in obj]

    return obj


def _maybe_parse_nested_json(parsed):
    if isinstance(parsed, str):
        s = parsed.strip()
        if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
            try:
                return json.loads(s)
            except Exception:
                return parsed
    return parsed


def _as_json_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if text == '':
        return None

    # Try JSON first
    try:
        parsed = json.loads(text)
        parsed = _maybe_parse_nested_json(parsed)
        parsed = _scrub_sensitive_obj(parsed)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # Always store valid JSON text
        return json.dumps({'raw': _truncate(_scrub_sensitive(text))}, ensure_ascii=False)


def _should_log_request(request: HttpRequest) -> bool:
    path = request.path or ''

    # Only dashboard endpoints
    if '/dashboard/' not in path:
        return False

    # Skip safe/preflight requests (too noisy for dashboards)
    method = (request.method or '').upper()
    if method in {'GET', 'OPTIONS', 'HEAD'}:
        return False

    # Avoid logging the logs endpoint itself
    if path.startswith('/dashboard/logs'):
        return False

    return True


def _get_user_for_log(request: HttpRequest):
    # If session-authenticated
    try:
        if hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
            return request.user
    except Exception:
        pass

    # Try DRF-authenticated (JWT / API key / etc. depending on project settings)
    try:
        for auth_class in api_settings.DEFAULT_AUTHENTICATION_CLASSES:
            auth = auth_class()
            result = auth.authenticate(request)
            if result is None:
                continue
            user, _auth = result
            return user
    except Exception:
        return None


def _scrub_sensitive(text: str) -> str:
    """Best-effort scrub for common secrets; keeps payload mostly intact."""
    if not text:
        return text

    lowered = text.lower()
    keys = ['password', 'pass', 'token', 'authorization', 'auth', 'secret', 'refresh', 'access']
    if not any(k in lowered for k in keys):
        return text

    # Try JSON scrub if payload is JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for k in list(obj.keys()):
                if str(k).lower() in keys:
                    obj[k] = '<redacted>'
            return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass

    return text


class DashboardRequestLoggingMiddleware:
    """Stores every dashboard request with request/response details."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if not _should_log_request(request):
            return self.get_response(request)

        request_body = None
        try:
            content_type = (request.META.get('CONTENT_TYPE') or '').lower()
            if 'multipart/form-data' in content_type:
                request_body = json.dumps({'raw': '<multipart/form-data omitted>'}, ensure_ascii=False)
            else:
                request_body_text = _safe_decode_bytes(getattr(request, 'body', b''))
                request_body = _as_json_text(request_body_text)
        except Exception:
            request_body = json.dumps({'raw': '<unavailable>'}, ensure_ascii=False)

        response: HttpResponse = self.get_response(request)

        response_body = None
        try:
            if getattr(response, 'streaming', False):
                response_body = json.dumps({'raw': '<streaming response omitted>'}, ensure_ascii=False)
            else:
                if hasattr(response, 'render') and callable(getattr(response, 'render')):
                    try:
                        response.render()
                    except Exception:
                        pass
                response_body_text = _safe_decode_bytes(getattr(response, 'content', b''))
                response_body = _as_json_text(response_body_text)
        except Exception:
            response_body = json.dumps({'raw': '<unavailable>'}, ensure_ascii=False)

        try:
            DashboardRequestLog.objects.create(
                user=_get_user_for_log(request),
                method=request.method,
                path=request.path,
                request_body=request_body,
                response_status=response.status_code,
                response_body=response_body,
            )
        except Exception:
            logger.exception('Failed to create dashboard request log')

        return response
