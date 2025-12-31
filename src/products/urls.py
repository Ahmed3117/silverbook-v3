from django.urls import path

from products import payment_views
from products.shakeout_webhooks import shakeout_webhook
from products.easypay_webhooks import easypay_webhook
from . import views

app_name = 'products'

urlpatterns = [
    # Customer Endpoints
    path('subjects/', views.SubjectListView.as_view(), name='subject-list'),
    path('teachers/', views.TeacherListView.as_view(), name='teacher-list'),
    path('teachers/<int:id>/', views.TeacherDetailView.as_view(), name='teacher-detail'),
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<int:id>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('last-products/', views.Last10ProductsListView.as_view(), name='last-products'),
    path('special-products/active/', views.ActiveSpecialProductsView.as_view(), name='special-products'),
    path('best-products/active/', views.ActiveBestProductsView.as_view(), name='best-products'),
    path('combined-products/', views.CombinedProductsView.as_view(), name='combined-products'),
    path('special-best-products/', views.SpecialBestProductsView.as_view(), name='special-best-products'),
    path('teacher-profile/<int:teacher_id>/', views.TeacherProductsView.as_view(), name='teacher-products'),
    path('pills/init/', views.PillCreateView.as_view(), name='pill-create'),
    path('pills/<int:id>/apply-coupon/', views.PillCouponApplyView.as_view(), name='pill-coupon-apply'),
    path('pills/<int:id>/', views.PillDetailView.as_view(), name='pill-detail'),
    path('user-pills/', views.UserPillsView.as_view(), name='user-pills'),
    path('my-books/', views.PurchasedBookListView.as_view(), name='purchased-books'),
    path('my-books/<int:purchased_book_id>/download/', views.PurchasedBookPDFDownloadView.as_view(), name='purchased-book-download'),
    path('<str:product_number>/add-free/', views.AddFreeBookView.as_view(), name='add-free-book'),
    path('<str:product_number>/owned/', views.ProductOwnedCheckView.as_view(), name='book-owned-check'),
    path('discounts/active/', views.ProductsWithActiveDiscountAPIView.as_view(), name='products-with-discount'),
    path('loved-products/', views.LovedProductListCreateView.as_view(), name='loved-product-list-create'),
    path('loved-products/<int:product_id>/', views.LovedProductRetrieveDestroyView.as_view(), name='loved-product-detail'),
    path('products/new-arrivals/', views.NewArrivalsView.as_view(), name='new-arrivals'),
    path('products/best-sellers/', views.BestSellersView.as_view(), name='best-sellers'),
    path('products/frequently-bought-together/', views.FrequentlyBoughtTogetherView.as_view(), name='frequently-bought-together'),
    path('products/recommendations/', views.ProductRecommendationsView.as_view(), name='recommendations'),

    # Admin Endpoints
    path('dashboard/subjects/', views.SubjectListCreateView.as_view(), name='admin-subject-list-create'),
    path('dashboard/subjects/<int:pk>/', views.SubjectRetrieveUpdateDestroyView.as_view(), name='admin-subject-detail'),
    path('dashboard/subjects-simple/', views.SubjectSimpleListView.as_view(), name='admin-subject-simple-list'),
    path('dashboard/teachers/', views.TeacherListCreateView.as_view(), name='admin-teacher-list-create'),
    path('dashboard/teachers/<int:pk>/', views.TeacherRetrieveUpdateDestroyView.as_view(), name='admin-teacher-detail'),
    path('dashboard/teachers-simple/', views.TeacherSimpleListView.as_view(), name='admin-teacher-simple-list'),
    path('dashboard/products/', views.ProductListCreateView.as_view(), name='admin-product-list-create'),
    path('dashboard/products-breifed/', views.ProductListBreifedView.as_view(), name='admin-product-list-breifed'),
    path('dashboard/products-simple/', views.ProductSimpleListView.as_view(), name='admin-product-simple-list'),
    path('dashboard/products/<int:pk>/', views.ProductRetrieveUpdateDestroyView.as_view(), name='admin-product-detail'),
    path('api/generate-presigned-url/', views.GeneratePresignedUploadUrlView.as_view(), name='generate-presigned-url'),
    path('dashboard/product-images/', views.ProductImageListCreateView.as_view(), name='admin-product-image-list-create'),
    path('dashboard/product-images/bulk-upload/', views.ProductImageBulkCreateView.as_view(), name='admin-product-image-bulk-create'),
    path('dashboard/product-images/bulk-upload-s3/', views.ProductImageBulkS3CreateView.as_view(), name='admin-product-image-bulk-s3-create'),
    path('dashboard/product-images/<int:pk>/', views.ProductImageDetailView.as_view(), name='admin-product-image-detail'),
    path('dashboard/special-products/', views.SpecialProductListCreateView.as_view(), name='admin-special-product-list-create'),
    path('dashboard/special-products/<int:pk>/', views.SpecialProductRetrieveUpdateDestroyView.as_view(), name='admin-special-product-detail'),
    path('dashboard/best-products/', views.BestProductListCreateView.as_view(), name='admin-best-product-list-create'),
    path('dashboard/best-products/<int:pk>/', views.BestProductRetrieveUpdateDestroyView.as_view(), name='admin-best-product-detail'),

    # PillItems endpoints
    path('dashboard/pill-items/', views.PillItemListCreateView.as_view(), name='pillitem-list'),
    path('dashboard/pill-items/<int:pk>/', views.PillItemRetrieveUpdateDestroyView.as_view(), name='pillitem-detail'),
    path('pills/<int:pill_id>/items/<int:item_id>/remove/', views.RemovePillItemView.as_view(), name='remove-pill-item'),
    
    # LovedItems endpoints
    path('dashboard/loved-items/', views.AdminLovedProductListCreateView.as_view(), name='lovedproduct-list'),
    path('dashboard/loved-items/<int:pk>/', views.AdminLovedProductRetrieveDestroyView.as_view(), name='lovedproduct-detail'),
    
    path('dashboard/pills/', views.PillListCreateView.as_view(), name='admin-pill-list-create'),
    path('dashboard/pills/<int:pk>/', views.PillRetrieveUpdateDestroyView.as_view(), name='admin-pill-detail'),
    path('dashboard/pills/<int:pk>/items/', views.PillItemsListView.as_view(), name='admin-pill-items'),
    path('dashboard/discounts/', views.DiscountListCreateView.as_view(), name='admin-discount-list-create'),
    path('dashboard/discounts/<int:pk>/', views.DiscountRetrieveUpdateDestroyView.as_view(), name='admin-discount-detail'),
    path('dashboard/coupons/', views.CouponListCreateView.as_view(), name='admin-coupon-list-create'),
    path('dashboard/coupons/bulk/', views.BulkCouponCreateView.as_view(), name='admin-coupon-bulk-create'),
    path('dashboard/coupons/<int:pk>/', views.CouponRetrieveUpdateDestroyView.as_view(), name='admin-coupon-detail'),
    path('dashboard/add-books-to-student/', views.AddBooksToStudentView.as_view(), name='add-books-to-student'),
    path('dashboard/purchased-books/', views.AdminPurchasedBookListCreateView.as_view(), name='admin-purchased-books-list-create'),
    path('dashboard/purchased-books/<int:pk>/', views.AdminPurchasedBookRetrieveUpdateDestroyView.as_view(), name='admin-purchased-books-detail'),
    path('dashboard/purchased-books/by-user/<int:user_id>/', views.AdminUserPurchasedBooksView.as_view(), name='admin-user-purchased-books'),

    # Package Product Endpoints
    path('my-books/package/<int:product_id>/details/', views.MyPackageDetailsView.as_view(), name='my-package-details'),
    path('products/<int:product_id>/related-products/', views.ProductRelatedProductsView.as_view(), name='product-related-products'),
    path('dashboard/packages/add-books/', views.AddBooksToPackageView.as_view(), name='add-books-to-package'),
    path('dashboard/packages/package-products/', views.PackageProductListView.as_view(), name='package-products-list'),
    path('dashboard/packages/package-products/<int:pk>/', views.RemoveBookFromPackageView.as_view(), name='package-product-detail'),
    path('dashboard/packages/packages/<int:package_id>/books/', views.PackageBooksListView.as_view(), name='package-books-list'),
    path('dashboard/packages/products/<int:product_id>/remove-all-relationships/', views.RemoveAllProductRelationshipsView.as_view(), name='remove-all-product-relationships'),

    # Payment Endpoints (Fawaterak, Shakeout, EasyPay)
    path('api/payment/create/<int:pill_id>/', payment_views.create_payment_view, name='api_create_payment'),
    path('api/payment/webhook/fawaterak/', payment_views.fawaterak_webhook, name='api_fawaterak_webhook'),
    path('api/payment/success/<str:pill_number>/', payment_views.payment_success_view, name='api_payment_success'),
    path('api/payment/failed/<str:pill_number>/', payment_views.payment_failed_view, name='api_payment_failed'),
    path('api/payment/pending/<str:pill_number>/', payment_views.payment_pending_view, name='api_payment_pending'),
    path('api/payment/status/<int:pill_id>/', payment_views.check_payment_status_view, name='api_check_payment_status'),

    # FALLBACK: Handle Fawaterak's incorrect redirect URLs with /products prefix
    path('products/api/payment/success/<str:pill_number>/', payment_views.payment_success_view, name='fallback_payment_success'),
    path('products/api/payment/failed/<str:pill_number>/', payment_views.payment_failed_view, name='fallback_payment_failed'),
    path('products/api/payment/pending/<str:pill_number>/', payment_views.payment_pending_view, name='fallback_payment_pending'),

    # Webhooks
    path('api/webhook/shakeout/', shakeout_webhook, name='shakeout_webhook'),
    
    # Invoice Creation Endpoints
    path('pills/<int:pill_id>/create-shakeout-invoice/', payment_views.create_shakeout_invoice_view, name='create_shakeout_invoice'),
    path('pills/<int:pill_id>/create-easypay-invoice/', payment_views.create_easypay_invoice_view, name='create_easypay_invoice'),
    path('pills/<int:pill_id>/check-easypay-status/', payment_views.check_easypay_invoice_status_view, name='check_easypay_status'),
    path('pills/<int:pill_id>/create-payment-invoice/', payment_views.create_payment_invoice_view, name='create_payment_invoice'),
]

