from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    CurrentUserView,
    ProfileView,
    verify_email_otp,
    resend_email_otp,
    list_subscription_plans,
    subscribe,
    create_order,
    verify_payment,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('verify-email/', verify_email_otp, name='verify_email'),
    path('resend-email-otp/', resend_email_otp, name='resend_email_otp'),
    path('plans/', list_subscription_plans, name='subscription_plans'),
    path('subscription/subscribe/', subscribe, name='subscribe'),
    path('subscription/create-order/', create_order, name='create_order'),
    path('subscription/verify-payment/', verify_payment, name='verify_payment'),
]
