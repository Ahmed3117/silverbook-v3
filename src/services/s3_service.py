"""
S3/Cloudflare R2 Storage Service

This service provides utilities for:
1. Generating presigned URLs for secure file access (e.g., purchased PDFs)
2. Generating presigned URLs for direct uploads
3. Managing files in S3/R2 storage

How it works:
- Files are stored in Cloudflare R2 (S3-compatible storage)
- Public files (images) are accessed via the custom domain: easy.easy-stream.net
- Private files (PDFs) use presigned URLs that expire after a set time
"""

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class S3Service:
    """
    Service for managing S3/R2 storage operations
    
    Usage:
        from services.s3_service import s3_service
        
        # Get a presigned URL for a PDF (valid for 1 hour)
        url = s3_service.generate_presigned_download_url('pdfs/book.pdf', expiration=3600)
        
        # Generate upload URL for direct browser uploads
        url = s3_service.generate_presigned_upload_url('uploads/file.pdf')
    """
    
    def __init__(self):
        self.access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        self.secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        self.endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        self.custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
        self.region = getattr(settings, 'AWS_S3_REGION_NAME', 'auto')
        
        self._client = None
        
    @property
    def client(self):
        """Lazy initialization of S3 client"""
        if self._client is None:
            if not all([self.access_key, self.secret_key, self.bucket_name, self.endpoint_url]):
                logger.warning("S3 credentials not fully configured")
                return None
                
            self._client = boto3.client(
                's3',
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
        return self._client
    
    def is_configured(self):
        """Check if S3 is properly configured"""
        return self.client is not None
    
    def generate_presigned_download_url(self, object_key, expiration=3600):
        """
        Generate a presigned URL for downloading a file
        
        Args:
            object_key: The path/key of the file in S3 (e.g., 'pdfs/book.pdf')
            expiration: URL validity in seconds (default: 1 hour)
            
        Returns:
            dict: {'success': True, 'url': '...'} or {'success': False, 'error': '...'}
            
        Example:
            # For a PDF stored at pdfs/my-book.pdf
            result = s3_service.generate_presigned_download_url('pdfs/my-book.pdf', expiration=7200)
            if result['success']:
                download_url = result['url']  # Valid for 2 hours
        """
        if not self.client:
            return {'success': False, 'error': 'S3 not configured'}
            
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned download URL for: {object_key}")
            return {'success': True, 'url': url}
            
        except ClientError as e:
            logger.error(f"Error generating presigned download URL: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_presigned_upload_url(self, object_key, expiration=3600, content_type=None):
        """
        Generate a presigned URL for uploading a file directly from browser
        
        Args:
            object_key: The path/key where file will be stored (e.g., 'uploads/file.pdf')
            expiration: URL validity in seconds (default: 1 hour)
            content_type: Optional MIME type (e.g., 'application/pdf')
            
        Returns:
            dict: {'success': True, 'url': '...', 'public_url': '...'} or {'success': False, 'error': '...'}
            
        Example:
            # Generate URL for browser-side upload
            result = s3_service.generate_presigned_upload_url(
                'pdfs/new-book.pdf',
                content_type='application/pdf'
            )
            # Frontend can PUT file directly to result['url']
        """
        if not self.client:
            return {'success': False, 'error': 'S3 not configured'}
            
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': object_key
            }
            
            if content_type:
                params['ContentType'] = content_type
            
            url = self.client.generate_presigned_url(
                'put_object',
                Params=params,
                ExpiresIn=expiration
            )
            
            # Public URL after upload (via custom domain)
            public_url = f"https://{self.custom_domain}/{object_key}"
            
            logger.info(f"Generated presigned upload URL for: {object_key}")
            return {
                'success': True,
                'url': url,
                'public_url': public_url,
                'object_key': object_key
            }
            
        except ClientError as e:
            logger.error(f"Error generating presigned upload URL: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_public_url(self, object_key):
        """
        Get the public URL for a file (via custom domain)
        
        Args:
            object_key: The path/key of the file in S3
            
        Returns:
            str: The public URL
            
        Example:
            url = s3_service.get_public_url('products/image.jpg')
            # Returns: https://easy.easy-stream.net/products/image.jpg
        """
        if self.custom_domain:
            return f"https://{self.custom_domain}/{object_key}"
        return None
    
    def delete_file(self, object_key):
        """
        Delete a file from S3
        
        Args:
            object_key: The path/key of the file to delete
            
        Returns:
            dict: {'success': True} or {'success': False, 'error': '...'}
        """
        if not self.client:
            return {'success': False, 'error': 'S3 not configured'}
            
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            
            logger.info(f"Deleted file from S3: {object_key}")
            return {'success': True}
            
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return {'success': False, 'error': str(e)}
    
    def file_exists(self, object_key):
        """
        Check if a file exists in S3
        
        Args:
            object_key: The path/key of the file
            
        Returns:
            bool: True if file exists, False otherwise
        """
        if not self.client:
            return False
            
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return True
        except ClientError:
            return False
    
    def list_files(self, prefix='', max_keys=1000):
        """
        List files in S3 with optional prefix filter
        
        Args:
            prefix: Filter by prefix (e.g., 'pdfs/' for all PDFs)
            max_keys: Maximum number of files to return
            
        Returns:
            dict: {'success': True, 'files': [...]} or {'success': False, 'error': '...'}
        """
        if not self.client:
            return {'success': False, 'error': 'S3 not configured'}
            
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'public_url': self.get_public_url(obj['Key'])
                })
            
            return {'success': True, 'files': files, 'count': len(files)}
            
        except ClientError as e:
            logger.error(f"Error listing files from S3: {e}")
            return {'success': False, 'error': str(e)}


# Singleton instance
s3_service = S3Service()
