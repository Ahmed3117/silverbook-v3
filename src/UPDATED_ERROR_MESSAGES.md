# Updated Endpoints Error Messages

This file lists endpoints/views whose manual error responses were changed to return HTTP 400 with a JSON body in the format:

{
  "error": "<Arabic message>"
}

All changes are implemented in the codebase under `src/`.

---

## `accounts/views.py`

- `signup` (POST `/signup/`) : serializer errors left intact (validation responses)
  - URL: `/accounts/signup/`
- `signin` (POST `/signin/`) : `{'error': 'بيانات الدخول غير صحيحة، من فضلك تحقق.'}`
  - URL: `/accounts/signin/`
- `signin` (device limit case) : `{'error': 'لقد تجاوزت العدد المسموح به من الأجهزة لتسجيل الدخول إلى حسابك .'}`
- `signin` (token exceptions) : `{'error': 'فشل إنشاء رمز المصادقة.'}`
- `signin_dashboard` (POST `/signin-dashboard/`) :
  - invalid credentials: `{'error': 'بيانات الدخول غير صحيحة، من فضلك تحقق.'}`
  - not staff/superuser: `{'error': 'غير مصرح بالدخول عبر هذا المسار.'}`
  - token exception: `{'error': 'فشل إنشاء رمز المصادقة.'}`
  - URL: `/accounts/dashboard/signin/`
- `request_password_reset` :
  - user not found: `{'error': 'المستخدم غير موجود'}`
  - failed SMS send: `{'error': 'فشل إرسال رمز التحقق عبر الرسائل القصيرة.'}`
  - generic exception: `{'error': 'حدث خطأ، يرجى المحاولة لاحقًا.'}`
  - URL: `/accounts/password-reset/`
- `reset_password_confirm` :
  - invalid otp/username: `{'error': 'رمز التحقق أو اسم المستخدم غير صحيح'}`
  - otp expired: `{'error': 'انتهت صلاحية رمز التحقق'}`
  - generic exception: `{'error': 'حدث خطأ، يرجى المحاولة لاحقًا.'}`
  - URL: `/accounts/password-reset/confirm/`
- `UpdateUserData` (PATCH `/user/`) : student username change blocked: `{'error': 'لا يمكن للطلاب تغيير اسم المستخدم'}`
  - URL: `/accounts/update-user-data/`
- `DeleteAccountView` (DELETE `/account/`) : admin-deletion blocked: `{'error': 'لا يمكن حذف حسابات المدير عبر هذا المسار.'}`
  - URL: `/accounts/delete-account/`
- `change_password` : old password incorrect: `{'error': 'كلمة المرور القديمة غير صحيحة'}`
  - URL: `/accounts/change-password/`
- `UserUpdateAPIView` / `UserDeleteAPIView` : user-not-found: `{'error': 'المستخدم غير موجود'}`
  - URLs:
    - Update: `/accounts/dashboard/users/update/<username>/`
    - Delete: `/accounts/dashboard/users/delete/<pk>/`
- `update_student_max_devices`, `remove_student_device`, `remove_all_student_devices`: student/device not found responses now: `{'error': 'الطالب غير موجود'}` / `{'error': 'الجهاز غير موجود لهذا الطالب'}`
  - URLs:
    - Update max devices: `/accounts/dashboard/students/<pk>/max-devices/`
    - Remove device: `/accounts/dashboard/students/<pk>/devices/<device_id>/remove/`
    - Remove all devices: `/accounts/dashboard/students/<pk>/devices/remove-all/`
  - `my_devices` URL: `/accounts/my-devices/`

## `products/views.py`

- `TeacherProductsView` (GET teacher products): teacher not found -> `{'error': 'المعلم غير موجود'}`
  - URL: `/products/teacher-profile/<teacher_id>/`
- `PurchasedBookPDFDownloadView` (GET `/products/my-books/<id>/download/`):
  - no PDF: `{'error': 'هذا الكتاب لا يحتوي على ملف PDF متاح.'}`
  - presigned URL generation failure: `{'error': 'فشل إنشاء رابط التحميل، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/my-books/<purchased_book_id>/download/`
- `RemovePillItemView` (DELETE `/pill/<pill_id>/item/<item_id>/`):
  - item not found: `{'error': 'العنصر غير موجود في هذه الفاتورة'}` (HTTP 400)
  - server error: `{'error': 'حدث خطأ في الخادم، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/pills/<pill_id>/items/<item_id>/remove/`
- `create_shakeout_invoice_view` :
  - already has invoice: `{'error': 'الفاتورة موجودة مسبقًا لهذه الفاتورة.'}`
  - failed to create invoice: `{'error': 'فشل إنشاء فاتورة الشيك آوت.'}`
  - pill not found / access denied: `{'error': 'الفاتورة غير موجودة أو لا تملك صلاحية الوصول لها'}`
  - generic exception: `{'error': 'حدث خطأ أثناء إنشاء الفاتورة، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/pills/<pill_id>/create-shakeout-invoice/` (note: this route is defined in `products/urls.py` and maps to `payment_views.create_shakeout_invoice_view`)
- `AddBooksToStudentView` (POST `/products/add-books-to-student/`) validations:
  - missing user_id: `{'error': 'حقل user_id مطلوب'}`
  - invalid product_ids: `{'error': 'حقل product_ids يجب أن يكون قائمة غير فارغة'}`
  - missing products: `{'error': 'المنتجات غير موجودة: [...]'}`
  - user not found: `{'error': 'المستخدم ذو المعرف <id> غير موجود'}`
  - generic exception: `{'error': 'حدث خطأ أثناء إضافة الكتب، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/dashboard/add-books-to-student/`
- `AdminPurchasedBookListCreateView` (admin create purchased books) validations/exceptions:
  - missing/invalid inputs now return Arabic `{'error': ...}` messages and HTTP 400
  - missing user/pill/pill_item now return Arabic messages (HTTP 400)
  - general exception: `{'error': 'حدث خطأ أثناء إنشاء السجلات، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/dashboard/purchased-books/`
- `GeneratePresignedUploadUrlView` (POST `/products/api/generate-presigned-url/`):
  - missing `file_name`: `{'error': 'حقل file_name مطلوب'}`
  - invalid `file_category`: `{'error': 'حقل file_category يجب أن يكون أحد القيم: pdf, image, uploads'}`
  - failed generation: `{'error': 'فشل إنشاء رابط التحميل'}` or generic: `{'error': 'حدث خطأ أثناء إنشاء رابط التحميل، يرجى المحاولة لاحقًا.'}`
  - URL: `/products/api/generate-presigned-url/`
- Subject/Teacher/other admin serializer error handlers: key changed from `message` to `error` when returning serializer-derived messages (still contains original text from serializer).
  - Subject list/create URL: `/products/dashboard/subjects/`
  - Subject detail (update) URL: `/products/dashboard/subjects/<pk>/`
  - Teacher admin URL: `/products/dashboard/teachers/` and `/products/dashboard/teachers/<pk>/`

---

If you want, I can:
- Translate serializer-derived messages into Arabic as well (requires mapping or automatic translation),
- Run `python manage.py check` and run tests to validate no syntax/runtime errors,
- Commit these changes and open a PR.

