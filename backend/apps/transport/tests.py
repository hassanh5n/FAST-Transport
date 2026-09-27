from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.test import APIClient
from unittest.mock import Mock, patch
import requests as req_lib

from .permissions import IsAdmin, IsAdminOrReadOnly, IsStudent, IsStudentCreateOnly
from .serializers import RouteAssignmentSerializer
from .seatallocation import (
	_get_next_available_seat_number,
	allocate_seat_for_student,
	allocate_seat_on_assignment,
)
from .models import (
	Bus,
	Driver,
	FeeVerification,
	Route,
	RouteAssignment,
	RouteStop,
	SeatAllocation,
	Semester,
	SemesterRegistration,
	Stop,
	StudentProfile,
	TransportRegistration,
	Waitlist,
)


class TransportAllocationFlowTests(TestCase):
	def setUp(self):
		self.client = APIClient()

		self.admin = User.objects.create_user(
			username="admin",
			password="adminpass",
			is_staff=True,
		)

		self.semester = Semester.objects.create(
			name="Spring",
			year=2026,
			term="S",
			is_active=True,
			registration_open=True,
		)
		self.route = Route.objects.create(name="Route A", is_active=True)
		self.stop = Stop.objects.create(name="Stop A")
		RouteStop.objects.create(route=self.route, stop=self.stop, stop_order=1)

		self.bus = Bus.objects.create(bus_number="BUS-1", capacity=1, is_active=True)
		self.driver = Driver.objects.create(name="Driver 1", is_available=True)
		self.assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)

		self.bus_2 = Bus.objects.create(bus_number="BUS-2", capacity=2, is_active=True)
		self.driver_2 = Driver.objects.create(name="Driver 2", is_available=True)
		self.assignment_2 = RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus_2,
			driver=self.driver_2,
			semester=self.semester,
			is_active=True,
		)

	def _create_student_with_profile(self, suffix):
		user = User.objects.create_user(username=f"student_{suffix}", password="pass1234")
		profile = StudentProfile.objects.create(
			user=user,
			roll_number=f"22F-{suffix}",
			department="CS",
			batch="22",
			phone="000",
			address="Address",
		)
		return user, profile

	def _create_transport_registration(self, user):
		self.client.force_authenticate(user=user)
		response = self.client.post(
			"/api/transport-registrations/",
			{"stop_id": self.stop.id, "semester_id": self.semester.id},
			format="json",
		)
		self.assertEqual(response.status_code, 201)
		return response

	def _verify_fee_as_admin(self, profile):
		fee = FeeVerification.objects.create(
			student=profile,
			semester=self.semester,
			amount=45000,
			challan_number=f"CHN-{profile.roll_number}",
			is_verified=False,
		)
		self.client.force_authenticate(user=self.admin)
		response = self.client.post(f"/api/fee-verifications/{fee.id}/verify/")
		self.assertEqual(response.status_code, 200)
		return fee

	def test_route_is_auto_assigned_on_transport_registration(self):
		student_user, profile = self._create_student_with_profile("001")
		self._create_transport_registration(student_user)

		registration = TransportRegistration.objects.get(student=profile, semester=self.semester)
		self.assertEqual(registration.route_id, self.route.id)

		semester_registration = SemesterRegistration.objects.get(
			student=profile,
			semester=self.semester,
		)
		self.assertEqual(semester_registration.route_id, self.route.id)
		self.assertEqual(semester_registration.stop_id, self.stop.id)

	def test_seat_is_auto_allocated_after_fee_verification(self):
		student_user, profile = self._create_student_with_profile("002")
		self._create_transport_registration(student_user)
		self._verify_fee_as_admin(profile)

		seat = SeatAllocation.objects.get(registration__student=profile, registration__semester=self.semester)
		self.assertEqual(seat.route_assignment_id, self.assignment.id)
		self.assertEqual(seat.seat_number, 1)

		registration = TransportRegistration.objects.get(student=profile, semester=self.semester)
		self.assertEqual(registration.status, "Approved")

	def test_waitlist_is_auto_created_when_bus_is_full(self):
		first_user, first_profile = self._create_student_with_profile("003")
		self._create_transport_registration(first_user)
		self._verify_fee_as_admin(first_profile)

		second_user, second_profile = self._create_student_with_profile("004")
		self._create_transport_registration(second_user)
		self._verify_fee_as_admin(second_profile)

		seat_count = SeatAllocation.objects.filter(
			registration__semester=self.semester,
			route_assignment=self.assignment,
		).count()
		self.assertEqual(seat_count, 1)

		waitlist = Waitlist.objects.get(registration__student=second_profile, registration__semester=self.semester)
		self.assertEqual(waitlist.position, 1)

	def test_admin_can_reassign_existing_seat(self):
		student_user, profile = self._create_student_with_profile("005")
		self._create_transport_registration(student_user)
		self._verify_fee_as_admin(profile)

		registration = SemesterRegistration.objects.get(student=profile, semester=self.semester)

		self.client.force_authenticate(user=self.admin)
		response = self.client.post(
			"/api/seat-allocations/reassign/",
			{
				"registration_id": registration.id,
				"route_assignment_id": self.assignment_2.id,
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		seat = SeatAllocation.objects.get(registration=registration)
		self.assertEqual(seat.route_assignment_id, self.assignment_2.id)
		self.assertEqual(seat.seat_number, 1)

	def test_reassign_requires_verified_fee(self):
		_, profile = self._create_student_with_profile("006")
		registration = SemesterRegistration.objects.create(
			student=profile,
			semester=self.semester,
			route=self.route,
			stop=self.stop,
			status="Confirmed",
		)
		SeatAllocation.objects.create(
			registration=registration,
			route_assignment=self.assignment,
			seat_number=1,
		)

		self.client.force_authenticate(user=self.admin)
		response = self.client.post(
			"/api/seat-allocations/reassign/",
			{
				"registration_id": registration.id,
				"route_assignment_id": self.assignment_2.id,
			},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("not verified", response.data.get("detail", ""))


class PermissionRulesTests(TestCase):
	def setUp(self):
		self.factory = APIRequestFactory()
		self.student = User.objects.create_user(username="student_perm", password="pass1234")
		self.admin = User.objects.create_user(
			username="admin_perm",
			password="adminpass",
			is_staff=True,
		)

	def _req(self, method, user):
		request = getattr(self.factory, method)("/api/test/")
		request.user = user
		return request

	def test_is_admin_allows_only_authenticated_staff(self):
		perm = IsAdmin()

		self.assertFalse(perm.has_permission(self._req("get", AnonymousUser()), None))
		self.assertFalse(perm.has_permission(self._req("get", self.student), None))
		self.assertTrue(perm.has_permission(self._req("get", self.admin), None))

	def test_is_student_allows_any_authenticated_user(self):
		perm = IsStudent()

		self.assertFalse(perm.has_permission(self._req("get", AnonymousUser()), None))
		self.assertTrue(perm.has_permission(self._req("get", self.student), None))
		self.assertTrue(perm.has_permission(self._req("get", self.admin), None))

	def test_is_admin_or_read_only_permission_matrix(self):
		perm = IsAdminOrReadOnly()

		self.assertFalse(perm.has_permission(self._req("get", AnonymousUser()), None))
		self.assertFalse(perm.has_permission(self._req("post", AnonymousUser()), None))

		self.assertTrue(perm.has_permission(self._req("get", self.student), None))
		self.assertFalse(perm.has_permission(self._req("post", self.student), None))
		self.assertFalse(perm.has_permission(self._req("patch", self.student), None))

		self.assertTrue(perm.has_permission(self._req("get", self.admin), None))
		self.assertTrue(perm.has_permission(self._req("post", self.admin), None))
		self.assertTrue(perm.has_permission(self._req("patch", self.admin), None))

	def test_is_student_create_only_permission_matrix(self):
		perm = IsStudentCreateOnly()

		self.assertFalse(perm.has_permission(self._req("get", AnonymousUser()), None))
		self.assertFalse(perm.has_permission(self._req("post", AnonymousUser()), None))

		self.assertTrue(perm.has_permission(self._req("get", self.student), None))
		self.assertTrue(perm.has_permission(self._req("post", self.student), None))
		self.assertFalse(perm.has_permission(self._req("patch", self.student), None))

		self.assertTrue(perm.has_permission(self._req("get", self.admin), None))
		self.assertTrue(perm.has_permission(self._req("post", self.admin), None))
		self.assertTrue(perm.has_permission(self._req("patch", self.admin), None))


class MapRouteApiTests(TestCase):
	def setUp(self):
		cache.clear()
		self.client = APIClient()
		self.admin = User.objects.create_user(username="map_admin", password="pass", is_staff=True)
		self.student = User.objects.create_user(username="map_student", password="pass")
		self.profile = StudentProfile.objects.create(
			user=self.student, roll_number="MAP-001", department="CS", batch="26", phone="0", address="Karachi"
		)
		self.semester = Semester.objects.create(name="Map Semester", year=2026, term="F", is_active=True, registration_open=True)
		self.route = Route.objects.create(name="Map Route")
		self.other_route = Route.objects.create(name="Other Map Route")
		self.stop = Stop.objects.create(name="Mapped Stop", latitude="24.921500", longitude="67.084700")
		self.other_stop = Stop.objects.create(name="Second Stop", latitude="24.931500", longitude="67.094700")
		self.route_stop = RouteStop.objects.create(route=self.route, stop=self.stop, stop_order=1)
		RouteStop.objects.create(route=self.route, stop=self.other_stop, stop_order=2)
		self.other_route_stop = RouteStop.objects.create(route=self.other_route, stop=self.stop, stop_order=1)
		RouteAssignment.objects.create(
			route=self.route, bus=Bus.objects.create(bus_number="MAP-1", capacity=10),
			driver=Driver.objects.create(name="Map Driver"), semester=self.semester
		)

	@patch("apps.transport.views.req_lib.get")
	def test_route_map_reroutes_missing_geometry(self, mock_get):
		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.student)
		response = self.client.get("/api/routes/map/")
		self.assertEqual(response.status_code, 200)
		route = next(item for item in response.data["routes"] if item["id"] == self.route.id)
		self.assertEqual(route["geometry"]["coordinates"], [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]])
		self.assertEqual(route["stops"][0]["route_stop_id"], self.route_stop.id)

	@patch("apps.transport.views.req_lib.get")
	def test_route_map_retries_a_saved_straight_line(self, mock_get):
		self.route.geometry = {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.0947, 24.9315]]}
		self.route.save(update_fields=["geometry"])
		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.student)
		response = self.client.get(f"/api/routes/{self.route.id}/map-detail/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["geometry"]["coordinates"], [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]])

	@patch("apps.transport.views.req_lib.get")
	def test_route_map_retries_a_rounded_straight_line(self, mock_get):
		self.route.geometry = {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.0897, 24.9265], [67.0947, 24.9315]]}
		self.route.save(update_fields=["geometry"])
		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.student)
		response = self.client.get(f"/api/routes/{self.route.id}/map-detail/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["geometry"]["coordinates"], [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]])

	@patch("apps.transport.views.req_lib.get")
	def test_route_preview_retries_after_a_provider_failure(self, mock_get):
		self.client.force_authenticate(user=self.admin)
		mock_get.side_effect = req_lib.RequestException
		fallback = self.client.post("/api/admin/maps/route-preview/", {"stop_ids": [self.stop.id, self.other_stop.id]}, format="json")
		self.assertEqual(fallback.data["source"], "fallback")

		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.side_effect = None
		mock_get.return_value = mock_response
		routed = self.client.post("/api/admin/maps/route-preview/", {"stop_ids": [self.stop.id, self.other_stop.id]}, format="json")
		self.assertEqual(routed.data["source"], "provider")
		self.assertEqual(mock_get.call_count, 2)

	@patch("apps.transport.views.req_lib.get")
	def test_eligible_route_stops_include_road_geometry(self, mock_get):
		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.student)
		response = self.client.get(f"/api/registration/eligible-route-stops/?semester={self.semester.id}")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["route_geometries"][self.route.id]["coordinates"], [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]])

	def test_registration_uses_explicit_route_stop_when_stop_is_shared(self):
		self.client.force_authenticate(user=self.student)
		response = self.client.post(
			"/api/transport-registrations/",
			{"semester_id": self.semester.id, "route_stop_id": self.other_route_stop.id},
			format="json",
		)
		self.assertEqual(response.status_code, 201, response.data)
		registration = TransportRegistration.objects.get(student=self.profile, semester=self.semester)
		self.assertEqual(registration.route_id, self.other_route.id)

	def test_admin_builder_replaces_ordered_stops_atomically(self):
		self.client.force_authenticate(user=self.admin)
		response = self.client.patch(
			f"/api/routes/{self.route.id}/builder/",
			{
				"stops": [
					{"stop_id": self.stop.id, "morning_eta": "06:30"},
					{"stop_id": self.other_stop.id, "morning_eta": "06:45"},
				],
				"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.0947, 24.9315]]},
			},
			format="json",
		)
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(list(RouteStop.objects.filter(route=self.route).values_list("stop_id", flat=True)), [self.stop.id, self.other_stop.id])

	@patch("apps.transport.views.req_lib.get")
	def test_admin_location_search_proxies_and_normalizes_results(self, mock_get):
		mock_response = Mock()
		mock_response.json.return_value = [{
			"lat": "24.9215", "lon": "67.0847", "display_name": "FAST NUCES, Karachi",
			"osm_type": "node", "osm_id": 123,
		}]
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.admin)
		response = self.client.post("/api/admin/maps/location/", {"action": "search", "query": "FAST NUCES"}, format="json")
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["results"][0]["label"], "FAST NUCES, Karachi")
		self.assertEqual(response.data["results"][0]["provider_place_id"], "node:123")

	@patch("apps.transport.views.req_lib.get")
	def test_admin_route_preview_returns_provider_geometry(self, mock_get):
		mock_response = Mock()
		mock_response.json.return_value = {"routes": [{"geometry": {"type": "LineString", "coordinates": [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]]}}]}
		mock_get.return_value = mock_response
		self.client.force_authenticate(user=self.admin)
		response = self.client.post("/api/admin/maps/route-preview/", {"stop_ids": [self.stop.id, self.other_stop.id]}, format="json")
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["geometry"]["coordinates"], [[67.0847, 24.9215], [67.09, 24.93], [67.0947, 24.9315]])


