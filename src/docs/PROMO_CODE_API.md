# Promo Code API (v2)

Each promo code is **single-use**. It can be either **book-specific** (tied to one book) or **general** (valid for any book).  
The admin generates codes in bulk under a shared **title** (batch label); the student redeems one code per booking.  
All URLs are prefixed with `/products/`. Authentication is **JWT Bearer token** on every request.

---

## Overview

| Endpoint | Method | Access | Description |
|---|---|---|---|
| `/products/dashboard/promo-codes/` | GET | Admin | List all promo codes with filters |
| `/products/dashboard/promo-codes/bulk-create/` | POST | Admin | Bulk-generate codes for one book |
| `/products/dashboard/promo-codes/book-stats/` | GET | Admin | Per-book usage summary |
| `/products/dashboard/promo-codes/<id>/` | GET | Admin | Retrieve a single promo code |
| `/products/dashboard/promo-codes/<id>/` | PATCH | Admin | Partially update a promo code |
| `/products/dashboard/promo-codes/<id>/` | PUT | Admin | Fully update a promo code |
| `/products/dashboard/promo-codes/<id>/` | DELETE | Admin | Delete a promo code |
| `/products/promo-codes/redeem/` | POST | Student | Redeem a code to get a book |

---

## 1. List Promo Codes

**`GET /products/dashboard/promo-codes/`**

Returns a paginated list of all promo codes.

### Query Parameters (filters)

| Parameter | Type | Description |
|---|---|---|
| `code` | string | Partial match on code (case-insensitive) |
| `title` | string | Partial match on batch title (case-insensitive) |
| `book_id` | integer | Filter codes for a specific book ID |
| `book_name` | string | Partial match on book name |
| `is_general` | boolean | `true` = general codes (no book), `false` = book-specific codes |
| `is_active` | boolean | `true` / `false` |
| `is_used` | boolean | `true` = redeemed, `false` = still available |
| `is_valid` | boolean | Fully usable right now (active + unused + within date window) |
| `created_by` | integer | Admin user ID who created the codes |
| `used_by` | integer | Student user ID who redeemed the code |
| `start_date` | date (`YYYY-MM-DD`) | Created on or after |
| `end_date` | date (`YYYY-MM-DD`) | Created on or before |
| `used_after` | datetime | `used_at` >= this datetime |
| `used_before` | datetime | `used_at` <= this datetime |
| `search` | string | Full-text search on `code`, `title`, and `book__name` |
| `ordering` | string | Sort by `created_at`, `valid_from`, `valid_until`, `code`, `used_at` (prefix `-` for desc) |

### Response `200 OK`

```json
{
  "count": 50,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "code": "4830291847",
      "title": "april-batch-physics",
      "book": {
        "id": 5,
        "product_number": "SB-5",
        "name": "Math Grade 10",
        "type": "book",
        "year": "first-secondary"
      },
      "is_active": true,
      "is_used": false,
      "is_valid": true,
      "is_general": false,
      "valid_from": null,
      "valid_until": null,
      "used_by": null,
      "used_by_name": null,
      "used_by_username": null,
      "used_at": null,
      "created_by": 1,
      "created_by_name": "Admin User",
      "created_at": "2026-04-05T10:00:00Z",
      "updated_at": "2026-04-05T10:00:00Z"
    }
  ]
}
```

---

## 2. Bulk Create Promo Codes

**`POST /products/dashboard/promo-codes/bulk-create/`**

Generates N single-use codes sharing the same batch `title`. Codes can be tied to one specific book or be **general** (valid for any book) by omitting `book_id`.

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | **Yes** | Batch label for this group of codes. Must be unique across all batches. |
| `number_of_codes` | integer (1–1000) | **Yes** | How many codes to generate |
| `book_id` | integer | No | The product ID of the book these codes grant. Omit (or send `null`) to create **general** codes valid for any book. |
| `is_active` | boolean | No (default: `true`) | Whether codes are immediately active |
| `valid_from` | datetime | No | Start of validity window (null = no restriction) |
| `valid_until` | datetime | No | End of validity window (null = no restriction) |

#### Example — Book-specific batch

```json
{
  "title": "april-batch-math",
  "book_id": 5,
  "number_of_codes": 30,
  "is_active": true,
  "valid_from": "2026-05-01T00:00:00Z",
  "valid_until": "2026-05-31T23:59:59Z"
}
```

#### Example — General batch (any book)

```json
{
  "title": "spring-general-2026",
  "number_of_codes": 50,
  "is_active": true
}
```

### Response `201 Created`

Returns the full list of newly created code objects (same shape as a single item from the list).

```json
[
  {
    "id": 10,
    "code": "7392018473",
    "title": "april-batch-math",
    "book": { "id": 5, "product_number": "SB-5", "name": "Math Grade 10", "type": "book", "year": "first-secondary" },
    "is_active": true,
    "is_used": false,
    "is_valid": true,
    "is_general": false,
    "valid_from": "2026-05-01T00:00:00Z",
    "valid_until": "2026-05-31T23:59:59Z",
    "used_by": null,
    "used_by_name": null,
    "used_by_username": null,
    "used_at": null,
    "created_by": 1,
    "created_by_name": "Admin User",
    "created_at": "2026-04-05T10:00:00Z",
    "updated_at": "2026-04-05T10:00:00Z"
  }
]
```

