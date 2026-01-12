"""
Dashboard views for security management (admin/staff only)
"""
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from accounts.security_models import SecurityBlock, AuthenticationAttempt
from accounts.security_serializers import (
    SecurityBlockSerializer,
    SecurityBlockDetailSerializer,
    AuthenticationAttemptSerializer,
    ManualUnblockSerializer,
    SecurityStatsSerializer
)
from services.security_service import security_service
from accounts.pagination import CustomPageNumberPagination


class SecurityBlockListView(generics.ListAPIView):
    """
    List all security blocks with filtering
    
    GET /api/accounts/dashboard/security/blocks/
    
    Query Parameters:
    - is_active: Filter by active status (true/false)
    - block_type: Filter by type (login/password_reset)
    - phone_number: Filter by phone number
    - search: Search in phone number
    """
    queryset = SecurityBlock.objects.all()
    serializer_class = SecurityBlockSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Filter by block type
        block_type = self.request.query_params.get('block_type')
        if block_type:
            queryset = queryset.filter(block_type=block_type)
        
        # Filter by phone number
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            queryset = queryset.filter(phone_number=phone_number)
        
        # Search in phone number
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(phone_number__icontains=search)
        
        return queryset.order_by('-blocked_at')


class SecurityBlockDetailView(generics.RetrieveAPIView):
    """
    Get detailed information about a specific security block
    
    GET /api/accounts/dashboard/security/blocks/{id}/
    """
    queryset = SecurityBlock.objects.all()
    serializer_class = SecurityBlockDetailSerializer
    permission_classes = [IsAdminUser]


