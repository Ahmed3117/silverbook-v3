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

class EasyPayService:
    def __init__(self):
        # EasyPay API configuration
        self.vendor_code = getattr(settings, 'EASYPAY_VENDOR_CODE', '')
        self.secret_key = getattr(settings, 'EASYPAY_SECRET_KEY', '')
        self.base_url = getattr(settings, 'EASYPAY_BASE_URL', 'https://api.easy-adds.com/api')
        self.payment_method = getattr(settings, 'EASYPAY_PAYMENT_METHOD', 'fawry')
        self.payment_expiry = getattr(settings, 'EASYPAY_PAYMENT_EXPIRY', 172800000)
        self.webhook_url = getattr(settings, 'EASYPAY_WEBHOOK_URL', '')

        # URLs
        self.create_invoice_url = f"{self.base_url}/create-invoice/"
        self.get_invoice_url = f"{self.base_url}/get-invoice"
        
        # Headers for API requests
        self.headers = {
            'Content-Type': 'application/json',
        }
        
        logger.info("🔧 EasyPay Service initialized")
        logger.info(f"🔧 Vendor Code: {self.vendor_code[:10]}...")
        logger.info(f"🔧 Base URL: {self.base_url}")
        logger.info(f"🔧 Webhook URL: {self.webhook_url}")

    def calculate_signature(self, amount, profile_id, phone):
        """Calculate SHA256 signature for EasyPay API"""
        # Pattern: vendor_code + secret_key + amount + profile_id + phone
        string_to_hash = f"{self.vendor_code}{self.secret_key}{amount}{profile_id}{phone}"
        signature = hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()
        
        logger.debug(f"String to hash: {string_to_hash}")
        logger.debug(f"Generated signature: {signature}")
        
        return signature

    def create_payment_invoice(self, pill):
        """Create a payment invoice with EasyPay"""
        try:
            logger.info(f"Creating EasyPay invoice for pill {pill.pill_number}")
            
            # Log pill details for debugging
            pill_items_count = pill.items.count()
            logger.info(f"Pill has {pill_items_count} items")
            if pill_items_count > 0:
                for i, item in enumerate(pill.items.all()[:5]):  # Log first 5 items
                    logger.info(f"  Item {i+1}: {item.product.name} (ID: {item.id})")
                if pill_items_count > 5:
                    logger.info(f"  ... and {pill_items_count - 5} more items")
            
            profile = get_customer_profile(pill)

            # Get customer information
            customer_name = profile['full_name']
            customer_phone = profile['phone']
            
            if not customer_phone:
                logger.error(f"Pill {pill.pill_number} has no customer phone")
                return {
                    'success': False,
                    'error': 'Customer phone is required for EasyPay invoice creation'
                }
            
            # Calculate amounts
            final_price = pill.final_price()
            amount = f"{final_price:.2f}"
            
            # Use pill ID as profile_id (unique identifier for customer)
            profile_id = str(pill.id)
            
            # Generate signature
            signature = self.calculate_signature(amount, profile_id, customer_phone)
            
            # Prepare items list - EasyPay expects the total to match sum of all item prices
            # So we'll create one consolidated item for the entire order to avoid calculation issues
            items = []
            
            # Get all pill items for description
            pill_items = pill.items.all()
            
            if pill_items:
                # Create a description that includes all products
                product_names = [item.product.name for item in pill_items[:3]]  # Limit to first 3 for readability
                if len(pill_items) > 3:
                    description = f"Order {pill.pill_number}: {', '.join(product_names)} and {len(pill_items) - 3} more items"
                else:
                    description = f"Order {pill.pill_number}: {', '.join(product_names)}"
                
                # Create single consolidated item with total amount
                items.append({
                    "item_id": str(pill.id),
                    "price": amount,
                    "quantity": 1,
                    "description": description
                })
            else:
                # Fallback for orders with no items
                items.append({
                    "item_id": str(pill.id),
                    "price": amount,
                    "quantity": 1,
                    "description": f"Order {pill.pill_number}"
                })
            
            # Prepare request payload
            # Calculate expiry timestamp (current time + payment expiry in milliseconds)
            current_time_ms = int(timezone.now().timestamp() * 1000)
            expiry_time_ms = current_time_ms + self.payment_expiry
            
            payload = {
                "vendor_code": self.vendor_code,
                "amount": amount,
                "payment_expiry": expiry_time_ms,
                "payment_method": self.payment_method,
                "signature": signature,
                "customer": {
                    "name": customer_name,
                    "phone": customer_phone,
                    "profile_id": profile_id
                },
                "items": items
            }
            
            # Add webhook URL if configured
            if self.webhook_url:
                payload["webhook_url"] = self.webhook_url
            
            # Log the final payload for debugging
            logger.info(f"EasyPay request payload:")
            logger.info(f"  - Amount: {amount}")
            logger.info(f"  - Items count: {len(items)}")
            logger.info(f"  - Items: {json.dumps(items, indent=4)}")
            logger.info(f"  - Customer: {payload['customer']}")
            logger.info(f"  - Full payload: {json.dumps(payload, indent=2)}")
            
            # Make API request
            response = requests.post(
                self.create_invoice_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            logger.info(f"EasyPay API response status: {response.status_code}")
            logger.info(f"EasyPay API response: {response.text}")
            
            # Accept both 200 (OK) and 201 (Created) as successful responses
            if response.status_code in [200, 201]:
                response_data = response.json()
                
                # Extract invoice details
                invoice_sequence = response_data.get('invoice_sequence')
                invoice_uid = response_data.get('invoice_uid')
                
                if invoice_sequence and invoice_uid:
                    # Get full invoice details
                    invoice_details = self.get_invoice_details(invoice_uid, invoice_sequence)
                    
                    if invoice_details['success']:
                        invoice_data = invoice_details['data']
                        
                        # Construct payment URL (assuming it follows a pattern)
                        payment_url = f"https://stu.easy-adds.com/invoice/{invoice_uid}/{invoice_sequence}"
                        
                        result_data = {
                            'invoice_sequence': invoice_sequence,
                            'invoice_uid': invoice_uid,
                            'payment_url': payment_url,
                            'invoice_details': invoice_data,
                            'amount': amount,
                            'customer_phone': customer_phone,
                            'profile_id': profile_id,
                            'payment_method': self.payment_method,
                            'created_at': timezone.now().isoformat()
                        }
                        
                        logger.info(f"✓ EasyPay invoice created successfully for pill {pill.pill_number}")
                        logger.info(f"  - Invoice UID: {invoice_uid}")
                        logger.info(f"  - Invoice Sequence: {invoice_sequence}")
                        logger.info(f"  - Payment URL: {payment_url}")
                        
                        return {
                            'success': True,
                            'data': result_data
                        }
                    else:
                        logger.error(f"Failed to get invoice details: {invoice_details['error']}")
                        return {
                            'success': False,
                            'error': f"Invoice created but failed to get details: {invoice_details['error']}"
                        }
                else:
                    logger.error(f"Missing invoice_sequence or invoice_uid in response: {response_data}")
                    return {
                        'success': False,
                        'error': 'Invalid response from EasyPay API - missing invoice identifiers'
                    }
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', f'HTTP {response.status_code}')
                except:
                    error_message = f'HTTP {response.status_code}: {response.text}'
                
                logger.error(f"EasyPay API error: {error_message}")
                return {
                    'success': False,
                    'error': f'EasyPay API error: {error_message}'
                }
                
        except requests.exceptions.Timeout:
            logger.error("EasyPay API request timed out")
            return {
                'success': False,
                'error': 'EasyPay API request timed out'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"EasyPay API request failed: {str(e)}")
            return {
                'success': False,
                'error': f'EasyPay API request failed: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error creating EasyPay invoice: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }

    def get_invoice_details(self, invoice_uid, invoice_sequence):
        """Get invoice details from EasyPay"""
        try:
            url = f"{self.get_invoice_url}/{invoice_uid}/{invoice_sequence}/"
            
            logger.info(f"Getting EasyPay invoice details from: {url}")
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30
            )
            
            logger.info(f"EasyPay get invoice response status: {response.status_code}")
            logger.info(f"EasyPay get invoice response: {response.text}")
            
            # Accept both 200 (OK) and 201 (Created) as successful responses
            if response.status_code in [200, 201]:
                invoice_data = response.json()
                return {
                    'success': True,
                    'data': invoice_data
                }
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', f'HTTP {response.status_code}')
                except:
                    error_message = f'HTTP {response.status_code}: {response.text}'
                
                logger.error(f"Failed to get EasyPay invoice details: {error_message}")
                return {
                    'success': False,
                    'error': error_message
                }
                
        except Exception as e:
            logger.error(f"Error getting EasyPay invoice details: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def check_payment_status(self, invoice_uid, invoice_sequence):
        """Check payment status with EasyPay"""
        try:
            invoice_details = self.get_invoice_details(invoice_uid, invoice_sequence)
            
            if invoice_details['success']:
                data = invoice_details['data']
                payment_status = data.get('payment_status', 'unknown')
                
                return {
                    'success': True,
                    'data': {
                        'payment_status': payment_status,
                        'invoice_data': data
                    }
                }
            else:
                return {
                    'success': False,
                    'error': invoice_details['error']
                }
                
        except Exception as e:
            logger.error(f"Error checking EasyPay payment status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def verify_webhook_signature(self, amount, customer_phone, received_signature):
        """Verify webhook signature from EasyPay"""
        try:
            # Pattern for webhook: amount + customer_phone + secret_key
            string_to_hash = f"{amount}{customer_phone}{self.secret_key}"
            expected_signature = hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()
            
            logger.debug(f"Webhook verification - String to hash: {string_to_hash}")
            logger.debug(f"Expected signature: {expected_signature}")
            logger.debug(f"Received signature: {received_signature}")
            
            return expected_signature == received_signature
            
        except Exception as e:
            logger.error(f"Error verifying EasyPay webhook signature: {str(e)}")
            return False

    def check_invoice_status(self, fawry_ref):
        """Check invoice status from EasyPay using Fawry reference"""
        try:
            logger.info(f"Checking EasyPay invoice status for Fawry ref: {fawry_ref}")
            
            # EasyPay invoice status check URL
            status_check_url = f"{self.base_url}/invoice-status-check/"
            
            # Parameters for the request
            params = {
                'vendor_code': self.vendor_code,
                'fawry_ref': fawry_ref
            }
            
            # Make API request
            response = requests.get(
                status_check_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            
            logger.info(f"EasyPay status check response status: {response.status_code}")
            logger.info(f"EasyPay status check response: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                return {
                    'success': True,
                    'data': response_data
                }
            else:
                logger.error(f"EasyPay status check failed with status {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}",
                    'response': response.text
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during EasyPay status check: {str(e)}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EasyPay status check response: {str(e)}")
            return {
                'success': False,
                'error': f"Invalid JSON response: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error during EasyPay status check: {str(e)}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }


# Create a singleton instance
easypay_service = EasyPayService()