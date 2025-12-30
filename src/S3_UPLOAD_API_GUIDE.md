# S3 Direct Upload API Guide

A step-by-step guide for frontend developers to implement the product creation flow with direct S3 uploads.

---

## Overview

This flow allows uploading large files (PDFs, images) directly to S3/R2 storage without passing through the server, then creating products with references to those uploaded files.

**Base URL:** `http://localhost:9000/products`

---

## Step 1: Get Presigned Upload URL

Get a presigned URL to upload a file directly to S3.

### Endpoint
```
POST /products/api/generate-presigned-url/
```

### Headers
```
Content-Type: application/json
```

### Request Body
```json
{
  "file_name": "my-document.pdf",
  "file_type": "application/pdf",
  "file_category": "pdf"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_name` | string | Yes | Original filename with extension |
| `file_type` | string | Yes | MIME type (e.g., `application/pdf`, `image/jpeg`) |
| `file_category` | string | Yes | `pdf`, `image`, or `uploads` |

### Response (Success - 200)
```json
{
  "success": true,
  "url": "https://s3-presigned-url...",
  "public_url": "https://easy.easy-stream.net/pdfs/uuid-filename.pdf",
  "object_key": "pdfs/a1b2c3d4-5678-90ab-cdef.pdf"
}
```

| Field | Description |
|-------|-------------|
| `url` | Presigned URL for uploading (PUT request) |
| `public_url` | Public URL after upload completes |
| `object_key` | S3 key to use when creating the product |

### Response (Error - 400)
```json
{
  "success": false,
  "error": "file_name is required"
}
```

---

## Step 2: Upload File to S3

Upload the file directly to S3 using the presigned URL from Step 1.

### Endpoint
```
PUT {presigned_url_from_step_1}
```

### Headers
```
Content-Type: {same file_type used in Step 1}
```

### Request Body
```
Raw file binary data
```

### Response (Success - 200)
Empty response body (HTTP 200 OK)

### JavaScript Example
```javascript
const xhr = new XMLHttpRequest();

// Track upload progress
xhr.upload.onprogress = (e) => {
  if (e.lengthComputable) {
    const percent = (e.loaded / e.total) * 100;
    console.log(`Upload progress: ${percent}%`);
  }
};

xhr.onload = () => {
  if (xhr.status === 200) {
    console.log('Upload complete!');
  }
};

xhr.open('PUT', presignedUrl);
xhr.setRequestHeader('Content-Type', file.type);
xhr.send(file);
```

---

## Step 3: Create Product

Create a product with the uploaded S3 file keys.

### Endpoint
```
POST /products/dashboard/products/
```

### Headers
```
Content-Type: application/json
Authorization: Bearer {jwt_token}
```

