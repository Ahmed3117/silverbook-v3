from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import get_authorization_header
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect
from django.utils import timezone
import json
import logging
import time

from products.models import Pill
from services.fawaterak_service import fawaterak_service
from services.shakeout_service import shakeout_service  # Add Shake-out service import
from services.easypay_service import easypay_service  # Add EasyPay service import

logger = logging.getLogger(__name__)


def _serialize_easypay_invoice(pill, attempts=0):
    data = pill.easypay_data or {}
    payment_url = data.get('payment_url') or pill.easypay_payment_url
    amount = data.get('amount') or pill.final_price()
    invoice_details = data.get('invoice_details', {}) if isinstance(data, dict) else {}
    fawry_ref = (
        invoice_details.get('fawry_ref')
        or data.get('fawry_ref')
        or pill.easypay_fawry_ref
    )

    return {
        'invoice_uid': pill.easypay_invoice_uid,
        'invoice_sequence': pill.easypay_invoice_sequence,
        'payment_url': payment_url,
        'amount': str(amount) if amount is not None else None,
        'pill_number': pill.pill_number,
        'payment_method': data.get('payment_method', 'fawry'),
        'payment_gateway': 'easypay',
        'fawry_ref': fawry_ref,
        'attempts': attempts
    }


def _serialize_shakeout_invoice(pill):
    data = pill.shakeout_data or {}
    payment_url = data.get('payment_url') or data.get('url') or pill.shakeout_payment_url
    total_amount = data.get('total_amount') or float(pill.final_price())

    return {
        'invoice_id': pill.shakeout_invoice_id,
        'invoice_ref': pill.shakeout_invoice_ref,
        'payment_url': payment_url,
        'total_amount': total_amount,
        'payment_gateway': 'shakeout'
    }

def is_fawry_ref_error(fawry_ref):
    """Check if fawry_ref contains an error"""
    if not fawry_ref:
        return True
    
    # Convert to string if it's not already
    fawry_ref_str = str(fawry_ref)
    
    # Check if it contains error indicators
    error_indicators = ['error', 'Error', 'ERROR', 'Invalid Merchant Code', 'statusCode', 'statusDescription']
    
    for indicator in error_indicators:
        if indicator in fawry_ref_str:
            return True
    
    # Check if it looks like a JSON error response
    try:
        if fawry_ref_str.startswith('{') and 'error' in fawry_ref_str.lower():
            return True
    except:
        pass
    
    return False

class CustomJWTAuthentication(JWTAuthentication):
    """Custom JWT authentication that checks both 'Authorization' and 'auth' headers"""
    
    def get_header(self, request):
        """
        Extracts the header containing the JSON web token from the given request.
        """
        # First try standard Authorization header
        header = request.META.get('HTTP_AUTHORIZATION')
        if header:
            return header.encode('iso-8859-1')
        
        # Then try custom 'auth' header
        header = request.META.get('HTTP_AUTH')
        if header:
            return header.encode('iso-8859-1')
        
        return None