class RouteStopCleanupCommandTests(TestCase):
	def test_cleanup_route_stops_removes_duplicates_and_reindexes_order(self):
		route = Route.objects.create(name="Cleanup Route")
		stop_a = Stop.objects.create(name="Stop A", latitude="24.921500", longitude="67.084700")
		stop_b = Stop.objects.create(name="Stop B", latitude="24.931500", longitude="67.094700")
		with connection.cursor() as cursor:
			cursor.execute("ALTER TABLE transport_routestop DROP CONSTRAINT IF EXISTS unique_stop_per_route")
			cursor.execute("ALTER TABLE transport_routestop DROP CONSTRAINT IF EXISTS unique_stop_order_per_route")
			cursor.execute(
				"INSERT INTO transport_routestop (route_id, stop_id, stop_order, morning_eta, evening_eta) VALUES (%s, %s, %s, NULL, NULL), (%s, %s, %s, NULL, NULL), (%s, %s, %s, NULL, NULL), (%s, %s, %s, NULL, NULL)",
				(route.id, stop_a.id, 1, route.id, stop_a.id, 1, route.id, stop_b.id, 2, route.id, stop_b.id, 2)
			)

		call_command("cleanup_route_stops")

		self.assertEqual(route.routestop_set.count(), 2)
		self.assertEqual(list(route.routestop_set.values_list("stop_id", flat=True)), [stop_a.id, stop_b.id])
		self.assertEqual(list(route.routestop_set.order_by("stop_order").values_list("stop_order", flat=True)), [1, 2])


