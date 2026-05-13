from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Registration & OTP
    path('signup/',             views.UserRegistrationView.as_view({'post': 'create'}),      name='signup'),
    path('verify-otp/',         views.UserRegistrationView.as_view({'post': 'verify_otp'}),  name='verify_otp'),
    path('resend-otp/',         views.UserRegistrationView.as_view({'post': 'resend_otp'}),  name='resend_otp'),

    # Login / Logout
    path('login/',              views.UserLoginView.as_view(),                               name='login'),
    path('logout/',             views.logout,                                                name='logout'),

    # Profile
    path('profile/',            views.UserProfileView.as_view(),                             name='profile'),
    path('<int:pk>/update-profile/', views.UserProfileView.as_view(),                        name='update_profile'),

    # Password
    path('change-password/',           views.change_password,           name='change_password'),
    path('initiate-password-reset/',   views.initiate_password_reset,   name='initiate_password_reset'),
    path('reset-password/',            views.reset_password,            name='reset_password'),

    # Addresses
    path('addresses/',          views.AddressListView.as_view(),                             name='address_list'),
    path('addresses/<int:pk>/', views.AddressDetailView.as_view(),                           name='address_detail'),

    # Activity log
    path('activities/',         views.UserActivityListView.as_view(),                        name='activity_list'),
]
