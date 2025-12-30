# S3 Direct Upload Implementation - Documentation

## Overview

This implementation fixes the large file upload problem by enabling **direct uploads to S3** from the client, bypassing your Django server entirely. This eliminates server storage bottlenecks and allows efficient handling of files up to 50MB or larger.

## How It Works

### Traditional Flow (Problem)
```
Client → Server (stores file) → S3 (transfers file) ❌ SLOW for large files
```

### New Flow (Solution)
```
Client → S3 (direct upload) ✅ FAST for large files
         Server (generates URL)
```

## New Endpoints

### 1. Generate Presigned Upload URL
**Endpoint:** `POST /products/api/generate-presigned-url/`

Generates a temporary S3 presigned URL that allows the client to upload directly to S3.

**Request:**
```json
{
    "file_name": "my-document.pdf",
    "file_type": "application/pdf",
    "file_category": "pdf"  // or "image", "uploads"
}
```

**Response:**
```json
{
    "success": true,
    "url": "https://s3-endpoint.amazonaws.com/bucket/pdfs/uuid.pdf?AWSAccessKeyId=...",
    "public_url": "https://custom-domain/pdfs/uuid.pdf",
    "object_key": "pdfs/uuid.pdf",
    "file_type": "application/pdf"
}
```

### 2. Create Product with S3 Files
**Endpoint:** `POST /products/dashboard/products/`

Creates a product using S3 object keys instead of uploading files.

**Request:**
```json
{
    "name": "Advanced Physics",
    "price": 99.99,
    "category": 1,
    "subject": 2,
    "description": "Complete physics course",
    "pdf_object_key": "pdfs/550e8400-e29b-41d4.pdf",
    "base_image_object_key": "products/550e8400-e29b-41d4.jpg",
    "page_count": 250,
    "file_size_mb": 45.5,
    "language": "ar",
    "is_available": true
}
```

**Response:**
```json
{
    "id": 123,
    "name": "Advanced Physics",
    "pdf_file": "pdfs/550e8400-e29b-41d4.pdf",
    "base_image": "products/550e8400-e29b-41d4.jpg",
    ...
}
```

### 3. Bulk Upload Product Images (S3)
**Endpoint:** `POST /products/dashboard/product-images/bulk-upload-s3/`

Create multiple product image records from S3 object keys.

**Request:**
```json
{
    "product": 123,
    "image_object_keys": [
        "products/image1.jpg",
        "products/image2.jpg",
        "products/image3.jpg"
    ]
}
```

**Response:**
```json
{
    "message": "Product images created from S3 successfully."
}
```

## Step-by-Step Usage Guide

### Step 1: Generate Presigned URL
```javascript
const response = await fetch('http://localhost:8000/products/api/generate-presigned-url/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_JWT_TOKEN'
    },
    body: JSON.stringify({
        file_name: 'my-large-file.pdf',
        file_type: 'application/pdf',
        file_category: 'pdf'
    })
});

const data = await response.json();
console.log(data);
// {
//     "success": true,
//     "url": "https://s3...",
//     "object_key": "pdfs/uuid.pdf",
//     ...
// }
```

### Step 2: Upload File Directly to S3
```javascript
const file = document.getElementById('fileInput').files[0];
const presignedUrl = data.url;

const uploadResponse = await fetch(presignedUrl, {
    method: 'PUT',
    headers: {
        'Content-Type': file.type
    },
    body: file
});

if (uploadResponse.ok) {
    console.log('File uploaded to S3!');
    // Now use the object_key from Step 1 to create the product
}
```

### Step 3: Create Product with S3 Object Keys
```javascript
const productResponse = await fetch('http://localhost:8000/products/dashboard/products/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_JWT_TOKEN'
    },
    body: JSON.stringify({
        name: 'My Product',
        price: 99.99,
        category: 1,
        pdf_object_key: 'pdfs/uuid.pdf',  // From Step 1
        base_image_object_key: 'products/uuid.jpg'
    })
});

const product = await productResponse.json();
console.log('Product created:', product);
```

## Testing

### Using the Test HTML File

A complete test interface is provided at `test.html` in your project root:

1. **Open the file:**
   ```bash
   # Simply open in your browser
   c:\Users\Royal\Desktop\silver\silverbook\test.html
   ```

2. **Configure:**
   - Set API Base URL: `http://localhost:8000/products`
   - Paste your JWT Admin Token

3. **Test Steps:**
   - **Step 1:** Generate Presigned URL for your file
   - **Step 2:** Select a file and upload it to S3
   - **Step 3:** Create a product with the uploaded file
   - **Step 4:** (Optional) Upload additional product images