class CreatePaymentView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pill_id):
        """Create a Fawaterak payment for a pill"""
        try:
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            
            # Check if pill is already paid
            if pill.status == 'p':
                return Response({
                    'success': False,
                    'error': 'This order is already paid',
                    'pill_number': pill.pill_number,
                    'status': 'already_paid'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create payment invoice
            result = fawaterak_service.create_payment_invoice(pill)
            
            if result['success']:
                pill.status = 'w'
                pill.payment_gateway = 'fawaterak'
                pill.save(update_fields=['status', 'payment_gateway'])
                return Response({
                    'success': True,
                    'message': 'Payment invoice created successfully',
                    'data': {
                        'payment_url': result['data']['payment_url'],
                        'invoice_id': result['data']['invoice_id'],
                        'reference_id': result['data']['reference_id'],
                        'total_amount': result['data']['total_amount'],
                        'pill_number': pill.pill_number,
                        'currency': 'EGP'
                    },
                    'status': 'payment_created'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': result['error'],
                    'pill_number': pill.pill_number,
                    'status': 'creation_failed'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error creating payment for pill {pill_id}: {e}")
            return Response({
                'success': False,
                'error': 'An error occurred while creating payment',
                'status': 'server_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckPaymentStatusView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pill_id):
        """Check payment status for a pill"""
        try:
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            
            if pill.status == 'p':
                return Response({
                    'success': True,
                    'message': 'Payment confirmed',
                    'data': {
                        'pill_number': pill.pill_number,
                        'paid': True,
                        'status': 'confirmed',
                        'total_amount': float(pill.final_price()),
                        'currency': 'EGP'
                    }
                }, status=status.HTTP_200_OK)
            
            # FIXED: Check cache first, if not found, try alternative status check
            from django.core.cache import cache
            cached_data = cache.get(f'fawaterak_invoice_{pill.pill_number}')
            
            if cached_data:
                # We have cached data, use Fawaterak service
                result = fawaterak_service.get_invoice_status(pill.pill_number)
            else:
                # No cached data, try direct API call or return pending status
                logger.warning(f"No cached invoice data for pill {pill.pill_number}, checking with basic status")
                
                # Return a basic pending status since we don't have cache data
                return Response({
                    'success': True,
                    'message': 'Payment status check in progress',
                    'data': {
                        'pill_number': pill.pill_number,
                        'paid': False,
                        'status': 'pending',
                        'total_amount': float(pill.final_price()),
                        'currency': 'EGP',
                        'note': 'Invoice data not in cache - payment may still be processing'
                    }
                }, status=status.HTTP_200_OK)
            
            if result['success']:
                invoice_data = result['data']
                payment_status = invoice_data.get('status', '').lower()
                
                if payment_status in ['paid', 'success', 'completed']:
                    pill.status = 'p'
                    pill.save(update_fields=['status'])
                    
                    return Response({
                        'success': True,
                        'message': 'Payment confirmed',
                        'data': {
                            'pill_number': pill.pill_number,
                            'paid': True,
                            'status': 'confirmed',
                            'total_amount': float(pill.final_price()),
                            'currency': 'EGP',
                            'paid_at': invoice_data.get('paid_at')
                        }
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': True,
                        'message': 'Payment still processing',
                        'data': {
                            'pill_number': pill.pill_number,
                            'paid': False,
                            'status': payment_status,
                            'total_amount': float(pill.final_price()),
                            'currency': 'EGP'
                        }
                    }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': result['error'],
                    'data': {
                        'pill_number': pill.pill_number,
                        'paid': False,
                        'status': 'unknown'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error checking payment status: {e}")
            return Response({
                'success': False,
                'error': 'Error checking payment status',
                'status': 'server_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['POST'])
@permission_classes([])  # No authentication required for webhooks
def fawaterak_webhook(request):
    print("-------------------------------------------")
    print('i am in webhook view')
    print("-------------------------------------------")
    
    try:
        webhook_data = request.data if hasattr(request, 'data') else json.loads(request.body.decode('utf-8'))
        logger.info(f"Received Fawaterak webhook: {webhook_data}")

        # Ensure pay_load is a dict
        pay_load = webhook_data.get('pay_load')
        if isinstance(pay_load, str):
            pay_load = json.loads(pay_load)

        if webhook_data.get('invoice_status') == 'paid':
            pill_number = pay_load.get('pill_number')
            pill = Pill.objects.get(pill_number=pill_number)
            pill.status = 'p'
            pill.invoice_id = webhook_data.get('invoice_id')
            pill.save(update_fields=['status', 'invoice_id'])

            return Response({
                'success': True,
                'message': 'Webhook processed successfully',
                'data': webhook_data
            }, status=status.HTTP_200_OK)
        else:
            logger.error(f"Webhook processing failed: {webhook_data.get('error', 'No error message')}")
            return Response({
                'success': False,
                'error': webhook_data.get('error', 'Unknown error')
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Exception in webhook handler")
        return Response({
            'success': False,
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class PaymentSuccessView(APIView):
    permission_classes = []  # No authentication required for callbacks
    
    def get(self, request, pill_number):
        """
        Handle successful payment return - Process and redirect to frontend
        """
        try:
            pill = get_object_or_404(Pill, pill_number=pill_number)
            
            # Verify payment status from Fawaterak
            result = fawaterak_service.get_invoice_status(pill_number)
            
            if result['success']:
                invoice_data = result['data']
                payment_status = invoice_data.get('status', '').lower()
                
                if payment_status in ['paid', 'success', 'completed']:
                    pill.status = 'p'
                    pill.save(update_fields=['status'])
                    
                    logger.info(f"✓ Payment SUCCESS confirmed for pill {pill_number}")
                    
                    # Redirect to frontend success page
                    frontend_url = f"https://bookefay.com/profile/orders?pill_number={pill_number}&payment_status=success&amount={pill.final_price()}"
                    return redirect(frontend_url)
                else:
                    logger.warning(f"Payment status still pending for pill {pill_number}: {payment_status}")
                    # Redirect to frontend pending page  
                    frontend_url = f"https://bookefay.com?pill_number={pill_number}&payment_status=pending&amount={pill.final_price()}"
                    return redirect(frontend_url)
            else:
                logger.error(f"Could not verify payment status for pill {pill_number}")
                # Redirect to frontend with error
                frontend_url = f"https://bookefay.com/profile?pill_number={pill_number}&payment_status=error&amount={pill.final_price()}"
                return redirect(frontend_url)
                
        except Exception as e:
            logger.error(f"Error in payment success: {e}")
            # Redirect to frontend with error
            frontend_url = f"https://bookefay.com/profile?pill_number={pill_number}&payment_status=error"
            return redirect(frontend_url)

class PaymentFailedView(APIView):
    permission_classes = []  # No authentication required for callbacks
    
    def get(self, request, pill_number):
        """
        Handle failed payment return - Process and redirect to frontend
        """
        try:
            pill = get_object_or_404(Pill, pill_number=pill_number)
            
            logger.info(f"✗ Payment FAILED for pill {pill_number}")
            
            # Redirect to frontend failure page
            frontend_url = f"https://bookefay.com/profile?pill_number={pill_number}&payment_status=failed&amount={pill.final_price()}"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Error in payment failed: {e}")
            # Redirect to frontend with error
            frontend_url = f"https://bookefay.com/profile?pill_number={pill_number}&payment_status=error"
            return redirect(frontend_url)

class PaymentPendingView(APIView):
    permission_classes = []  # No authentication required for callbacks
    
    def get(self, request, pill_number):
        """
        Handle pending payment return - Process and redirect to frontend
        """
        try:
            pill = get_object_or_404(Pill, pill_number=pill_number)
            
            logger.info(f"⏳ Payment PENDING for pill {pill_number}")
            
            # Redirect to frontend pending page
            frontend_url = f"https://bookefay.com?pill_number={pill_number}&payment_status=pending&amount={pill.final_price()}"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Error in payment pending: {e}")
            # Redirect to frontend with error
            frontend_url = f"https://bookefay.com?pill_number={pill_number}&payment_status=error"
            return redirect(frontend_url)

class CreateShakeoutInvoiceView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pill_id):
        """Create a Shake-out invoice for a pill"""
        try:
            logger.info(f"Starting Shake-out invoice creation for pill {pill_id}, user: {request.user}")
            
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            logger.info(f"Pill found: {pill.pill_number}")
            
            # Check if pill already has a Shake-out invoice
            if pill.shakeout_invoice_id:
                # Check if the existing invoice is expired or invalid
                if pill.is_shakeout_invoice_expired():
                    logger.info(f"Existing Shake-out invoice {pill.shakeout_invoice_id} for pill {pill_id} is expired/invalid - creating new one")
                    
                    # Clear old invoice data to create a new one
                    pill.shakeout_invoice_id = None
                    pill.shakeout_invoice_ref = None
                    pill.shakeout_data = None
                    pill.shakeout_created_at = None
                    pill.save(update_fields=['shakeout_invoice_id', 'shakeout_invoice_ref', 'shakeout_data', 'shakeout_created_at'])
                else:
                    logger.warning(f"Pill {pill_id} already has active Shake-out invoice: {pill.shakeout_invoice_id}")
                    return Response({
                        'success': True,
                        'message': 'Shakeout invoice already exists',
                        'data': _serialize_shakeout_invoice(pill)
                    }, status=status.HTTP_200_OK)
            
            # Check stock availability before creating invoice
            logger.info(f"Checking stock availability for pill {pill_id}")
            availability_check = pill.check_all_items_availability()
            
            if not availability_check['all_available']:
                logger.warning(f"Stock problems found for pill {pill_id}: {availability_check['problem_items_count']} items")
                
                # Create detailed error message for each problem item
                problem_details = []
                for item in availability_check['problem_items']:
                    if item['reason'] == 'out_of_stock':
                        problem_details.append(f"{item['product_name']} غير متاح حالياً")
                    elif item['reason'] == 'insufficient_quantity':
                        problem_details.append(f"{item['product_name']} متاح فقط {item['available_quantity']} قطعة من أصل {item['required_quantity']} مطلوبة")
                    else:
                        problem_details.append(f"{item['product_name']} غير متاح")
                
                return Response({
                    'success': False,
                    'error_code': 'STOCK_UNAVAILABLE',
                    'error': 'هذا المنتج لم يعد متاحا الان , يمكنك حذفه من الفاتورة والاستكمال بباقى المنتجات او الذهاب للصفحة الرئيسية لانشاء فاتورة جديدة',
                    'details': {
                        'problem_items': availability_check['problem_items'],
                        'problem_details': problem_details,
                        'total_items': availability_check['total_items'],
                        'problem_items_count': availability_check['problem_items_count']
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"All items available for pill {pill_id}, proceeding with Shake-out invoice creation")
            
            # Try creating the invoice with retry logic for fawry_ref errors
            max_retries = 2  # Initial attempt + 1 retry
            retry_delay = 10  # 10 seconds
            
            for attempt in range(max_retries):
                logger.info(f"Shake-out invoice creation attempt {attempt + 1} for pill {pill_id}")
                
                result = shakeout_service.create_payment_invoice(pill)
                logger.info(f"shakeout_service.create_payment_invoice returned: {result}")
                
                if result['success']:
                    # Extract invoice data from successful response
                    invoice_id = result['data'].get('invoice_id', '')
                    invoice_ref = result['data'].get('invoice_ref', '')
                    
                    # Check if there's a fawry_ref in the response that might contain an error
                    fawry_ref = result['data'].get('fawry_ref', '')
                    if fawry_ref:
                        fawry_ref = str(fawry_ref)
                        
                        # Check if fawry_ref contains an error
                        if is_fawry_ref_error(fawry_ref):
                            logger.warning(f"Shake-out fawry_ref contains error on attempt {attempt + 1}: {fawry_ref}")
                            
                            if attempt < max_retries - 1:  # Not the last attempt
                                logger.info(f"Waiting {retry_delay} seconds before retry...")
                                time.sleep(retry_delay)
                                continue  # Retry
                            else:
                                # Last attempt failed, return error
                                logger.error(f"Shake-out fawry_ref still contains error after {max_retries} attempts")
                                return Response({
                                    'success': False,
                                    'error': f'Shake-out invoice creation failed: Invalid Fawry reference after {max_retries} attempts',
                                    'details': {
                                        'fawry_ref_error': fawry_ref,
                                        'attempts': max_retries
                                    },
                                    'pill_number': pill.pill_number
                                }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Invoice created successfully, proceed with saving
                    logger.info(f"Shake-out invoice created successfully on attempt {attempt + 1}")
                    
                    # Update pill with invoice data from successful response
                    pill.shakeout_invoice_id = result['data']['invoice_id']
                    pill.shakeout_invoice_ref = result['data']['invoice_ref']
                    pill.shakeout_data = result['data']
                    pill.shakeout_created_at = timezone.now()
                    pill.payment_gateway = 'shakeout'
                    pill.status = 'w'
                    pill.save(update_fields=['shakeout_invoice_id', 'shakeout_invoice_ref', 'shakeout_data', 'shakeout_created_at', 'payment_gateway', 'status'])
                    
                    return Response({
                        'success': True,
                        'message': result.get('message', 'Shake-out invoice created successfully'),
                        'data': {
                            'invoice_id': result['data']['invoice_id'],
                            'invoice_ref': result['data']['invoice_ref'],
                            'payment_url': result['data']['url'],
                            'total_amount': result['data']['total_amount'],
                            'pill_number': pill.pill_number,
                            'currency': result['data']['currency'],
                            'attempts': attempt + 1
                        }
                    }, status=status.HTTP_201_CREATED)
                else:
                    # Shake-out service returned an error
                    logger.error(f"Shake-out service error on attempt {attempt + 1}: {result['error']}")
                    
                    if attempt < max_retries - 1:  # Not the last attempt
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        continue  # Retry
                    else:
                        # Last attempt failed, return the service error
                        response_data = {
                            'success': False,
                            'error': result['error'],
                            'pill_number': pill.pill_number,
                            'attempts': max_retries
                        }
                        
                        # Include additional data if available (like existing invoice info)
                        if result.get('data'):
                            response_data['data'] = result['data']
                        
                        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Exception creating Shake-out invoice for pill {pill_id}: {str(e)}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Instantiate the views
create_payment_view = CreatePaymentView.as_view()
create_shakeout_invoice_view = CreateShakeoutInvoiceView.as_view()  # Add Shake-out view


class CreateEasyPayInvoiceView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pill_id):
        """Create an EasyPay invoice for a pill"""
        try:
            logger.info(f"Starting EasyPay invoice creation for pill {pill_id}, user: {request.user}")
            
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            logger.info(f"Pill found: {pill.pill_number}")
            
            # Check if pill already has an EasyPay invoice
            if pill.easypay_invoice_uid:
                # Check if the existing invoice is expired or invalid
                if pill.is_easypay_invoice_expired():
                    logger.info(f"Existing EasyPay invoice {pill.easypay_invoice_uid} for pill {pill_id} is expired/invalid - creating new one")
                    
                    # Clear old invoice data to create a new one
                    pill.easypay_invoice_uid = None
                    pill.easypay_invoice_sequence = None
                    pill.easypay_fawry_ref = None
                    pill.easypay_data = None
                    pill.easypay_created_at = None
                    pill.save(update_fields=['easypay_invoice_uid', 'easypay_invoice_sequence', 'easypay_fawry_ref', 'easypay_data', 'easypay_created_at'])
                else:
                    logger.warning(f"Pill {pill_id} already has active EasyPay invoice: {pill.easypay_invoice_uid}")
                    return Response({
                        'success': True,
                        'message': 'EasyPay invoice already exists',
                        'data': _serialize_easypay_invoice(pill, attempts=0)
                    }, status=status.HTTP_200_OK)
            
            # Check stock availability before creating invoice
            logger.info(f"Checking stock availability for pill {pill_id}")
            availability_check = pill.check_all_items_availability()
            
            if not availability_check['all_available']:
                logger.warning(f"Stock problems found for pill {pill_id}: {availability_check['problem_items_count']} items")
                
                # Create detailed error message for each problem item
                problem_details = []
                for item in availability_check['problem_items']:
                    if item['reason'] == 'out_of_stock':
                        problem_details.append(f"{item['product_name']} غير متاح حالياً")
                    elif item['reason'] == 'insufficient_quantity':
                        problem_details.append(f"{item['product_name']} متاح فقط {item['available_quantity']} قطعة من أصل {item['required_quantity']} مطلوبة")
                    else:
                        problem_details.append(f"{item['product_name']} غير متاح")
                
                return Response({
                    'success': False,
                    'error_code': 'STOCK_UNAVAILABLE',
                    'error': 'هذا المنتج لم يعد متاحا الان , يمكنك حذفه من الفاتورة والاستكمال بباقى المنتجات او الذهاب للصفحة الرئيسية لانشاء فاتورة جديدة',
                    'details': {
                        'problem_items': availability_check['problem_items'],
                        'problem_details': problem_details,
                        'total_items': availability_check['total_items'],
                        'problem_items_count': availability_check['problem_items_count']
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"All items available for pill {pill_id}, proceeding with EasyPay invoice creation")
            
            # Try creating the invoice with retry logic for fawry_ref errors
            max_retries = 2  # Initial attempt + 1 retry
            retry_delay = 10  # 10 seconds
            
            for attempt in range(max_retries):
                logger.info(f"EasyPay invoice creation attempt {attempt + 1} for pill {pill_id}")
                
                result = easypay_service.create_payment_invoice(pill)
                logger.info(f"easypay_service.create_payment_invoice returned: {result}")
                
                if result['success']:
                    # Extract invoice data from successful response
                    invoice_uid = result['data'].get('invoice_uid', '')
                    invoice_sequence = result['data'].get('invoice_sequence', '')
                    
                    # Safely extract fawry_ref from nested invoice_details
                    invoice_details = result['data'].get('invoice_details', {})
                    fawry_ref = invoice_details.get('fawry_ref', '')
                    if fawry_ref:
                        fawry_ref = str(fawry_ref)
                    
                    # Log field values for debugging
                    logger.info(f"EasyPay fields - UID: {invoice_uid}, Sequence: {invoice_sequence}, Fawry: {fawry_ref}")
                    
                    # Check if fawry_ref contains an error
                    if is_fawry_ref_error(fawry_ref):
                        logger.warning(f"EasyPay fawry_ref contains error on attempt {attempt + 1}: {fawry_ref}")
                        
                        if attempt < max_retries - 1:  # Not the last attempt
                            logger.info(f"Waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                            continue  # Retry
                        else:
                            # Last attempt failed, return error
                            logger.error(f"EasyPay fawry_ref still contains error after {max_retries} attempts")
                            return Response({
                                'success': False,
                                'error': f'EasyPay invoice creation failed: Invalid Fawry reference after {max_retries} attempts',
                                'details': {
                                    'fawry_ref_error': fawry_ref,
                                    'attempts': max_retries
                                },
                                'pill_number': pill.pill_number
                            }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # fawry_ref is valid, proceed with saving
                    logger.info(f"EasyPay invoice created successfully with valid fawry_ref on attempt {attempt + 1}")
                    
                    # Update pill fields
                    pill.easypay_invoice_uid = invoice_uid
                    pill.easypay_invoice_sequence = invoice_sequence
                    pill.easypay_fawry_ref = fawry_ref
                    pill.easypay_data = result['data']
                    pill.easypay_created_at = timezone.now()
                    pill.payment_gateway = 'easypay'
                    pill.status = 'w'
                    pill.save(update_fields=['easypay_invoice_uid', 'easypay_invoice_sequence', 'easypay_fawry_ref', 'easypay_data', 'easypay_created_at', 'payment_gateway', 'status'])

                    return Response({
                        'success': True,
                        'message': 'EasyPay invoice created successfully',
                        'data': _serialize_easypay_invoice(pill, attempts=attempt + 1)
                    }, status=status.HTTP_201_CREATED)
                else:
                    # EasyPay service returned an error
                    logger.error(f"EasyPay service error on attempt {attempt + 1}: {result['error']}")
                    
                    if attempt < max_retries - 1:  # Not the last attempt
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        continue  # Retry
                    else:
                        # Last attempt failed, return the service error
                        response_data = {
                            'success': False,
                            'error': result['error'],
                            'pill_number': pill.pill_number,
                            'attempts': max_retries
                        }
                        
                        # Include additional data if available (like existing invoice info)
                        if result.get('data'):
                            response_data['data'] = result['data']
                        
                        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Exception creating EasyPay invoice for pill {pill_id}: {str(e)}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreatePaymentInvoiceView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pill_id):
        """Create a payment invoice using the active payment gateway"""
        try:
            from django.conf import settings
            
            logger.info(f"Starting payment invoice creation for pill {pill_id}, user: {request.user}")
            
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            logger.info(f"Pill found: {pill.pill_number}")
            
            # Check stock availability before creating invoice
            logger.info(f"Checking stock availability for pill {pill_id}")
            availability_check = pill.check_all_items_availability()
            
            if not availability_check['all_available']:
                logger.warning(f"Stock problems found for pill {pill_id}: {availability_check['problem_items_count']} items")
                
                # Create detailed error message for each problem item
                problem_details = []
                for item in availability_check['problem_items']:
                    if item['reason'] == 'out_of_stock':
                        problem_details.append(f"{item['product_name']} غير متاح حالياً")
                    elif item['reason'] == 'insufficient_quantity':
                        problem_details.append(f"{item['product_name']} متاح فقط {item['available_quantity']} قطعة من أصل {item['required_quantity']} مطلوبة")
                    else:
                        problem_details.append(f"{item['product_name']} غير متاح")
                
                return Response({
                    'success': False,
                    'error_code': 'STOCK_UNAVAILABLE',
                    'error': 'هذا المنتج لم يعد متاحا الان , يمكنك حذفه من الفاتورة والاستكمال بباقى المنتجات او الذهاب للصفحة الرئيسية لانشاء فاتورة جديدة',
                    'details': {
                        'problem_items': availability_check['problem_items'],
                        'problem_details': problem_details,
                        'total_items': availability_check['total_items'],
                        'problem_items_count': availability_check['problem_items_count']
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"All items available for pill {pill_id}, proceeding with invoice creation")
            
            # Get active payment method from settings
            active_method = getattr(settings, 'ACTIVE_PAYMENT_METHOD', 'easypay').lower()
            logger.info(f"Active payment method: {active_method}")
            
            if active_method == 'easypay':
                # Use EasyPay
                if pill.easypay_invoice_uid and not pill.is_easypay_invoice_expired():
                    logger.warning(f"Pill {pill_id} already has active EasyPay invoice")
                    return Response({
                        'success': True,
                        'message': 'EasyPay invoice already exists',
                        'data': _serialize_easypay_invoice(pill, attempts=0)
                    }, status=status.HTTP_200_OK)
                
                # Try creating the invoice with retry logic for fawry_ref errors
                max_retries = 2  # Initial attempt + 1 retry
                retry_delay = 10  # 10 seconds
                
                for attempt in range(max_retries):
                    logger.info(f"EasyPay invoice creation attempt {attempt + 1} for pill {pill_id}")
                    
                    result = easypay_service.create_payment_invoice(pill)
                    
                    if result['success']:
                        # Extract invoice data from successful response
                        invoice_uid = result['data'].get('invoice_uid', '')
                        invoice_sequence = result['data'].get('invoice_sequence', '')
                        
                        # Safely extract fawry_ref from nested invoice_details
                        invoice_details = result['data'].get('invoice_details', {})
                        fawry_ref = invoice_details.get('fawry_ref', '')
                        if fawry_ref:
                            fawry_ref = str(fawry_ref)
                        
                        # Log field values for debugging
                        logger.info(f"EasyPay fields - UID: {invoice_uid}, Sequence: {invoice_sequence}, Fawry: {fawry_ref}")
                        
                        # Check if fawry_ref contains an error
                        if is_fawry_ref_error(fawry_ref):
                            logger.warning(f"EasyPay fawry_ref contains error on attempt {attempt + 1}: {fawry_ref}")
                            
                            if attempt < max_retries - 1:  # Not the last attempt
                                logger.info(f"Waiting {retry_delay} seconds before retry...")
                                time.sleep(retry_delay)
                                continue  # Retry
                            else:
                                # Last attempt failed, return error
                                logger.error(f"EasyPay fawry_ref still contains error after {max_retries} attempts")
                                return Response({
                                    'success': False,
                                    'error': f'EasyPay invoice creation failed: Invalid Fawry reference after {max_retries} attempts',
                                    'details': {
                                        'fawry_ref_error': fawry_ref,
                                        'attempts': max_retries
                                    },
                                    'payment_gateway': 'easypay'
                                }, status=status.HTTP_400_BAD_REQUEST)
                        
                        # fawry_ref is valid, proceed with saving
                        logger.info(f"EasyPay invoice created successfully with valid fawry_ref on attempt {attempt + 1}")
                        
                        # Update pill fields
                        pill.easypay_invoice_uid = invoice_uid
                        pill.easypay_invoice_sequence = invoice_sequence
                        pill.easypay_fawry_ref = fawry_ref
                        pill.easypay_data = result['data']
                        pill.easypay_created_at = timezone.now()
                        pill.payment_gateway = 'easypay'
                        pill.status = 'w'
                        pill.save(update_fields=['easypay_invoice_uid', 'easypay_invoice_sequence', 'easypay_fawry_ref', 'easypay_data', 'easypay_created_at', 'payment_gateway', 'status'])

                        return Response({
                            'success': True,
                            'message': 'EasyPay invoice created successfully',
                            'data': _serialize_easypay_invoice(pill, attempts=attempt + 1)
                        }, status=status.HTTP_201_CREATED)
                    else:
                        # EasyPay service returned an error
                        logger.error(f"EasyPay service error on attempt {attempt + 1}: {result['error']}")
                        
                        if attempt < max_retries - 1:  # Not the last attempt
                            logger.info(f"Waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                            continue  # Retry
                        else:
                            # Last attempt failed, return the service error
                            return Response({
                                'success': False,
                                'error': result['error'],
                                'payment_gateway': 'easypay',
                                'attempts': max_retries
                            }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({
                        'success': False,
                        'error': result['error'],
                        'payment_gateway': 'easypay'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            else:  # Default to shakeout
                # Use Shakeout
                if pill.shakeout_invoice_id and not pill.is_shakeout_invoice_expired():
                    logger.warning(f"Pill {pill_id} already has active Shakeout invoice")
                    return Response({
                        'success': True,
                        'message': 'Shakeout invoice already exists',
                        'data': _serialize_shakeout_invoice(pill)
                    }, status=status.HTTP_200_OK)
                
                result = shakeout_service.create_payment_invoice(pill)
                
                if result['success']:
                    pill.shakeout_invoice_id = result['data']['invoice_id']
                    pill.shakeout_invoice_ref = result['data']['invoice_ref']
                    pill.shakeout_data = result['data']
                    pill.shakeout_created_at = timezone.now()
                    pill.payment_gateway = 'shakeout'
                    pill.status = 'w'
                    pill.save(update_fields=['shakeout_invoice_id', 'shakeout_invoice_ref', 'shakeout_data', 'shakeout_created_at', 'payment_gateway', 'status'])
                    
                    return Response({
                        'success': True,
                        'message': 'Shakeout invoice created successfully',
                        'data': {
                            'invoice_id': result['data']['invoice_id'],
                            'invoice_ref': result['data']['invoice_ref'],
                            'payment_url': result['data']['url'],
                            'total_amount': result['data']['total_amount'],
                            'payment_gateway': 'shakeout'
                        }
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'success': False,
                        'error': result['error'],
                        'payment_gateway': 'shakeout'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Exception creating payment invoice for pill {pill_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckEasyPayInvoiceStatusView(APIView):
    # authentication_classes = [CustomJWTAuthentication]
    # permission_classes = [IsAuthenticated]
    
    def get(self, request, pill_id):
        """Check EasyPay invoice status and update pill if paid"""
        try:
            pill = get_object_or_404(Pill, id=pill_id)
            
            # Check if pill has EasyPay Fawry reference
            if not pill.easypay_fawry_ref:
                return Response({
                    'success': False,
                    'error': 'This pill does not have an EasyPay Fawry reference'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"Checking EasyPay status for pill {pill_id} with Fawry ref: {pill.easypay_fawry_ref}")
            
            # Use EasyPay service to check invoice status
            result = easypay_service.check_invoice_status(pill.easypay_fawry_ref)
            
            if not result['success']:
                logger.error(f"EasyPay status check failed for pill {pill_id}: {result['error']}")
                return Response({
                    'success': False,
                    'error': result['error'],
                    'payment_status': 'unknown'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Extract payment status from EasyPay response
            easypay_data = result['data']
            payment_status = easypay_data.get('payment_status', 'unknown')
            
            logger.info(f"EasyPay status for pill {pill_id}: {payment_status}")
            
            # Update pill if payment is confirmed in EasyPay but not in our system
            updated = False
            normalized_status = payment_status.lower()
            if normalized_status in ['paid', 'success', 'completed'] and pill.status != 'p':
                logger.info(f"Updating pill {pill_id} as paid (confirmed by EasyPay)")
                pill.status = 'p'  # Set status to paid
                pill.save(update_fields=['status'])
                updated = True
                
                # Grant purchased books to user - THIS IS CRITICAL for adding books after payment
                try:
                    pill.grant_purchased_books()
                    logger.info(f"✓ Purchased books granted for pill {pill_id}")
                except Exception as e:
                    logger.error(f"Failed to grant purchased books for pill {pill_id}: {str(e)}")
                
                logger.info(f"Pill {pill_id} payment status updated successfully")
            
            return Response({
                'success': True,
                'payment_status': payment_status,
                'updated': updated,
                'data': {
                    'pill_number': pill.pill_number,
                    'pill_id': pill.id,
                    'paid': pill.status == 'p',
                    'status': pill.get_status_display(),
                    'total_amount': float(pill.final_price()),
                    'currency': 'EGP',
                    'easypay_fawry_ref': pill.easypay_fawry_ref,
                    'easypay_payment_status': payment_status,
                    'easypay_data': easypay_data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Exception checking EasyPay status for pill {pill_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Server error: {str(e)}',
                'payment_status': 'unknown'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# Instantiate the new views
create_easypay_invoice_view = CreateEasyPayInvoiceView.as_view()
create_payment_invoice_view = CreatePaymentInvoiceView.as_view()
payment_success_view = PaymentSuccessView.as_view()
payment_failed_view = PaymentFailedView.as_view()
payment_pending_view = PaymentPendingView.as_view()
check_payment_status_view = CheckPaymentStatusView.as_view()
check_easypay_invoice_status_view = CheckEasyPayInvoiceStatusView.as_view()
