from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import StudentSignupView, CurrentUserView
from .views import students_list, get_challan, pay_challan, verify_fee, list_fee_verifications
from .views import student_bus_tracking, live_bus_location
from .views import create_payment_intent, confirm_stripe_payment, verify_payment_otp
from .views import download_transport_card
from .views import BusLocationPingCreateView, IncidentViewSet, approved_incidents
from .views import eligible_route_stops
from .views import resolve_map_location, preview_route_geometry
from .views import crime_risk_zones
from .admin_views import (
    AdminRoleViewSet, AdminUserViewSet, LoggedTokenObtainPairView,
    activity_logs, modules_meta,
)
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
router.register(r"incidents", IncidentViewSet, basename="incident")

# Super admin: admin accounts & roles
router.register(r"admin-management/roles", AdminRoleViewSet, basename="admin-role")
router.register(r"admin-management/admins", AdminUserViewSet, basename="admin-user")

urlpatterns = [
    # Explicit paths FIRST
    path('signup/', StudentSignupView.as_view(), name='student-signup'),
    path('user/', CurrentUserView.as_view(), name='current-user'),
    path('verify-otp/', verify_otp, name='verify-otp'),
    path('resend-otp/', resend_otp, name='resend-otp'),
    path('forgot-password/', forgot_password, name='forgot-password'),
    path('reset-password/', reset_password, name='reset-password'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("students-list/", students_list),
    path('transport-registrations/<int:pk>/challan/', get_challan),
    path("transport-registrations/<int:pk>/challan/pay/", pay_challan),
    path('login/', LoggedTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("fee-verifications/list/", list_fee_verifications),
    path("fee-verifications/<int:pk>/verify/", verify_fee),
    path('student/bus-tracking/', student_bus_tracking, name='student-bus-tracking'),
    path("student/live-location/", live_bus_location, name="live-bus-location"),
    path('transport-registrations/<int:pk>/create-payment-intent/', create_payment_intent, name='create-payment-intent'),
    path('transport-registrations/<int:pk>/confirm-stripe-payment/', confirm_stripe_payment, name='confirm-stripe-payment'),
    path('transport-registrations/<int:pk>/verify-payment-otp/', verify_payment_otp, name='verify-payment-otp'),
    path("download-transport-card/", download_transport_card, name="download-transport-card"),
    path("bus-location/ping/", BusLocationPingCreateView.as_view(), name="bus-location-ping"),
    path("incidents/approved/", approved_incidents, name="approved-incidents"),
    path("registration/eligible-route-stops/", eligible_route_stops, name="eligible-route-stops"),
    path("admin/maps/location/", resolve_map_location, name="resolve-map-location"),
    path("admin/maps/route-preview/", preview_route_geometry, name="preview-route-geometry"),
    path("crime-risk/zones/", crime_risk_zones, name="crime-risk-zones"),
    path("admin-management/modules/", modules_meta, name="admin-modules"),
    path("admin-management/activity-logs/", activity_logs, name="admin-activity-logs"),
    path("driver/overview/", driver_overview, name="driver-overview"),
    path("driver/location/", driver_location, name="driver-location"),
] + router.urls  # Router LAST
