from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import security_views
app_name="accounts"

urlpatterns = [
    # OTP-based Signup
    path('signup/', views.signup, name='signup'),
    path('signup/verify-otp/', views.verify_signup_otp, name='verify-signup-otp'),
    path('signup/resend-otp/', views.resend_signup_otp, name='resend-signup-otp'),
    
    # Authentication
    path('signin/', views.signin, name='signin'),
    # Dashboard (admin) signin endpoint
    path('dashboard/signin/', views.signin_dashboard, name='signin-dashboard'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password-reset/', views.request_password_reset, name='password_reset'),
    path('password-reset/confirm/', views.reset_password_confirm, name='password_reset_confirm'),
    path('password-reset/resend-otp/', views.resend_password_reset_otp, name='resend-password-reset-otp'),
    path('update-user-data/', views.UpdateUserData.as_view(), name='update-user-data'),
    path('get-user-data/', views.GetUserData.as_view(), name='get-user-data'),
    path('orders/', views.UserOrdersView.as_view(), name='user-orders'),
    path('delete-account/', views.DeleteAccountView.as_view(), name='delete-account'),
    path('change-password/', views.change_password, name='change_password'),
    #-----------------Admin--------------------------#
    path('dashboard/create-admin-user/', views.create_admin_user, name='create-admin-user'),
    path('dashboard/users/create/', views.UserCreateAPIView.as_view(), name='user-create'),
    path('dashboard/users/update/<str:username>/', views.UserUpdateAPIView.as_view(), name='user-update'),
    path('dashboard/users/delete/<int:pk>/', views.UserDeleteAPIView.as_view(), name='user-delete'),
    # User profile image 
    path('dashboard/profile-images/', views.UserProfileImageListCreateView.as_view(), name='profile-image-list'),
    path('dashboard/profile-images/<int:pk>/', views.UserProfileImageRetrieveUpdateDestroyView.as_view(), name='profile-image-detail'),
    # user analysis
    # Dashboard user lists: admins and non-admin users
    path('dashboard/admins/', views.AdminsListView.as_view(), name='admin-list'),
    path('dashboard/users/', views.UsersListView.as_view(), name='dashboard-users-list'),
    path('dashboard/users/<int:pk>/', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    
    # Device Management (Admin)
    path('dashboard/students/devices/', views.StudentDeviceListView.as_view(), name='student-device-list'),
    path('dashboard/students/<int:pk>/devices/', views.StudentDeviceDetailView.as_view(), name='student-device-detail'),
    path('dashboard/students/<int:pk>/max-devices/', views.update_student_max_devices, name='update-student-max-devices'),
    path('dashboard/students/<int:pk>/devices/<int:device_id>/remove/', views.remove_student_device, name='remove-student-device'),
    path('dashboard/students/<int:pk>/devices/remove-all/', views.remove_all_student_devices, name='remove-all-student-devices'),
    
    # Ban/Unban Management (Admin) - Admin-specific endpoints (Superuser only)
    path('dashboard/admins/<int:pk>/ban/', views.ban_admin, name='ban-admin'),
    path('dashboard/admins/<int:pk>/unban/', views.unban_admin, name='unban-admin'),
    
    # Ban/Unban Management (Admin) - Student-specific endpoints
    path('dashboard/students/<int:pk>/ban/', views.ban_student, name='ban-student'),
    path('dashboard/students/<int:pk>/unban/', views.unban_student, name='unban-student'),
    path('dashboard/students/<int:pk>/devices/<int:device_id>/ban/', views.ban_device, name='ban-device'),
    path('dashboard/students/<int:pk>/devices/<int:device_id>/unban/', views.unban_device, name='unban-device'),
    
    # Deleted User Archive (Admin)
    path('dashboard/deleted-users/', views.DeletedUserArchiveListView.as_view(), name='deleted-users-list'),
    path('dashboard/deleted-users/<int:pk>/', views.DeletedUserArchiveDetailView.as_view(), name='deleted-user-detail'),
    path('dashboard/deleted-users/restore/', views.RestoreUserView.as_view(), name='restore-user'),
    
    # Security Management (Dashboard/Admin)
    path('dashboard/security/blocks/', security_views.SecurityBlockListView.as_view(), name='security-blocks-list'),
    path('dashboard/security/blocks/<int:pk>/', security_views.SecurityBlockDetailView.as_view(), name='security-block-detail'),
    path('dashboard/security/blocks/<int:pk>/deactivate/', security_views.deactivate_block_view, name='security-block-deactivate'),
    path('dashboard/security/unblock/', security_views.manual_unblock_view, name='security-unblock'),
    path('dashboard/security/attempts/', security_views.AuthenticationAttemptListView.as_view(), name='security-attempts-list'),
    path('dashboard/security/attempts/<int:pk>/', security_views.AuthenticationAttemptDetailView.as_view(), name='security-attempt-detail'),
    path('dashboard/security/stats/', security_views.security_statistics_view, name='security-stats'),
    path('dashboard/security/phone/<str:phone_number>/history/', security_views.phone_security_history_view, name='phone-security-history'),
    
    # Student's own devices
    path('my-devices/', views.my_devices, name='my-devices'),
]