class SeatAllocationServiceTests(TestCase):
	def setUp(self):
		self.semester = Semester.objects.create(
			name="Fall",
			year=2026,
			term="F",
			is_active=True,
			registration_open=True,
		)
		self.other_semester = Semester.objects.create(
			name="Spring",
			year=2027,
			term="S",
			is_active=True,
			registration_open=True,
		)

		self.route = Route.objects.create(name="Route Core", is_active=True)
		self.other_route = Route.objects.create(name="Route Other", is_active=True)
		self.stop = Stop.objects.create(name="Main Stop")

		self.bus = Bus.objects.create(bus_number="BUS-CORE", capacity=4, is_active=True)
		self.driver = Driver.objects.create(name="Driver Core", is_available=True)
		self.assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)

	def _registration(self, suffix, route=None, semester=None):
		user = User.objects.create_user(username=f"seat_user_{suffix}", password="pass1234")
		profile = StudentProfile.objects.create(
			user=user,
			roll_number=f"22F-SEAT-{suffix}",
			department="CS",
			batch="22",
			phone="000",
			address="Address",
		)
		return SemesterRegistration.objects.create(
			student=profile,
			semester=semester or self.semester,
			route=route or self.route,
			stop=self.stop,
			status="Pending",
		)

	def test_next_available_seat_number_prefers_lowest_gap(self):
		reg1 = self._registration("001")
		reg2 = self._registration("002")

		SeatAllocation.objects.create(
			registration=reg1,
			route_assignment=self.assignment,
			seat_number=1,
		)
		SeatAllocation.objects.create(
			registration=reg2,
			route_assignment=self.assignment,
			seat_number=3,
		)

		self.assertEqual(_get_next_available_seat_number(self.assignment), 2)

	def test_allocate_seat_for_student_is_idempotent(self):
		registration = self._registration("003")

		first = allocate_seat_for_student(registration)
		second = allocate_seat_for_student(registration)

		self.assertEqual(first, "Seat Allocated")
		self.assertEqual(second, "Seat already allocated")
		self.assertEqual(SeatAllocation.objects.filter(registration=registration).count(), 1)

	def test_allocate_seat_for_student_returns_already_on_waitlist(self):
		registration = self._registration("004")
		Waitlist.objects.create(registration=registration, position=1)

		result = allocate_seat_for_student(registration)

		self.assertEqual(result, "Already on waitlist")
		self.assertEqual(SeatAllocation.objects.filter(registration=registration).count(), 0)
		self.assertEqual(Waitlist.objects.filter(registration=registration).count(), 1)

	def test_allocate_seat_on_assignment_rejects_route_or_semester_mismatch(self):
		registration = self._registration("005")
		mismatch_assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=Bus.objects.create(bus_number="BUS-MISMATCH", capacity=2, is_active=True),
			driver=Driver.objects.create(name="Driver Mismatch", is_available=True),
			semester=self.other_semester,
			is_active=True,
		)

		result = allocate_seat_on_assignment(registration, mismatch_assignment)

		self.assertEqual(result, "Assignment does not match student's route and semester")

	def test_allocate_seat_on_assignment_rejects_inactive_assignment(self):
		registration = self._registration("006")
		inactive_assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=Bus.objects.create(bus_number="BUS-INACTIVE-A", capacity=2, is_active=True),
			driver=Driver.objects.create(name="Driver Inactive A", is_available=True),
			semester=self.semester,
			is_active=False,
		)

		result = allocate_seat_on_assignment(registration, inactive_assignment)

		self.assertEqual(result, "Route assignment is inactive")

	def test_allocate_seat_on_assignment_rejects_inactive_bus(self):
		registration = self._registration("007")
		inactive_bus_assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=Bus.objects.create(bus_number="BUS-INACTIVE-B", capacity=2, is_active=False),
			driver=Driver.objects.create(name="Driver Inactive B", is_available=True),
			semester=self.semester,
			is_active=True,
		)

		result = allocate_seat_on_assignment(registration, inactive_bus_assignment)

		self.assertEqual(result, "Assigned bus is inactive")


