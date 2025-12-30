from django.conf import settings
from datetime import datetime, timedelta
import boto3

# Generate presigned URL valid for 1 hour

def generate_upload_url(object_name):
    s3 = boto3.client(
        "s3",
        region_name="auto",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
    )

    url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': object_name},
        ExpiresIn=3600
    )
    return url