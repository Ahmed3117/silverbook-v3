import json
import logging
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from products.models import Pill
from django.utils import timezone
from services.shakeout_service import shakeout_service

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["GET", "POST", "HEAD"])
def shakeout_webhook(request):
    """
    Shake-out Payment Webhook Handler
    
    GET: Health check for monitoring services  
    POST: Actual webhook processing
    """
    
    # Handle GET requests (health checks from monitoring services)
    if request.method == 'GET':
        logger.info("GET request received - Health check")
        return JsonResponse({
            'status': 'ok',
            'message': 'Shake-out webhook endpoint is healthy',
            'method': 'GET',
            'timestamp': timezone.now().isoformat(),
            'endpoint': 'shakeout-webhook'
        }, status=200)
    
    # Handle POST requests (actual webhooks)
    if request.method == 'POST':
        return handle_shakeout_webhook_post(request)

def handle_shakeout_webhook_post(request):
    """
    Handle actual Shake-out webhook POST requests
    """
    try:
        # Log the incoming webhook
        logger.info("=== Shake-out Webhook Received ===")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Body: {request.body.decode('utf-8')}")
        
        # Parse the webhook payload
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Extract webhook data according to Shake-out documentation
        event_type = payload.get('type')
        data = payload.get('data', {})
        received_signature = payload.get('signature')
        
        # Required fields from the webhook
        invoice_id = data.get('invoice_id')
        invoice_ref = data.get('invoice_ref')
        payment_method = data.get('payment_method')
        invoice_status = data.get('invoice_status')
        amount = data.get('amount')
        reference_number = data.get('referenceNumber')
        updated_at = data.get('updated_at')
        
        logger.info(f"Webhook Data - Type: {event_type}, Invoice ID: {invoice_id}, Status: {invoice_status}, Amount: {amount}")
        
        # Validate required fields
        if not invoice_id or not invoice_status or not amount or not updated_at:
            logger.error("Missing required fields in webhook payload")
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Verify signature if available
        if received_signature:
            is_valid_signature = shakeout_service.verify_webhook_signature(
                invoice_id, amount, invoice_status, updated_at, received_signature
            )
            if not is_valid_signature:
                logger.error("❌ Invalid webhook signature - potential security threat!")
                return JsonResponse({'error': 'Invalid signature'}, status=401)
            else:
                logger.info("✅ Webhook signature verified successfully")
        else:
            logger.warning("⚠️ No signature provided in webhook")
        
        # Find the pill associated with this invoice
        pill = find_pill_from_shakeout_data(invoice_id, invoice_ref)
        
        if not pill:
            logger.warning(f"No pill found for Shake-out invoice: {invoice_id}, ref: {invoice_ref}")
            # Return success to prevent webhook retries, but log the issue
            return JsonResponse({
                'success': True,
                'message': 'Invoice not found in system',
                'invoice_id': invoice_id,
                'invoice_ref': invoice_ref
            }, status=200)
        
        # Update pill payment status based on Shake-out status
        payment_updated = update_pill_payment_status(pill, invoice_status, data)
        
        # Log the status update
        logger.info(f"Processing webhook for Pill #{pill.pill_number}")
        logger.info(f"Shake-out Status: {invoice_status}")
        logger.info(f"Payment Status Updated: {payment_updated}")
        
        # Store webhook data for audit trail
        store_shakeout_webhook_data(pill, payload)
        
        # Send success response
        response_data = {
            'success': True,
            'pill_id': pill.id,
            'pill_number': pill.pill_number,
            'payment_updated': payment_updated,
            'current_status': pill.status,
            'shakeout_status': invoice_status
        }
        
        logger.info(f"Webhook processed successfully: {response_data}")
        return JsonResponse(response_data, status=200)
        
    except Exception as e:
        logger.error(f"Error processing Shake-out webhook: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

def find_pill_from_shakeout_data(invoice_id, invoice_ref):
    """
    Find pill from Shake-out webhook data
    """
    pill = None
    
    # Method 1: Try to find by Shake-out invoice ID
    if invoice_id:
        pill = Pill.objects.filter(shakeout_invoice_id=invoice_id).first()
        if pill:
            logger.info(f"Found pill by shakeout_invoice_id: {invoice_id}")
            return pill
    
    # Method 2: Try to find by Shake-out invoice reference
    if invoice_ref:
        pill = Pill.objects.filter(shakeout_invoice_ref=invoice_ref).first()
        if pill:
            logger.info(f"Found pill by shakeout_invoice_ref: {invoice_ref}")
            return pill
    
    logger.warning(f"No pill found using any method for: invoice_id={invoice_id}, invoice_ref={invoice_ref}")
    return None

def update_pill_payment_status(pill, shakeout_status, webhook_data):
    """
    Update pill payment status based on Shake-out invoice status
    """
    try:
        old_status = pill.status
        new_status = old_status
        
        # Map Shake-out statuses to our payment statuses
        if shakeout_status in ["paid"]:
            new_status = 'p'
        elif shakeout_status in ["failed", "cancelled", "expired"] and pill.status == 'p':
            new_status = 'i'
        # For "pending" status, we don't change the payment status
        
        if new_status != old_status:
            pill.status = new_status
            pill.save(update_fields=['status'])
            
            logger.info(f"Updated Pill #{pill.pill_number} status from {old_status} to {new_status}")
            
            # Grant purchased books if payment is confirmed
            if new_status == 'p':
                try:
                    pill.grant_purchased_books()
                    logger.info(f"✓ Purchased books granted for pill {pill.pill_number}")
                except Exception as e:
                    logger.error(f"Failed to grant purchased books for pill {pill.pill_number}: {str(e)}")
            
            return True
        else:
            logger.info(f"No status change needed for Pill #{pill.pill_number} (current: {old_status})")
            return False
            
    except Exception as e:
        logger.error(f"Error updating pill payment status: {e}")
        return False

def store_shakeout_webhook_data(pill, payload):
    """
    Store webhook data in pill's shakeout_data for audit trail
    """
    try:
        # Get existing data or create new
        existing_data = pill.shakeout_data or {}
        
        # Add webhook data
        if 'webhooks' not in existing_data:
            existing_data['webhooks'] = []
        
        webhook_entry = {
            'timestamp': timezone.now().isoformat(),
            'type': payload.get('type'),
            'invoice_status': payload.get('data', {}).get('invoice_status'),
            'amount': payload.get('data', {}).get('amount'),
            'payment_method': payload.get('data', {}).get('payment_method'),
            'payload': payload
        }
        
        existing_data['webhooks'].append(webhook_entry)
        
        # Keep only last 20 webhooks to avoid bloating
        if len(existing_data['webhooks']) > 20:
            existing_data['webhooks'] = existing_data['webhooks'][-20:]
        
        # Update the pill
        pill.shakeout_data = existing_data
        pill.save(update_fields=['shakeout_data'])
        
        logger.info(f"Stored webhook data for Pill #{pill.pill_number}")
        
    except Exception as e:
        logger.error(f"Error storing webhook data: {e}")