class FeeVerificationApiRegressionTests(TestCase):
	def setUp(self):
		self.client = APIClient()

		self.admin = User.objects.create_user(
			username="admin_fee_reg",
			password="adminpass",
			is_staff=True,
		)

		student_user = User.objects.create_user(username="student_fee_reg", password="pass1234")
		self.profile = StudentProfile.objects.create(
			user=student_user,
			roll_number="22F-FEE-001",
			department="CS",
			batch="22",
			phone="000",
			address="Address",
		)

		self.semester = Semester.objects.create(
			name="Summer",
			year=2026,
			term="U",
			is_active=True,
			registration_open=True,
		)
		self.route = Route.objects.create(name="Route Verify", is_active=True)
		self.stop = Stop.objects.create(name="Stop Verify")

		TransportRegistration.objects.create(
			student=self.profile,
			semester=self.semester,
			route=self.route,
			stop=self.stop,
			status="Pending",
		)

		self.fee = FeeVerification.objects.create(
			student=self.profile,
			semester=self.semester,
			amount=45000,
			challan_number="CHN-VERIFY-001",
			is_verified=False,
		)

		RouteAssignment.objects.create(
			route=self.route,
			bus=Bus.objects.create(bus_number="BUS-VERIFY", capacity=2, is_active=True),
			driver=Driver.objects.create(name="Driver Verify", is_available=True),
			semester=self.semester,
			is_active=True,
		)

	def test_verify_fee_endpoint_does_not_duplicate_seat_allocation(self):
		self.client.force_authenticate(user=self.admin)

		first = self.client.post(f"/api/fee-verifications/{self.fee.id}/verify/")
		second = self.client.post(f"/api/fee-verifications/{self.fee.id}/verify/")

		self.assertEqual(first.status_code, 200)
		self.assertEqual(second.status_code, 200)

		registration = SemesterRegistration.objects.get(
			student=self.profile,
			semester=self.semester,
		)
		self.assertEqual(SeatAllocation.objects.filter(registration=registration).count(), 1)