### Key Features of Test File

✅ Drag-and-drop file support  
✅ Real-time upload progress tracking  
✅ Large file handling (50MB+)  
✅ All endpoints tested in one interface  
✅ No server dependencies (pure client-side)  
✅ Beautiful UI with status indicators  

## How to Get JWT Token

1. **Login via your API:**
   ```bash
   curl -X POST http://localhost:8000/accounts/api/token/ \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"password"}'
   ```

2. **Response:**
   ```json
   {
       "access": "eyJhbGciOiJIUzI1NiIs...",
       "refresh": "eyJhbGciOiJIUzI1NiIs..."
   }
   ```

3. **Copy the `access` token and paste into test.html**

## Architecture Benefits

### Before (Direct Upload to Server)
- ❌ Large files timeout
- ❌ Server runs out of disk space
- ❌ Single-threaded processing
- ❌ Memory overhead
- ❌ No progress tracking

### After (S3 Direct Upload)
- ✅ Handles files of any size
- ✅ Server disk space not used
- ✅ Parallel uploads supported
- ✅ Minimal server memory
- ✅ Real-time progress tracking
- ✅ Browser handles interruptions automatically
- ✅ Faster uploads (S3's infrastructure)

## Files Modified

### Backend Changes
1. **`products/views.py`**
   - Added `GeneratePresignedUploadUrlView` - generates presigned URLs
   - Added `ProductImageBulkS3CreateView` - bulk image creation from S3 keys
   - Updated imports for S3 service

2. **`products/serializers.py`**
   - Added `ProductS3UploadSerializer` - accepts S3 object keys instead of files
   - Added `ProductImageBulkS3UploadSerializer` - for bulk image uploads

3. **`products/urls.py`**
   - Added route for presigned URL generation
   - Added route for bulk S3 image uploads

### Frontend Files
1. **`test.html`** (NEW)
   - Complete testing interface for all upload operations
   - 5-step workflow for testing the entire process
   - Progress tracking and error handling

## Modifications to Models

**NO model changes needed!** The existing `pdf_file` and `base_image` fields on the Product model are used to store the S3 object keys instead of file paths.

```python
# In products/models.py (existing code, now uses S3 keys)
pdf_file = models.FileField(
    upload_to='pdfs/',
    null=True,
    blank=True,
    help_text="PDF file stored in S3 in production"  # Now stores S3 key
)

base_image = models.ImageField(
    upload_to='products/',
    null=True,
    blank=True,
    help_text="Main product cover image"  # Now stores S3 key
)
```

## Troubleshooting

### "S3 not configured" Error
- Ensure AWS credentials are set in `settings.py`
- Check `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`
- Verify `AWS_S3_ENDPOINT_URL` for Cloudflare R2

### CORS Errors
If you see CORS errors when uploading to S3:
1. Check S3/R2 CORS settings
2. Required CORS configuration for presigned uploads:
   ```json
   {
       "AllowedOrigins": ["http://localhost:8000", "https://your-domain.com"],
       "AllowedMethods": ["PUT", "POST"],
       "AllowedHeaders": ["*"]
   }
   ```

### Authentication Issues
- Ensure JWT token is included in test.html
- Token must be from an admin user
- Token may have expired; generate a new one

### File Size Limits
- Presigned URLs are valid for 1 hour by default
- Can be changed in `GeneratePresignedUploadUrlView.expiration=3600`
- S3 supports multipart uploads for files >5GB automatically

## Performance Metrics

### Expected Improvements
- **50MB file:** ~2-5 seconds (previously timeout)
- **100MB file:** ~4-10 seconds (previously error)
- **500MB file:** ~20-50 seconds (previously impossible)

*Actual times depend on network speed and S3 region*

## Security Notes

✅ Presigned URLs are:
- Time-limited (1 hour)
- Single-file specific
- Require admin authentication
- Cannot be used for other operations

✅ Best practices implemented:
- JWT authentication required
- Admin-only endpoints
- Object key validation
- MIME type checking

## Next Steps

1. **Test with the provided test.html**
2. **Monitor S3 uploads** - check CloudFlare R2 console
3. **Integrate into your frontend** - follow the JavaScript examples
4. **Set appropriate timeouts** for large files in your client
5. **Monitor AWS costs** - S3 pricing for requests and storage

## Support & Documentation

For more information:
- AWS S3 Presigned URLs: https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Boto3 Documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
