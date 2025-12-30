import json
import logging
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from products.models import Pill
from django.utils import timezone
from services.easypay_service import easypay_service

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["GET", "POST", "HEAD"])
def easypay_webhook(request, api_key=None):
    """
    EasyPay Payment Webhook Handler
    
    GET: Health check for monitoring services  
    POST: Actual webhook processing with API key validation
    """
    
    # Handle GET requests (health checks from monitoring services)
    if request.method == 'GET':
        logger.info("GET request received - Health check")
        return JsonResponse({
            'status': 'ok',
            'message': 'EasyPay webhook endpoint is healthy',
            'method': 'GET',
            'timestamp': timezone.now().isoformat(),
            'endpoint': 'easypay-webhook'
        }, status=200)
    
    # Handle POST requests (actual webhooks)
    if request.method == 'POST':
        return handle_easypay_webhook_post(request, api_key)

def handle_easypay_webhook_post(request, api_key):
    """
    Handle actual EasyPay webhook POST requests
    """
    try:
        # Validate API key if provided in URL
        if api_key:
            expected_api_key = getattr(settings, 'EASYPAY_API_KEY', None)
            if not expected_api_key or api_key != expected_api_key:
                logger.warning(f"Invalid API key received: {api_key}")
                return JsonResponse({
                    'error': 'Unauthorized'
                }, status=401)
        
        # Log the incoming webhook
        logger.info("=== EasyPay Webhook Received ===")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Body: {request.body.decode('utf-8')}")
        
        # Parse the webhook payload
        try:
            webhook_data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook payload: {str(e)}")
            return JsonResponse({
                'error': 'Invalid JSON payload'
            }, status=400)
        
        # Extract required fields
        easypay_sequence = webhook_data.get("easy_pay_sequence")
        status_paid = webhook_data.get("status")
        received_signature = webhook_data.get("signature")
        customer_phone = webhook_data.get("customer_phone")
        amount = webhook_data.get("amount")
        
        logger.info(f"Webhook data extracted:")
        logger.info(f"  - EasyPay Sequence: {easypay_sequence}")
        logger.info(f"  - Status: {status_paid}")
        logger.info(f"  - Customer Phone: {customer_phone}")
        logger.info(f"  - Amount: {amount}")
        logger.info(f"  - Received Signature: {received_signature}")
        
        # Validate required fields
        if not all([easypay_sequence, status_paid, received_signature, customer_phone, amount]):
            missing_fields = []
            if not easypay_sequence: missing_fields.append("easy_pay_sequence")
            if not status_paid: missing_fields.append("status")
            if not received_signature: missing_fields.append("signature")
            if not customer_phone: missing_fields.append("customer_phone")
            if not amount: missing_fields.append("amount")
            
            logger.error(f"Missing required fields in webhook: {missing_fields}")
            return JsonResponse({
                'error': 'Missing required fields',
                'missing_fields': missing_fields
            }, status=400)
        
        # Find the pill with matching EasyPay sequence
        try:
            pill = Pill.objects.get(easypay_invoice_sequence=easypay_sequence)
            logger.info(f"Found pill {pill.pill_number} for EasyPay sequence {easypay_sequence}")
        except Pill.DoesNotExist:
            logger.error(f"No pill found with EasyPay sequence: {easypay_sequence}")
            return JsonResponse({
                'error': 'Invoice not found',
                'easy_pay_sequence': easypay_sequence
            }, status=404)
        except Exception as e:
            logger.error(f"Error finding pill: {str(e)}")
            return JsonResponse({
                'error': 'Database error while finding invoice'
            }, status=500)
        
        # Verify signature
        is_signature_valid = easypay_service.verify_webhook_signature(
            amount, customer_phone, received_signature
        )
        
        if not is_signature_valid:
            logger.error(f"Invalid signature for pill {pill.pill_number}")
            logger.error(f"  - Expected pattern: amount + customer_phone + secret_key")
            logger.error(f"  - Received signature: {received_signature}")
            return JsonResponse({
                'error': 'Invalid signature'
            }, status=403)
        
        logger.info(f"✓ Signature verification passed for pill {pill.pill_number}")
        
        # Process payment status
        if status_paid == 'PAID':
            logger.info(f"Processing payment confirmation for pill {pill.pill_number}")
            
            old_status = pill.status
            pill.status = 'p'
            
            # Update EasyPay data with webhook information 
            easypay_payload = pill.easypay_data or {}
            easypay_payload['webhook_received'] = True
            easypay_payload['webhook_timestamp'] = timezone.now().isoformat()
            easypay_payload['webhook_data'] = webhook_data
            pill.easypay_data = easypay_payload
            
            pill.save(update_fields=['status', 'easypay_data'])
            
            logger.info(f"✓ Updated pill {pill.pill_number}:")
            logger.info(f"  - Status: {old_status} → {pill.status}")
            logger.info(f"  - Amount: {amount}")
            
            # Grant purchased books to user - THIS IS CRITICAL for adding books after payment
            try:
                pill.grant_purchased_books()
                logger.info(f"✓ Purchased books granted for pill {pill.pill_number}")
            except Exception as e:
                logger.error(f"Failed to grant purchased books for pill {pill.pill_number}: {str(e)}")
                # Don't fail the webhook for book granting errors - the payment was still successful
            
            # Send payment notification if applicable
            try:
                pill.send_payment_notification()
                logger.info(f"✓ Payment notification sent for pill {pill.pill_number}")
            except Exception as e:
                logger.error(f"Failed to send payment notification for pill {pill.pill_number}: {str(e)}")
                # Don't fail the webhook for notification errors
        
        else:
            logger.info(f"Non-payment status received for pill {pill.pill_number}: {status_paid}")
            
            # Update EasyPay data with webhook information for non-payment statuses
            easypay_payload = pill.easypay_data or {}
            easypay_payload['webhook_received'] = True
            easypay_payload['webhook_timestamp'] = timezone.now().isoformat()
            easypay_payload['webhook_data'] = webhook_data
            pill.easypay_data = easypay_payload
            pill.save(update_fields=['easypay_data'])
        
        logger.info(f"✓ EasyPay webhook processed successfully for pill {pill.pill_number}")
        
        return JsonResponse({
            'message': 'Webhook processed successfully',
            'pill_number': pill.pill_number,
            'status': status_paid,
            'processed_at': timezone.now().isoformat()
        }, status=200)
        
    except Exception as e:
        logger.error(f"✗ Unexpected error processing EasyPay webhook: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


def test_easypay_webhook_signature():
    """
    Test function to verify EasyPay webhook signature calculation
    """
    # Test data
    amount = "180.00"
    customer_phone = "01030265229"
    secret_key = getattr(settings, 'EASYPAY_SECRET_KEY', '')
    
    # Calculate signature
    string_to_hash = f"{amount}{customer_phone}{secret_key}"
    expected_signature = hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()
    
    logger.info("=== EasyPay Webhook Signature Test ===")
    logger.info(f"Amount: {amount}")
    logger.info(f"Customer Phone: {customer_phone}")
    logger.info(f"Secret Key: {secret_key}")
    logger.info(f"String to Hash: {string_to_hash}")
    logger.info(f"Expected Signature: {expected_signature}")
    
    return expected_signature