@api_view(['POST'])
@permission_classes([IsAdminUser])
def manual_unblock_view(request):
    """
    Manually unblock a phone number
    
    POST /api/accounts/dashboard/security/unblock/
    {
        "phone_number": "01234567890",
        "reason": "User contacted support"
    }
    """
    serializer = ManualUnblockSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    phone_number = serializer.validated_data['phone_number']
    reason = serializer.validated_data.get('reason', 'تم رفع الحظر يدويًا عبر لوحة التحكم')
    
    # Check if there are any active blocks
    active_blocks = SecurityBlock.objects.filter(
        phone_number=phone_number,
        is_active=True
    )
    
    if not active_blocks.exists():
        return Response({
            'error': 'لا توجد أي عمليات حظر نشطة لهذا الرقم'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Unblock
    count = security_service.manually_unblock(
        phone_number=phone_number,
        unblocked_by_user=request.user,
        reason=reason
    )
    
    return Response({
        'success': True,
        'message': f'تم رفع الحظر بنجاح عن {count} عملية/عمليات حظر',
        'phone_number': phone_number,
        'unblocked_count': count
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def deactivate_block_view(request, pk):
    """
    Deactivate a specific security block
    
    POST /api/accounts/dashboard/security/blocks/{id}/deactivate/
    {
        "reason": "Block no longer needed"
    }
    """
    try:
        block = SecurityBlock.objects.get(pk=pk)
    except SecurityBlock.DoesNotExist:
        return Response({
            'error': 'الحظر الأمني غير موجود'
        }, status=status.HTTP_404_NOT_FOUND)
    
    if not block.is_active:
        return Response({
            'error': 'هذا الحظر غير نشط بالفعل'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    reason = request.data.get('reason', 'تم إلغاء التفعيل عبر لوحة التحكم')
    
    block.is_active = False
    block.manually_unblocked = True
    block.unblocked_by = request.user
    block.unblocked_at = timezone.now()
    block.unblock_reason = reason
    block.save()
    
    return Response({
        'success': True,
        'message': 'تم إلغاء تفعيل الحظر الأمني بنجاح',
        'block': SecurityBlockSerializer(block).data
    }, status=status.HTTP_200_OK)


class AuthenticationAttemptListView(generics.ListAPIView):
    """
    List all authentication attempts with filtering
    
    GET /api/accounts/dashboard/security/attempts/
    
    Query Parameters:
    - phone_number: Filter by phone number
    - attempt_type: Filter by type (login/password_reset)
    - result: Filter by result (success/failed/blocked)
    - date_from: Filter from date (ISO format)
    - date_to: Filter to date (ISO format)
    - search: Search in phone number
    """
    queryset = AuthenticationAttempt.objects.all()
    serializer_class = AuthenticationAttemptSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by phone number
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            queryset = queryset.filter(phone_number=phone_number)
        
        # Filter by attempt type
        attempt_type = self.request.query_params.get('attempt_type')
        if attempt_type:
            queryset = queryset.filter(attempt_type=attempt_type)
        
        # Filter by result
        result = self.request.query_params.get('result')
        if result:
            queryset = queryset.filter(result=result)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(attempted_at__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(attempted_at__lte=date_to)
        
        # Search in phone number
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(phone_number__icontains=search)
        
        return queryset.order_by('-attempted_at')


class AuthenticationAttemptDetailView(generics.RetrieveAPIView):
    """
    Get detailed information about a specific authentication attempt
    
    GET /api/accounts/dashboard/security/attempts/{id}/
    """
    queryset = AuthenticationAttempt.objects.all()
    serializer_class = AuthenticationAttemptSerializer
    permission_classes = [IsAdminUser]


@api_view(['GET'])
@permission_classes([IsAdminUser])
def security_statistics_view(request):
    """
    Get security statistics
    
    GET /api/accounts/dashboard/security/stats/
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    
    # Total blocks
    total_blocks = SecurityBlock.objects.count()
    active_blocks = SecurityBlock.objects.filter(is_active=True).count()
    blocks_today = SecurityBlock.objects.filter(blocked_at__gte=today_start).count()
    blocks_this_week = SecurityBlock.objects.filter(blocked_at__gte=week_start).count()
    
    # Total attempts
    total_attempts = AuthenticationAttempt.objects.count()
    failed_attempts_today = AuthenticationAttempt.objects.filter(
        attempted_at__gte=today_start,
        result='failed'
    ).count()
    blocked_attempts_today = AuthenticationAttempt.objects.filter(
        attempted_at__gte=today_start,
        result='blocked'
    ).count()
    
    # Top blocked numbers (last 7 days)
    top_blocked = SecurityBlock.objects.filter(
        blocked_at__gte=week_start
    ).values('phone_number').annotate(
        block_count=Count('id')
    ).order_by('-block_count')[:10]
    
    top_blocked_numbers = [
        {
            'phone_number': item['phone_number'],
            'block_count': item['block_count']
        }
        for item in top_blocked
    ]
    
    # Block types distribution
    block_types = SecurityBlock.objects.filter(
        blocked_at__gte=week_start
    ).values('block_type').annotate(
        count=Count('id')
    )
    
    block_types_distribution = {
        item['block_type']: item['count']
        for item in block_types
    }
    
    stats = {
        'total_blocks': total_blocks,
        'active_blocks': active_blocks,
        'blocks_today': blocks_today,
        'blocks_this_week': blocks_this_week,
        'total_attempts': total_attempts,
        'failed_attempts_today': failed_attempts_today,
        'blocked_attempts_today': blocked_attempts_today,
        'top_blocked_numbers': top_blocked_numbers,
        'block_types_distribution': block_types_distribution
    }
    
    serializer = SecurityStatsSerializer(stats)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def phone_security_history_view(request, phone_number):
    """
    Get complete security history for a specific phone number
    
    GET /api/accounts/dashboard/security/phone/{phone_number}/history/
    """
    # Get all blocks
    blocks = SecurityBlock.objects.filter(
        phone_number=phone_number
    ).order_by('-blocked_at')
    
    # Get all attempts (queryset)
    attempts_qs = AuthenticationAttempt.objects.filter(
        phone_number=phone_number
    ).order_by('-attempted_at')

    # Slice only for response payload (avoid filtering after slicing)
    recent_attempts = attempts_qs[:50]  # Last 50 attempts
    
    # Get current status
    current_block = security_service.get_block_status(phone_number)
    
    # Calculate statistics
    total_blocks = blocks.count()
    active_blocks_count = blocks.filter(is_active=True).count()
    failed_attempts_count = attempts_qs.filter(result='failed').count()
    successful_attempts_count = attempts_qs.filter(result='success').count()
    
    return Response({
        'phone_number': phone_number,
        'current_status': current_block,
        'statistics': {
            'total_blocks': total_blocks,
            'active_blocks': active_blocks_count,
            'failed_attempts': failed_attempts_count,
            'successful_attempts': successful_attempts_count
        },
        'blocks': SecurityBlockSerializer(blocks, many=True).data,
        'recent_attempts': AuthenticationAttemptSerializer(recent_attempts, many=True).data
    }, status=status.HTTP_200_OK)