class RouteAssignmentSerializerValidationTests(TestCase):
	def setUp(self):
		self.semester = Semester.objects.create(
			name="Serializer Semester",
			year=2027,
			term="S",
			is_active=True,
			registration_open=True,
		)
		self.route = Route.objects.create(name="Serializer Route", is_active=True)
		self.bus = Bus.objects.create(bus_number="BUS-SER-1", capacity=40, is_active=True)
		self.driver = Driver.objects.create(name="Driver Ser 1", is_available=True)

	def _payload(self, **overrides):
		payload = {
			"route_id": self.route.id,
			"bus_id": self.bus.id,
			"driver_id": self.driver.id,
			"semester_id": self.semester.id,
			"is_active": True,
		}
		payload.update(overrides)
		return payload

	def test_rejects_activation_when_route_inactive(self):
		inactive_route = Route.objects.create(name="Inactive Route", is_active=False)
		serializer = RouteAssignmentSerializer(data=self._payload(route_id=inactive_route.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("route is inactive", str(serializer.errors))

	def test_rejects_activation_when_bus_inactive(self):
		inactive_bus = Bus.objects.create(bus_number="BUS-SER-2", capacity=40, is_active=False)
		serializer = RouteAssignmentSerializer(data=self._payload(bus_id=inactive_bus.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("bus is inactive", str(serializer.errors))

	def test_rejects_activation_when_driver_unavailable(self):
		unavailable_driver = Driver.objects.create(name="Driver Ser 2", is_available=False)
		serializer = RouteAssignmentSerializer(data=self._payload(driver_id=unavailable_driver.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("driver is unavailable", str(serializer.errors))

	def test_rejects_activation_when_semester_inactive(self):
		inactive_semester = Semester.objects.create(
			name="Inactive Sem",
			year=2028,
			term="F",
			is_active=False,
			registration_open=True,
		)
		serializer = RouteAssignmentSerializer(data=self._payload(semester_id=inactive_semester.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("semester is inactive", str(serializer.errors))

	def test_rejects_duplicate_bus_assignment_in_same_semester(self):
		RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)

		other_driver = Driver.objects.create(name="Driver Ser 3", is_available=True)
		serializer = RouteAssignmentSerializer(data=self._payload(driver_id=other_driver.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("bus is already assigned", str(serializer.errors))

	def test_rejects_duplicate_driver_assignment_in_same_semester(self):
		RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)

		other_bus = Bus.objects.create(bus_number="BUS-SER-3", capacity=40, is_active=True)
		serializer = RouteAssignmentSerializer(data=self._payload(bus_id=other_bus.id))

		self.assertFalse(serializer.is_valid())
		self.assertIn("driver is already assigned", str(serializer.errors))

	def test_update_same_instance_does_not_fail_duplicate_checks(self):
		assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)

		serializer = RouteAssignmentSerializer(
			instance=assignment,
			data=self._payload(),
			partial=True,
		)

		self.assertTrue(serializer.is_valid(), serializer.errors)


class SignalHandlersTests(TestCase):
	def setUp(self):
		self.semester = Semester.objects.create(
			name="Signal Sem",
			year=2028,
			term="S",
			is_active=True,
			registration_open=True,
		)
		self.other_semester = Semester.objects.create(
			name="Signal Other Sem",
			year=2028,
			term="F",
			is_active=True,
			registration_open=True,
		)

		self.route = Route.objects.create(name="Signal Route", is_active=True)
		self.other_route = Route.objects.create(name="Other Route", is_active=True)
		self.stop = Stop.objects.create(name="Signal Stop")

		self.bus = Bus.objects.create(bus_number="BUS-SIG-1", capacity=2, is_active=True)
		self.other_bus = Bus.objects.create(bus_number="BUS-SIG-2", capacity=2, is_active=True)

		self.driver = Driver.objects.create(name="Signal Driver", is_available=True)
		self.other_driver = Driver.objects.create(name="Other Driver", is_available=True)

		self.assignment = RouteAssignment.objects.create(
			route=self.route,
			bus=self.bus,
			driver=self.driver,
			semester=self.semester,
			is_active=True,
		)
		self.unrelated_assignment = RouteAssignment.objects.create(
			route=self.other_route,
			bus=self.other_bus,
			driver=self.other_driver,
			semester=self.other_semester,
			is_active=True,
		)

		self.user = User.objects.create_user(username="signal_user", password="pass1234")
		self.profile = StudentProfile.objects.create(
			user=self.user,
			roll_number="22F-SIG-001",
			department="CS",
			batch="22",
			phone="000",
			address="Address",
		)

	def test_route_inactive_deactivates_matching_assignments_only(self):
		self.route.is_active = False
		self.route.save(update_fields=["is_active"])

		self.assignment.refresh_from_db()
		self.unrelated_assignment.refresh_from_db()
		self.assertFalse(self.assignment.is_active)
		self.assertTrue(self.unrelated_assignment.is_active)

	def test_bus_inactive_deactivates_matching_assignments_only(self):
		self.bus.is_active = False
		self.bus.save(update_fields=["is_active"])

		self.assignment.refresh_from_db()
		self.unrelated_assignment.refresh_from_db()
		self.assertFalse(self.assignment.is_active)
		self.assertTrue(self.unrelated_assignment.is_active)

	def test_driver_unavailable_deactivates_matching_assignments_only(self):
		self.driver.is_available = False
		self.driver.save(update_fields=["is_available"])

		self.assignment.refresh_from_db()
		self.unrelated_assignment.refresh_from_db()
		self.assertFalse(self.assignment.is_active)
		self.assertTrue(self.unrelated_assignment.is_active)

	def test_semester_inactive_deactivates_matching_assignments_only(self):
		self.semester.is_active = False
		self.semester.save(update_fields=["is_active"])

		self.assignment.refresh_from_db()
		self.unrelated_assignment.refresh_from_db()
		self.assertFalse(self.assignment.is_active)
		self.assertTrue(self.unrelated_assignment.is_active)

	@patch("apps.transport.signals.allocate_seat_for_student")
	def test_fee_verification_signal_calls_allocation_when_verified(self, mock_allocate):
		registration = SemesterRegistration.objects.create(
			student=self.profile,
			semester=self.semester,
			route=self.route,
			stop=self.stop,
			status="Pending",
		)

		FeeVerification.objects.create(
			student=self.profile,
			semester=self.semester,
			amount=5000,
			is_verified=True,
			challan_number="CHN-SIG-001",
		)

		mock_allocate.assert_called_once_with(registration)

	@patch("apps.transport.signals.allocate_seat_for_student")
	def test_fee_verification_signal_skips_unverified_fees(self, mock_allocate):
		SemesterRegistration.objects.create(
			student=self.profile,
			semester=self.semester,
			route=self.route,
			stop=self.stop,
			status="Pending",
		)

		FeeVerification.objects.create(
			student=self.profile,
			semester=self.semester,
			amount=5000,
			is_verified=False,
			challan_number="CHN-SIG-002",
		)

		mock_allocate.assert_not_called()

	@patch("apps.transport.signals.allocate_seat_for_student")
	def test_fee_verification_signal_skips_when_registration_missing(self, mock_allocate):
		FeeVerification.objects.create(
			student=self.profile,
			semester=self.semester,
			amount=5000,
			is_verified=True,
			challan_number="CHN-SIG-003",
		)

		mock_allocate.assert_not_called()

	@patch("apps.transport.signals.allocate_seat_for_student")
	def test_fee_verification_signal_skips_when_seat_already_exists(self, mock_allocate):
		registration = SemesterRegistration.objects.create(
			student=self.profile,
			semester=self.semester,
			route=self.route,
			stop=self.stop,
			status="Approved",
		)
		SeatAllocation.objects.create(
			registration=registration,
			route_assignment=self.assignment,
			seat_number=1,
		)

		FeeVerification.objects.create(
			student=self.profile,
			semester=self.semester,
			amount=5000,
			is_verified=True,
			challan_number="CHN-SIG-004",
		)

		mock_allocate.assert_not_called()


# ── Driver console ──────────────────────────────────────────────────────────
import requests as _requests
from unittest import mock as _mock
from rest_framework.test import APIClient as _APIClient
from apps.transport.models import BusLocationPing as _Ping, RouteStop as _RouteStop
from apps.transport.serializers import DriverSerializer as _DriverSerializer


@_mock.patch("apps.transport.signals.is_off_route", return_value=(False, 5.0))
@_mock.patch("apps.transport.views.req_lib.get", side_effect=_requests.RequestException("offline"))
class DriverConsoleTests(TestCase):
	def setUp(self):
		self.semester = Semester.objects.create(name="Drv Sem", year=2029, term="F", is_active=True, registration_open=True)
		self.route = Route.objects.create(name="Drv Route", is_active=True)
		stop_a = Stop.objects.create(name="Drv A", latitude="24.921500", longitude="67.084700")
		self.stop_b = Stop.objects.create(name="Drv B", latitude="24.931500", longitude="67.094700")
		self.rs_a = _RouteStop.objects.create(route=self.route, stop=stop_a, stop_order=1)
		self.rs_b = _RouteStop.objects.create(route=self.route, stop=self.stop_b, stop_order=2)
		bus = Bus.objects.create(bus_number="DRV-1", capacity=10, is_active=True)
		serializer = _DriverSerializer(data={"name": "Drv One", "cnic": "1", "username": "drv_one", "password": "drivepass1"})
		self.assertTrue(serializer.is_valid(), serializer.errors)
		self.driver = serializer.save()
		assignment = RouteAssignment.objects.create(route=self.route, bus=bus, driver=self.driver, semester=self.semester, is_active=True)
		self.student = User.objects.create_user(username="drv_student", password="pass1234")
		profile = StudentProfile.objects.create(user=self.student, roll_number="22K-DRV-1", department="CS", batch="22", phone="0", address="x")
		registration = SemesterRegistration.objects.create(student=profile, semester=self.semester, route=self.route, stop=self.stop_b, status="Confirmed")
		SeatAllocation.objects.create(registration=registration, route_assignment=assignment, seat_number=3)
		self.client = _APIClient()

	def test_driver_login_role_and_overview(self, *_):
		self.assertTrue(self.driver.user.groups.filter(name="Driver").exists())
		self.client.force_authenticate(user=self.driver.user)
		self.assertEqual(self.client.get("/api/user/").data["role"], "driver")
		response = self.client.get("/api/driver/overview/")
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["assignment"]["bus"]["bus_number"], "DRV-1")
		counts = {s["id"]: s["student_count"] for s in response.data["stops"]}
		self.assertEqual(counts[self.stop_b.id], 1)
		self.assertEqual(response.data["passengers"][0]["seat_number"], 3)

	def test_students_cannot_use_driver_endpoints_or_list_profiles(self, *_):
		self.client.force_authenticate(user=self.student)
		self.assertEqual(self.client.get("/api/driver/overview/").status_code, 403)
		self.client.force_authenticate(user=self.driver.user)
		self.assertEqual(self.client.get("/api/students/").data["count"], 0)  # list is paginated

	def test_location_ping_stores_fix_and_returns_ordered_etas(self, *_):
		self.client.force_authenticate(user=self.driver.user)
		response = self.client.post(
			"/api/driver/location/",
			{"latitude": 24.9215, "longitude": 67.0847, "remaining": [self.rs_b.id, self.rs_a.id]},
			format="json",
		)
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(_Ping.objects.count(), 1)
		etas = response.data["etas"]
		self.assertEqual([e["route_stop_id"] for e in etas], [self.rs_b.id, self.rs_a.id])
		self.assertLess(etas[0]["eta_seconds"], etas[1]["eta_seconds"])
		self.assertEqual(response.data["eta_source"], "estimate")

	def test_deleting_driver_removes_login(self, *_):
		admin = User.objects.create_user(username="drv_admin", password="adminpass", is_staff=True)
		user_id = self.driver.user_id
		self.client.force_authenticate(user=admin)
		self.assertEqual(self.client.delete(f"/api/drivers/{self.driver.id}/").status_code, 204)
		self.assertFalse(User.objects.filter(pk=user_id).exists())