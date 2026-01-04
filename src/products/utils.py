import json
import requests
from django.conf import settings

def send_whatsapp_message(phone_number, message):
    """
    Send SMS message using BeOn service.
    This is a wrapper function to maintain backward compatibility.
    Now uses SMS instead of WhatsApp for message delivery.
    """
    from services.beon_service import send_beon_sms
    
    result = send_beon_sms(phone_number, message)
    
    # Return format compatible with old implementation
    if result['success']:
        return result.get('data', {'status': 'success'})
    else:
        return {'error': result.get('error', 'Failed to send message')}






