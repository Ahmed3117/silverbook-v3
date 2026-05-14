import requests
import json
import logging
import hashlib
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, timedelta
from django.utils import timezone

from services.customer_profile import get_customer_profile

logger = logging.getLogger(__name__)
CREATE_INVOICE_TIMEOUT = (5, 12)
ERROR_TEXT_LIMIT = 200


def _response_summary(response):
    return {
        'status_code': response.status_code,
        'content_type': response.headers.get('content-type'),
        'content_length': response.headers.get('content-length') or len(response.content or b''),
    }


def _safe_response_error(response):
    try:
        error_data = response.json()
        if isinstance(error_data, dict):
            return (
                error_data.get('error')
                or error_data.get('message')
                or error_data.get('detail')
                or f'HTTP {response.status_code}'
            )
    except (ValueError, TypeError):
        pass

    text = (response.text or '').strip()
    if not text:
        return f'HTTP {response.status_code}'
    return f'HTTP {response.status_code}: {text[:ERROR_TEXT_LIMIT]}'

class ShakeoutService:
    def __init__(self):
        # Shake-out API configuration
        self.api_key = getattr(settings, 'SHAKEOUT_API_KEY', '')
        self.secret_key = getattr(settings, 'SHAKEOUT_SECRET_KEY', '')
        self.base_url = getattr(settings, 'SHAKEOUT_BASE_URL', 'https://dash.shake-out.com/api/public/vendor')
        self.create_invoice_url = f"{self.base_url}/invoice"
        
        # Headers for API requests - Back to working API key authentication
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'apikey {self.api_key}'
        }
        
        logger.info("🔧 Shake-out Service initialized")
        logger.info(f"🔧 API Key loaded: {self.api_key[:10]}...")
        logger.info(f"🔧 Base URL: {self.base_url}")

    def calculate_invoice_amount(self, items, shipping=0, discount=0, discount_type='fixed', tax=0):
        """Calculate total invoice amount including shipping, discount, and tax"""
        subtotal = sum(float(item['price']) * int(item['quantity']) for item in items)
        
        if discount > 0:
            if discount_type == 'percent':
                discount_amount = subtotal * (discount / 100)
            else:
                discount_amount = discount
            subtotal -= discount_amount
        
        total = subtotal + shipping
        if tax > 0:
            total += total * (tax / 100)
        
        return round(total, 2)

    def create_payment_invoice(self, pill):
        """Create a payment invoice with Shake-out"""
        try:
            logger.info("Creating Shake-out invoice for pill_id=%s pill_number=%s", pill.id, pill.pill_number)
            
            # Check if pill already has a Shake-out invoice
            if pill.shakeout_invoice_id:
                logger.info(f"Pill {pill.pill_number} already has a Shake-out invoice: {pill.shakeout_invoice_id}")
                
                # Return existing invoice data in unified format
                return {
                    'success': False,
                    'error': 'Pill already has a Shake-out invoice',
                    'data': {
                        'invoice_id': pill.shakeout_invoice_id,
                        'invoice_ref': pill.shakeout_invoice_ref,
                        'url': self._build_payment_url(pill.shakeout_invoice_id, pill.shakeout_invoice_ref),
                        'payment_url': self._build_payment_url(pill.shakeout_invoice_id, pill.shakeout_invoice_ref),
                        'created_at': pill.shakeout_created_at.isoformat() if pill.shakeout_created_at else None,
                        'status': 'active',  # Assume active if stored
                        'total_amount': float(pill.final_price()),
                        'currency': 'EGP'
                    }
                }
            
            profile = get_customer_profile(pill)

            # Prepare customer data
            customer_data = {
                "first_name": profile['first_name'],
                "last_name": profile['last_name'],
                "email": profile['email'],
                "phone": profile['international_phone'],
                "address": f"{profile['address']}"
            }
            
            # Calculate totals for digital products (quantity always 1)
            invoice_items = []
            for item in pill.items.select_related('product').all():
                product = getattr(item, 'product', None)
                if not product:
                    continue

                price = product.discounted_price()
                if price is None:
                    price = product.price or 0.0

                invoice_items.append({
                    "name": product.name,
                    "price": float(price),
                    "quantity": 1
                })

            shipping_cost = 0.0
            total_discount = float(getattr(pill, 'coupon_discount', 0.0) or 0.0)
            final_amount = float(pill.final_price())

            # Handle discounts via Shake-out discount fields
            discount_enabled = total_discount > 0
            discount_value = total_discount if discount_enabled else 0.0
            
            # Prepare invoice data
            invoice_data = {
                "amount": float(final_amount),
                "currency": "EGP",
                "due_date": (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                "customer": customer_data,
                "redirection_urls": {
                    "success_url": f"https://bookefay.com/payment-redirect/{pill.pill_number}/successful-payment/success/{int(datetime.now().timestamp() * 1000)}",
                    "fail_url": f"https://bookefay.com/payment-redirect/{pill.pill_number}/failed-payment/failed/{int(datetime.now().timestamp() * 1000)}",
                    "pending_url": f"https://bookefay.com/payment-redirect/{pill.pill_number}/pending-payment/pending/{int(datetime.now().timestamp() * 1000)}"
                },
                "invoice_items": invoice_items,
                "tax_enabled": False,
                "discount_enabled": discount_enabled,
                "discount_type": "fixed",
                "discount_value": discount_value
            }
            
            logger.info(
                "Shake-out invoice payload prepared for pill_id=%s: amount=%s, items=%s",
                pill.id,
                final_amount,
                len(invoice_items),
            )
            
            # Make API request with session and retry logic
            session = requests.Session()
            session.headers.update(self.headers)
            
            session.verify = True
            
            try:
                response = session.post(
                    self.create_invoice_url,
                    json=invoice_data,
                    timeout=CREATE_INVOICE_TIMEOUT
                )
                
                logger.info("Shake-out create invoice response summary: %s", _response_summary(response))
                
                # Check if response is empty
                if not response.text.strip():
                    logger.error("Received empty response from Shake-out API")
                    return {
                        'success': False,
                        'error': f'Empty response from Shake-out API (HTTP {response.status_code})',
                        'data': None
                    }
                
                if (response.status_code == 403 and 'cloudflare' in response.text.lower()) or \
                   (response.headers.get('content-type', '').startswith('text/html')):
                    logger.warning("Received Cloudflare challenge or HTML response from Shake-out API")
                    return {
                        'success': False,
                        'error': f'Shake-out API blocked by Cloudflare protection. HTTP {response.status_code}. Consider using a different approach or contact Shake-out support.',
                        'data': None
                    }
                
            finally:
                session.close()
            
            # Handle successful responses (200 status)
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    
                    # Handle successful creation - unify response format
                    if response_data.get('status') == 'success':
                        # Successful creation response format
                        data = response_data.get('data', {})
                        invoice_id = data.get('invoice_id')
                        invoice_ref = data.get('invoice_ref')
                        payment_url = data.get('url')
                        
                        return {
                            'success': True,
                            'message': response_data.get('message', 'Invoice created successfully'),
                            'data': {
                                'invoice_id': invoice_id,
                                'invoice_ref': invoice_ref,
                                'url': payment_url,
                                'payment_url': payment_url,  # Unified key name
                                'created_at': timezone.now().isoformat(),
                                'status': 'active',
                                'total_amount': float(final_amount),
                                'currency': 'EGP',
                                'raw_response': response_data
                            }
                        }
                    else:
                        # Handle API error responses
                        return self._handle_api_error_response(response_data)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON response: {e}")
                    return {
                        'success': False,
                        'error': f'Invalid JSON response from Shake-out API: {str(e)}',
                        'data': None
                    }
            else:
                # Handle HTTP errors (non-200 status codes)
                try:
                    error_data = response.json()
                    return self._handle_api_error_response(error_data)
                except json.JSONDecodeError:
                    # Response is not JSON (probably HTML error page)
                    error_message = _safe_response_error(response)
                    return {
                        'success': False,
                        'error': error_message,
                        'data': None
                    }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating Shake-out invoice: {str(e)}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error creating Shake-out invoice: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def verify_webhook_signature(self, invoice_id, amount, invoice_status, updated_at, received_signature):
        """
        Verify webhook signature using SHA-256 hash
        """
        try:
            # Create the signature string as per Shake-out documentation
            signature_string = str(invoice_id) + str(amount) + str(invoice_status) + str(updated_at) + self.secret_key
            expected_signature = hashlib.sha256(signature_string.encode()).hexdigest()
            
            return expected_signature == received_signature
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    def check_payment_status(self, invoice_id):
        """
        Check payment status (if API supports it)
        Note: This might need to be implemented based on Shake-out's status check API
        """
        try:
            # This would need to be implemented if Shake-out provides a status check endpoint
            # For now, we rely on webhooks for status updates
            logger.info(f"Payment status check requested for invoice: {invoice_id}")
            return {'success': True, 'status': 'pending', 'message': 'Status check via webhooks only'}
        except Exception as e:
            logger.error(f"Exception checking payment status: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_api_error_response(self, response_data):
        """Handle different API error response formats and unify them"""
        # Handle case where success=False in response
        if 'success' in response_data and not response_data['success']:
            data = response_data.get('data', {})
            
            return {
                'success': False,
                'error': response_data.get('error', 'Unknown API error'),
                'data': {
                    'invoice_id': data.get('invoice_id'),
                    'invoice_ref': data.get('invoice_ref'),
                    'url': data.get('payment_url') or self._build_payment_url(data.get('invoice_id'), data.get('invoice_ref')),
                    'payment_url': data.get('payment_url') or self._build_payment_url(data.get('invoice_id'), data.get('invoice_ref')),
                    'created_at': data.get('created_at'),
                    'status': data.get('status', 'unknown'),
                    'total_amount': None,  # Not provided in error responses
                    'currency': 'EGP'
                } if data else None
            }
        
        # Handle other error formats
        error_message = response_data.get('message') or response_data.get('error', 'Unknown API error')
        return {
            'success': False,
            'error': error_message,
            'data': None
        }

    def _build_payment_url(self, invoice_id, invoice_ref):
        """Build payment URL from invoice ID and reference"""
        if invoice_id and invoice_ref:
            return f"https://dash.shake-out.com/invoice/{invoice_id}/{invoice_ref}"
        return None

# Global instance
shakeout_service = ShakeoutService()