### Validations

| Rule | Error |
|---|---|
| `title` already used in a previous batch | `{"title": "A batch with this title already exists."}` |
| `number_of_codes` < 1 or > 1000 | `{"number_of_codes": "Ensure this value is greater than or equal to 1."}` |
| `book_id` provided but does not exist | `{"book_id": "Invalid pk ... - object does not exist."}` |

---

## 3. Per-Book Stats

**`GET /products/dashboard/promo-codes/book-stats/`**

Returns an aggregated summary per book that has at least one promo code.

### Response `200 OK`

```json
[
  {
    "id": 5,
    "product_number": "SB-5",
    "name": "Math Grade 10",
    "total_codes": 30,
    "used_codes": 12,
    "available_codes": 18
  }
]
```

- `total_codes` — all codes ever created for this book
- `used_codes` — codes that have been redeemed
- `available_codes` — codes that are currently valid (active + unused + within date window)

---

## 4. Retrieve Promo Code

**`GET /products/dashboard/promo-codes/<id>/`**

Returns a single promo code object (same shape as a list item).

### Response `404 Not Found`

```json
{ "detail": "No PromoCode matches the given query." }
```

---

## 5. Update Promo Code

**`PATCH /products/dashboard/promo-codes/<id>/`** — partial update  
**`PUT /products/dashboard/promo-codes/<id>/`** — full update

### Writable fields

| Field | Type | Notes |
|---|---|---|
| `title` | string | Rename the batch label for this code |
| `book_id` | integer \| null | Change which book the code is for; set to `null` to make it general |
| `is_active` | boolean | Enable / disable the code |
| `valid_from` | datetime \| null | Adjust validity start |
| `valid_until` | datetime \| null | Adjust validity end |

> `code`, `is_used`, `used_by`, `used_at`, `created_by`, `created_at`, `updated_at` are **read-only**.

#### Example — Deactivate a code

```json
{ "is_active": false }
```

### Response `200 OK` — full updated code object.

---

## 6. Delete Promo Code

**`DELETE /products/dashboard/promo-codes/<id>/`**

### Response `204 No Content`

```json
{ "detail": "تم حذف الكود 4830291847 بنجاح." }
```

---

## 7. Redeem a Promo Code (Student)

**`POST /products/promo-codes/redeem/`**

The student taps **"Join using a promo code"** on a book card and submits the code together with the book ID.

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | **Yes** | The 10-digit promo code |
| `product_id` | integer | **Yes** | The ID of the book the student is trying to access |

```json
{
  "code": "4830291847",
  "product_id": 5
}
```

### Success Response `200 OK`

```json
{
  "promo_code": "4830291847",
  "book": {
    "id": 5,
    "product_number": "SB-5",
    "name": "Math Grade 10",
    "type": "book",
    "year": "first-secondary"
  },
  "already_owned": false
}
```

- `already_owned: true` means the student already had this book before redeeming (the code is still consumed).

### Error Responses

| Scenario | HTTP | Body |
|---|---|---|
| Code does not exist | `400` | `{"code": "الكود غير موجود."}` |
| Code already used by someone | `400` | `{"code": "تم استخدام هذا الكود من قبل."}` |
| Code inactive / outside date window | `400` | `{"code": "الكود غير صالح أو منتهي الصلاحية."}` |
| Code is book-specific and does not match the requested book | `400` | `{"code": "هذا الكود غير مخصص لهذا الكتاب."}` |
| `product_id` not found | `400` | `{"product_id": "Invalid pk ... - object does not exist."}` |
| Unauthenticated | `401` | `{"detail": "Authentication credentials were not provided."}` |

### Redemption Logic

1. Look up the code (exact match on `code` field).
2. Reject if `is_used=True` — already consumed.
3. Reject if `is_active=False` or outside valid date window.
4. If the code is **book-specific** (`book` is set), reject if `code.book_id != product_id`. General codes (`book=null`) skip this check and are valid for any book.
5. `PurchasedBook.get_or_create(user, product)` with `purchase_method=promo_code`, `price_at_sale=0`.
6. Set `code.is_used=True`, `code.used_by=student`, `code.used_at=now`.
7. The code is permanently consumed — **no one** can use it again.

---

## Model Reference

### PromoCode

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto primary key |
| `code` | string(10) | Unique 10-digit numeric code (auto-generated) |
| `title` | string \| null | Batch label shared by all codes created together. Unique per batch. |
| `book` | FK → Product \| null | The book this code grants access to. `null` = general code. |
| `is_active` | boolean | Hard on/off switch (admin-controlled) |
| `is_used` | boolean | `true` after redemption — single-use enforcement |
| `valid_from` | datetime \| null | Start of validity window |
| `valid_until` | datetime \| null | End of validity window |
| `used_by` | FK → User \| null | Student who redeemed the code |
| `used_at` | datetime \| null | When the code was redeemed |
| `created_by` | FK → User \| null | Admin who generated it |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |
| `is_valid` _(computed)_ | boolean | `true` when: `is_active=True` **and** `is_used=False` **and** within date window |
| `is_general` _(computed)_ | boolean | `true` when `book` is null — code can be redeemed against any book |