### Request Body
```json
{
  "name": "Advanced Physics Book",
  "price": 99.99,
  "description": "A comprehensive physics guide",
  "category": 1,
  "subject": 1,
  "pdf_file": "pdfs/a1b2c3d4-5678-90ab-cdef.pdf",
  "base_image": "products/e5f6g7h8-1234-56cd-efgh.jpg",
  "page_count": 200,
  "file_size_mb": 25.5
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Product name |
| `price` | number | No | Product price |
| `description` | string | No | Product description |
| `category` | integer | No | Category ID |
| `subject` | integer | No | Subject ID |
| `sub_category` | integer | No | Sub-category ID |
| `teacher` | integer | No | Teacher ID |
| `year` | string | No | Year value |
| `pdf_file` | string | No | S3 object key from Step 1 (for PDF) |
| `base_image` | string | No | S3 object key from Step 1 (for cover image) |
| `page_count` | integer | No | Number of pages |
| `file_size_mb` | number | No | File size in MB |
| `language` | string | No | Language code |
| `is_available` | boolean | No | Availability status |

### Response (Success - 201)
```json
{
  "id": 5,
  "product_number": "PRD-00005",
  "name": "Advanced Physics Book",
  "price": "99.99",
  "description": "A comprehensive physics guide",
  "category": 1,
  "category_id": 1,
  "category_name": "Science",
  "subject": 1,
  "subject_id": 1,
  "subject_name": "Physics",
  "pdf_file": "https://your-cdn-domain.com/pdfs/a1b2c3d4-5678-90ab-cdef.pdf",
  "base_image": "https://your-cdn-domain.com/products/e5f6g7h8-1234-56cd-efgh.jpg",
  "page_count": 200,
  "file_size_mb": "25.50",
  "date_added": "2025-12-10T10:30:00Z",
  "images": [],
  "descriptions": []
}
```

### Response (Error - 400)
```json
{
  "name": ["This field is required."],
  "category": ["Invalid pk \"99\" - object does not exist."]
}
```

---

## Step 4: Upload Product Images (Optional)

Add additional images to an existing product.

### 4a. Get Presigned URLs for Images

Repeat **Step 1** for each image with `file_category: "image"`.

```json
{
  "file_name": "product-image-1.jpg",
  "file_type": "image/jpeg",
  "file_category": "image"
}
```

### 4b. Upload Images to S3

Repeat **Step 2** for each image.

### 4c. Create Product Images in Database

### Endpoint
```
POST /products/dashboard/product-images/bulk-upload-s3/
```

### Headers
```
Content-Type: application/json
Authorization: Bearer {jwt_token}
```

### Request Body
```json
{
  "product": 5,
  "images": [
    { "object_key": "products/img1-uuid.jpg" },
    { "object_key": "products/img2-uuid.png" },
    { "object_key": "products/img3-uuid.webp" }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product` | integer | Yes | Product ID from Step 3 |
| `images` | array | Yes | Array of image objects |
| `images[].object_key` | string | Yes | S3 object key for each image |

### Response (Success - 201)
```json
[
  {
    "id": 10,
    "product": 5,
    "image": "https://your-cdn-domain.com/products/img1-uuid.jpg"
  },
  {
    "id": 11,
    "product": 5,
    "image": "https://your-cdn-domain.com/products/img2-uuid.png"
  },
  {
    "id": 12,
    "product": 5,
    "image": "https://your-cdn-domain.com/products/img3-uuid.webp"
  }
]
```

### Response (Error - 400)
```json
{
  "product": ["Invalid pk \"999\" - object does not exist."],
  "images": ["Image at index 0 is missing 'object_key'"]
}
```

---

## Common MIME Types Reference

| Extension | MIME Type |
|-----------|-----------|
| `.pdf` | `application/pdf` |
| `.jpg`, `.jpeg`, `.jfif` | `image/jpeg` |
| `.png` | `image/png` |
| `.gif` | `image/gif` |
| `.webp` | `image/webp` |
| `.svg` | `image/svg+xml` |
| `.bmp` | `image/bmp` |

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCT CREATION FLOW                        │
└─────────────────────────────────────────────────────────────────┘

1. PDF Upload
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Frontend │───▶│  Django  │───▶│ Get URL  │
   │          │    │  API     │    │ Response │
   └──────────┘    └──────────┘    └──────────┘
        │                               │
        │         presigned_url         │
        ◀───────────────────────────────┘
        │
        │    PUT file to S3
        ▼
   ┌──────────┐
   │   S3/R2  │  ✓ PDF uploaded
   └──────────┘

2. Cover Image Upload (same process)
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Frontend │───▶│  Django  │───▶│ Get URL  │
   └──────────┘    └──────────┘    └──────────┘
        │                               │
        ◀───────────────────────────────┘
        │
        ▼
   ┌──────────┐
   │   S3/R2  │  ✓ Image uploaded
   └──────────┘

3. Create Product
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Frontend │───▶│  Django  │───▶│ Database │
   │ (S3 keys)│    │  API     │    │  Create  │
   └──────────┘    └──────────┘    └──────────┘
                                        │
                   product_id           │
        ◀───────────────────────────────┘

4. Additional Images (optional)
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Frontend │───▶│   S3/R2  │───▶│  Django  │
   │ (upload) │    │ (images) │    │  (bulk)  │
   └──────────┘    └──────────┘    └──────────┘
```

---

## Error Handling

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Success | Continue to next step |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Check request body for errors |
| 401 | Unauthorized | Refresh JWT token |
| 403 | Forbidden | User lacks permission |
| 404 | Not Found | Check endpoint URL |
| 500 | Server Error | Contact backend team |

---

## Notes

1. **Presigned URLs expire** after 1 hour. Generate new ones if upload takes longer.
2. **Large files** (50MB+) upload efficiently with progress tracking using XHR.
3. **S3 object keys** returned in Step 1 must be used exactly as-is in Steps 3 & 4.
4. **Authentication** is required for product creation and image upload endpoints.
