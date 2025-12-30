from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
app_name="accounts"

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('signin/', views.signin, name='signin'),
    # Dashboard (admin) signin endpoint
    path('dashboard/signin/', views.signin_dashboard, name='signin-dashboard'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password-reset/', views.request_password_reset, name='password_reset'),
    path('password-reset/confirm/', views.reset_password_confirm, name='password_reset_confirm'),
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
    
    # Student's own devices
    path('my-devices/', views.my_devices, name='my-devices'),
]


