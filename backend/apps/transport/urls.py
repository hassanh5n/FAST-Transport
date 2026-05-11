from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import StudentSignupView, CurrentUserView
from .views import students_list, get_challan, pay_challan, verify_fee, list_fee_verifications
from .views import student_bus_tracking, live_bus_location
from .views import create_payment_intent, confirm_stripe_payment, verify_payment_otp
from .views import download_transport_card
from .views import forgot_password, reset_password 

router = DefaultRouter()

# Existing ViewSets
router.register(r'students', StudentProfileViewSet)
router.register(r'semesters', SemesterViewSet)
router.register(r'routes', RouteViewSet)
router.register(r'stops', StopViewSet)
router.register(r'routestops', RouteStopViewSet)
router.register(r'buses', BusViewSet)
router.register(r'drivers', DriverViewSet)
router.register(r'route-assignments', RouteAssignmentViewSet)
router.register(r'semester-registrations', SemesterRegistrationViewSet)
router.register(r'seat-allocations', SeatAllocationViewSet)
router.register(r'waitlist', WaitlistViewSet)
router.register(r'fee-verifications', FeeVerificationViewSet)
router.register(r'complaints', ComplaintViewSet)
router.register(r'route-change-requests', RouteChangeRequestViewSet, basename='route-change-request')
router.register(r'maintenance-schedules', MaintenanceScheduleViewSet)
router.register(r'notifications', NotificationViewSet)
router.register(r"transport-registrations", TransportRegistrationViewSet)

urlpatterns = [
    # Explicit paths FIRST
    path('signup/', StudentSignupView.as_view(), name='student-signup'),
    path('user/', CurrentUserView.as_view(), name='current-user'),
    path('verify-otp/', verify_otp, name='verify-otp'),
    path('resend-otp/', resend_otp, name='resend-otp'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("students-list/", students_list),
    path('transport-registrations/<int:pk>/challan/', get_challan),
    path("transport-registrations/<int:pk>/challan/pay/", pay_challan),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("fee-verifications/list/", list_fee_verifications),
    path("fee-verifications/<int:pk>/verify/", verify_fee),
    path('student/bus-tracking/', student_bus_tracking, name='student-bus-tracking'),
    path("student/live-location/", live_bus_location, name="live-bus-location"),
    path('transport-registrations/<int:pk>/create-payment-intent/', create_payment_intent, name='create-payment-intent'),
    path('transport-registrations/<int:pk>/confirm-stripe-payment/', confirm_stripe_payment, name='confirm-stripe-payment'),
    path('transport-registrations/<int:pk>/verify-payment-otp/', verify_payment_otp, name='verify-payment-otp'),
    path("download-transport-card/", download_transport_card, name="download-transport-card"),
    path('forgot-password/', forgot_password, name='forgot-password'),
    path('reset-password/', reset_password, name='reset-password'),
] + router.urls  # Router LAST