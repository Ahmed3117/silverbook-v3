import requests
import json
import logging
from django.conf import settings
from django.core.cache import cache

from services.customer_profile import get_customer_profile

logger = logging.getLogger(__name__)

class FawaterakPaymentService:
    def __init__(self):
        # Use getattr with fallback values to handle missing Fawaterak settings gracefully
        self.api_key = getattr(settings, 'FAWATERAK_API_KEY', None)
        self.provider_key = getattr(settings, 'FAWATERAK_PROVIDER_KEY', None)
        self.base_url = getattr(settings, 'FAWATERAK_BASE_URL', 'https://app.fawaterk.com/api/v2')
        self.webhook_url = getattr(settings, 'FAWATERAK_WEBHOOK_URL', None)
        
        # If Fawaterak is not configured, log a warning
        if not self.api_key:
            logger.warning("Fawaterak service not configured - API key missing. Shake-out is now the primary payment gateway.")
        
        # Correct API endpoints (only if base_url exists)
        if self.base_url:
            self.create_invoice_url = f"{self.base_url}/createInvoiceLink"
            # Try different endpoint names for getting invoice status
            self.invoice_status_urls = [
                f"{self.base_url}/getInvoiceData",
                f"{self.base_url}/invoiceStatus", 
                f"{self.base_url}/checkInvoice",
                f"{self.base_url}/invoice/status"
            ]
        
    def create_payment_invoice(self, pill):
        """
        Create a payment invoice for a pill using Fawaterak Production API
        """
        if not self.api_key:
            return {
                'success': False, 
                'error': 'Fawaterak service not configured. Please use Shake-out payment gateway instead.'
            }
            
        try:
            logger.info(f"Creating Fawaterak invoice for pill {pill.pill_number}")
            
            # Validate pill
            if not pill.items.exists():
                return {'success': False, 'error': 'No items in pill'}
            
            profile = get_customer_profile(pill)
            
            # Prepare cart items
            cart_items = []
            cart_total = 0
            
            # Add product items
            for item in pill.items.all():
                item_price = float(item.product.discounted_price())
                cart_total += item_price * item.quantity
                
                item_description = item.product.name
                if item.size:
                    item_description += f" - Size: {item.size}"
                if item.color:
                    item_description += f" - Color: {item.color.name}"
                
                cart_items.append({
                    "name": item_description[:100],
                    "price": str(item_price),
                    "quantity": str(item.quantity)
                })
            
            # Add shipping
            shipping_price = float(pill.shipping_price())
            if shipping_price > 0:
                cart_items.append({
                    "name": "Shipping Fee",
                    "price": str(shipping_price),
                    "quantity": "1"
                })
                cart_total += shipping_price
            
            # Handle discounts
            discount_amount = float(pill.coupon_discount + pill.calculate_gift_discount())
            if discount_amount > 0:
                cart_items.append({
                    "name": "Discount (Coupon + Gifts)",
                    "price": str(-discount_amount),
                    "quantity": "1"
                })
                cart_total -= discount_amount
            
            # Prepare customer data
            customer_names = profile['full_name'].split()
            customer_data = {
                "first_name": (customer_names[0] if customer_names else profile['first_name'])[:50],
                "last_name": (" ".join(customer_names[1:]) if len(customer_names) > 1 else profile['last_name'])[:50],
                "email": profile['email'],
                "phone": profile['phone'].replace('+', '').replace('-', '').replace(' ', ''),
                "address": profile['address'][:200],
                "customer_unique_id": str(pill.user.id)
            }
            
            webhook_url= settings.FAWATERAK_WEBHOOK_URL
            success_url = f"{settings.PILL_STATUS_URL}/{pill.id}/success?pill_number={pill.pill_number}&amount={cart_total}"
            pending_url = f"{settings.PILL_STATUS_URL}/{pill.id}/pending?pill_number={pill.pill_number}&amount={cart_total}"
            fail_url = f"{settings.PILL_STATUS_URL}/{pill.id}/failed?pill_number={pill.pill_number}&amount={cart_total}"
            payload = {
                "cartTotal": str(round(cart_total, 2)),
                "currency": "EGP",
                "customer": customer_data,
                "cartItems": cart_items,
                "redirectionUrls": {
                    "successUrl": success_url,
                    "pendingUrl": pending_url,
                    "failUrl": fail_url,
                    "webhookUrl": webhook_url
                },
                "payLoad": {
                    "pill_id": pill.id,
                    "pill_number": pill.pill_number,
                    "user_id": pill.user.id,
                    "original_total": str(pill.final_price())
                },
                "sendEmail": True,
                "sendSMS": False,
                "frequency": "once"
            }
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Making request to: {self.create_invoice_url}")
            logger.info(f"Redirect URLs:")
            logger.info(f"  Success: {success_url}")
            logger.info(f"  Pending: {pending_url}")
            logger.info(f"  Fail: {fail_url}")
            
            response = requests.post(
                self.create_invoice_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Fawaterak response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                
                if response_data.get('status') == 'success':
                    invoice_data = response_data.get('data', {})
                    payment_url = invoice_data.get('url')
                    invoice_key = invoice_data.get('invoiceKey')
                    invoice_id = invoice_data.get('invoiceId')
                    
                    if payment_url:
                        # Cache invoice data
                        cache.set(
                            f'fawaterak_invoice_{pill.pill_number}',
                            {
                                'invoice_id': invoice_id,
                                'invoice_key': invoice_key,
                                'payment_url': payment_url,
                                'total_amount': cart_total,
                                'pill_id': pill.id,
                                'created_at': str(pill.date_added)
                            },
                            timeout=24*60*60
                        )
                        
                        logger.info(f"✓ Fawaterak invoice created successfully for pill {pill.pill_number}")
                        logger.info(f"Payment URL: {payment_url}")
                        
                        return {
                            'success': True,
                            'data': {
                                'payment_url': payment_url,
                                'invoice_id': invoice_id,
                                'invoice_key': invoice_key,
                                'reference_id': pill.pill_number,
                                'total_amount': cart_total
                            }
                        }
                    else:
                        return {'success': False, 'error': 'No payment URL in response'}
                else:
                    error_msg = response_data.get('message', 'Unknown error from Fawaterak')
                    return {'success': False, 'error': error_msg}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}: {response.text}'}
                
        except Exception as e:
            logger.error(f"Exception creating Fawaterak invoice: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}

    
    def get_invoice_status(self, reference_id):
        """
        Get invoice status by reference ID - try multiple endpoints
        """
        if not self.api_key:
            return {
                'success': False, 
                'error': 'Fawaterak service not configured. Please use Shake-out payment gateway instead.'
            }
            
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Get cached invoice data
            cached_data = cache.get(f'fawaterak_invoice_{reference_id}')
            if not cached_data:
                logger.warning(f"Invoice data not found in cache for {reference_id}")
                return {'success': False, 'error': 'Invoice data not found in cache'}
            
            invoice_key = cached_data.get('invoice_key')
            invoice_id = cached_data.get('invoice_id')
            
            if not invoice_key:
                return {'success': False, 'error': 'Invoice key not found'}
            
            # Try different payload formats
            payloads = [
                {"invoiceKey": invoice_key},
                {"invoice_key": invoice_key},
                {"invoiceId": invoice_id},
                {"invoice_id": invoice_id}
            ]
            
            # Try different endpoints
            for url in self.invoice_status_urls:
                for payload in payloads:
                    try:
                        logger.info(f"Trying invoice status: {url} with payload: {payload}")
                        response = requests.post(url, json=payload, headers=headers, timeout=30)
                        
                        logger.info(f"Invoice status response: {response.status_code} - {response.text}")
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            if response_data.get('status') == 'success':
                                return {'success': True, 'data': response_data.get('data', {})}
                    except Exception as e:
                        logger.warning(f"Failed to check status at {url}: {e}")
                        continue
            
            # If all endpoints fail, return cached data
            return {
                'success': True, 
                'data': {
                    'status': 'unknown',
                    'invoice_id': invoice_id,
                    'invoice_key': invoice_key,
                    'message': 'Could not verify status with Fawaterak, using cached data'
                }
            }
                
        except Exception as e:
            logger.error(f"Exception getting invoice status: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_webhook_payment(self, webhook_data):
        print("-------------------------------------------")
        print('i am in webhook service')
        print("-------------------------------------------")
        """
        Process payment webhook from Fawaterak
        """
        try:
            logger.info(f"Processing Fawaterak webhook: {webhook_data}")
            
            # Extract payment information
            payload_data = webhook_data.get('payLoad', {})
            pill_number = payload_data.get('pill_number')
            payment_status = webhook_data.get('invoice_status', '').lower()
            payment_method = webhook_data.get('payment_method', '').lower()
            invoice_id = webhook_data.get('invoiceId')
            
            if not pill_number:
                return {'success': False, 'error': 'No pill reference in webhook'}
            
            # Find the pill
            from products.models import Pill
            
            try:
                pill = Pill.objects.get(pill_number=pill_number)
            except Pill.DoesNotExist:
                logger.error(f"Pill not found for reference ID: {pill_number}")
                return {'success': False, 'error': f'Pill not found: {pill_number}'}
            
            # FIXED: Handle Fawry-specific status logic
            # Fawry payments may show as "pending" even when money is taken
            # Check for Fawry-specific indicators of successful payment
            fawry_success_indicators = [
                'paid', 'success', 'completed', 'successful', 
                'fawry_paid', 'wallet_deducted', 'transaction_completed'
            ]
            
            fawry_pending_but_paid = (
                payment_method == 'fawry' and 
                payment_status == 'pending' and 
                webhook_data.get('transaction_id') and  # Has transaction ID
                webhook_data.get('amount_paid', 0) > 0   # Amount was deducted
            )
            
            # Update pill payment status
            if payment_status in fawry_success_indicators or fawry_pending_but_paid:
                if pill.status != 'p':
                    pill.status = 'p'
                    pill.save(update_fields=['status'])
                
                logger.info(f"✓ Payment confirmed for pill {pill.pill_number} (Status: {payment_status}, Method: {payment_method})")
                
                # Clear cached invoice data
                cache.delete(f'fawaterak_invoice_{pill.pill_number}')
                
                return {
                    'success': True,
                    'data': {
                        'pill_number': pill.pill_number,
                        'payment_status': 'confirmed',
                        'payment_method': payment_method,
                        'invoice_id': invoice_id
                    }
                }
            
            elif payment_status in ['failed', 'cancelled', 'expired', 'fail']:
                logger.warning(f"Payment failed for pill {pill.pill_number}: {payment_status}")
                
                return {
                    'success': True,
                    'data': {
                        'pill_number': pill.pill_number,
                        'payment_status': 'failed',
                        'reason': payment_status
                    }
                }
            
            else:
                logger.warning(f"Unknown payment status for pill {pill.pill_number}: {payment_status} (Method: {payment_method})")
                logger.info(f"Full webhook data: {webhook_data}")
                return {'success': False, 'error': f'Unknown payment status: {payment_status}'}
                
        except Exception as e:
            logger.error(f"Exception processing webhook: {e}")
            return {'success': False, 'error': str(e)}

# Global instance
fawaterak_service = FawaterakPaymentService()