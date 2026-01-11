"""
Serializers for security models (dashboard endpoints)
"""
from rest_framework import serializers
from accounts.security_models import SecurityBlock, AuthenticationAttempt


class AuthenticationAttemptSerializer(serializers.ModelSerializer):
    """Serializer for authentication attempts"""
    
    attempt_type_display = serializers.CharField(source='get_attempt_type_display', read_only=True)
    result_display = serializers.CharField(source='get_result_display', read_only=True)
    
    class Meta:
        model = AuthenticationAttempt
        fields = [
            'id',
            'phone_number',
            'attempt_type',
            'attempt_type_display',
            'result',
            'result_display',
            'attempted_at',
            'ip_address',
            'user_agent',
            'device_id',
            'failure_reason',
            'related_block'
        ]
        read_only_fields = fields


class SecurityBlockSerializer(serializers.ModelSerializer):
    """Serializer for security blocks"""
    
    block_type_display = serializers.CharField(source='get_block_type_display', read_only=True)
    is_expired = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    remaining_formatted = serializers.SerializerMethodField()
    unblocked_by_username = serializers.CharField(source='unblocked_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = SecurityBlock
        fields = [
            'id',
            'phone_number',
            'block_type',
            'block_type_display',
            'blocked_at',
            'blocked_until',
            'block_level',
            'consecutive_blocks',
            'is_active',
            'is_expired',
            'remaining_seconds',
            'remaining_formatted',
            'manually_unblocked',
            'unblocked_by',
            'unblocked_by_username',
            'unblocked_at',
            'unblock_reason',
            'failed_attempts',
            'ip_addresses',
            'user_agents',
            'device_ids'
        ]
        read_only_fields = [
            'id',
            'phone_number',
            'block_type',
            'blocked_at',
            'blocked_until',
            'block_level',
            'consecutive_blocks',
            'failed_attempts',
            'ip_addresses',
            'user_agents',
            'device_ids'
        ]
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_remaining_seconds(self, obj):
        return obj.remaining_time()
    
    def get_remaining_formatted(self, obj):
        return obj.remaining_time_formatted()


class SecurityBlockDetailSerializer(SecurityBlockSerializer):
    """Detailed serializer with related attempts"""
    
    recent_attempts = AuthenticationAttemptSerializer(source='attempts', many=True, read_only=True)
    
    class Meta(SecurityBlockSerializer.Meta):
        fields = SecurityBlockSerializer.Meta.fields + ['recent_attempts']


class ManualUnblockSerializer(serializers.Serializer):
    """Serializer for manual unblock action"""
    
    phone_number = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Phone number to unblock"
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for unblocking"
    )
    
    def validate_phone_number(self, value):
        """Validate phone number format"""
        if not value:
            raise serializers.ValidationError("Phone number is required")
        return value


class SecurityStatsSerializer(serializers.Serializer):
    """Serializer for security statistics"""
    
    total_blocks = serializers.IntegerField(read_only=True)
    active_blocks = serializers.IntegerField(read_only=True)
    blocks_today = serializers.IntegerField(read_only=True)
    blocks_this_week = serializers.IntegerField(read_only=True)
    total_attempts = serializers.IntegerField(read_only=True)
    failed_attempts_today = serializers.IntegerField(read_only=True)
    blocked_attempts_today = serializers.IntegerField(read_only=True)
    top_blocked_numbers = serializers.ListField(read_only=True)
    block_types_distribution = serializers.DictField(read_only=True)
