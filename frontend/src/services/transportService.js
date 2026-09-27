import api from "./api";

export const getToken = (credentials) => api.post("/api/token/", credentials);
export const getUser = () => api.get("/api/user/");
export const signup = (data) => api.post("/api/signup/", data);
export const forgotPassword = (data) => api.post("/api/forgot-password/", data);
export const resetPassword = (data) => api.post("/api/reset-password/", data);

export const getDashboard = () => api.get("/api/dashboard/");

export const getStudents = () => api.get("/api/students/");

export const getBuses = () => api.get("/api/buses/");
export const createBus = (data) => api.post("/api/buses/", data);
export const updateBus = (id, data) => api.patch(`/api/buses/${id}/`, data);
export const deleteBus = (id) => api.delete(`/api/buses/${id}/`);

export const getDrivers = () => api.get("/api/drivers/");
export const createDriver = (data) => api.post("/api/drivers/", data);
export const updateDriver = (id, data) => api.patch(`/api/drivers/${id}/`, data);
export const deleteDriver = (id) => api.delete(`/api/drivers/${id}/`);

export const getRoutes = () => api.get("/api/routes/");
export const getRoutesMap = () => api.get("/api/routes/map/");
export const createRoute = (data) => api.post("/api/routes/", data);
export const updateRoute = (id, data) => api.patch(`/api/routes/${id}/`, data);
export const deleteRoute = (id) => api.delete(`/api/routes/${id}/`);
export const getRouteOverview = (id) => api.get(`/api/routes/${id}/overview/`);
export const getRouteMapDetail = (id) => api.get(`/api/routes/${id}/map-detail/`);
export const saveRouteBuilder = (id, data) => api.patch(`/api/routes/${id}/builder/`, data);
export const resolveMapLocation = (data) => api.post("/api/admin/maps/location/", data);
export const previewRouteGeometry = (stopIds) => api.post("/api/admin/maps/route-preview/", { stop_ids: stopIds });

export const getAssignments = () => api.get("/api/route-assignments/");
export const createAssignment = (data) => api.post("/api/route-assignments/", data);
export const updateAssignment = (id, data) => api.patch(`/api/route-assignments/${id}/`, data);
export const deleteAssignment = (id) => api.delete(`/api/route-assignments/${id}/`);

export const getSemesters = () => api.get("/api/semesters/");
export const createSemester = (data) => api.post("/api/semesters/", data);
export const updateSemester = (id, data) => api.patch(`/api/semesters/${id}/`, data);
export const deleteSemester = (id) => api.delete(`/api/semesters/${id}/`);

export const getComplaints = () => api.get("/api/complaints/");
export const createComplaint = (data) => api.post("/api/complaints/", data);
export const resolveComplaint = (id, data) =>
	api.patch(`/api/complaints/${id}/resolve/`, data);

export const getStops = () => api.get("/api/stops/");
export const createStop = (data) => api.post("/api/stops/", data);
export const updateStop = (id, data) => api.patch(`/api/stops/${id}/`, data);
export const deleteStop = (id) => api.delete(`/api/stops/${id}/`);

export const getRouteStops = () => api.get("/api/routestops/");
export const createRouteStop = (data) => api.post("/api/routestops/", data);
export const updateRouteStop = (id, data) => api.patch(`/api/routestops/${id}/`, data);
export const deleteRouteStop = (id) => api.delete(`/api/routestops/${id}/`);

export const getDriverByName = (name) => api.get(`/api/drivers/?search=${name}`);
export const getDriverById = (id) => api.get(`/api/drivers/${id}/public_detail/`)

export const createRegistration = (data) => api.post("/api/transport-registrations/", data);
export const getRegistration = () => api.get("/api/transport-registrations/");
export const getEligibleRouteStops = (semesterId) =>
  api.get(`/api/registration/eligible-route-stops/${semesterId ? `?semester=${semesterId}` : ""}`);
export const updateRegistration = (id, data) => api.patch(`/api/transport-registrations/${id}/`, data);

export const getChallan = (id) => api.get(`/api/transport-registrations/${id}/challan/`);
export const payChallan = (registrationId) =>api.post(`/api/transport-registrations/${registrationId}/challan/pay/`);

export const listFeeVerifications = () => api.get("/api/fee-verifications/list/");
export const verifyFee = (id) => api.post(`/api/fee-verifications/${id}/verify/`);

export const listEligibleSeatAssignments = () =>
	api.get("/api/seat-allocations/eligible-registrations/");
export const assignStudentSeat = (data) => api.post("/api/seat-allocations/assign/", data);
export const listCurrentSeatAllocations = () =>
	api.get("/api/seat-allocations/current-allocations/");
export const reassignStudentSeat = (data) => api.post("/api/seat-allocations/reassign/", data);

export const verifyOtp = (data) =>
  api.post("/api/verify-otp/", data);

export const resendOtp = (data) =>
  api.post("/api/resend-otp/", data);

export const submitRouteChangeRequest = (data) =>
  api.post("/api/route-change-requests/", data);
 
export const cancelRouteChangeRequest = (id) =>
  api.post(`/api/route-change-requests/${id}/cancel/`);
 
export const getMyRouteChangeRequests = () =>
  api.get("/api/route-change-requests/");
 
// Admin
export const listAllRouteChangeRequests = () =>
  api.get("/api/route-change-requests/");
 
export const approveRouteChangeRequest = (id, admin_remarks = "") =>
  api.post(`/api/route-change-requests/${id}/approve/`, { admin_remarks });
 
export const denyRouteChangeRequest = (id, admin_remarks = "") =>
  api.post(`/api/route-change-requests/${id}/deny/`, { admin_remarks });

// ── Stripe Payment + OTP ──
export const createPaymentIntent = (regId) =>
  api.post(`/api/transport-registrations/${regId}/create-payment-intent/`);

export const confirmStripePayment = (regId) =>
  api.post(`/api/transport-registrations/${regId}/confirm-stripe-payment/`);

export const verifyPaymentOtp = (regId, otp) =>
  api.post(`/api/transport-registrations/${regId}/verify-payment-otp/`, { otp });

// ── Notifications ──
export const getNotifications = () => api.get("/api/notifications/");
export const markNotificationRead = (id) =>
  api.post(`/api/notifications/${id}/mark-read/`);
export const markAllNotificationsRead = () =>
  api.post("/api/notifications/mark-all-read/");
export const deleteNotification = (id) =>
  api.delete(`/api/notifications/${id}/`);
export const clearAllNotifications = () =>
  api.delete("/api/notifications/clear-all/");

// ── Waitlist / seat offers ──
export const cancelRegistration = (id) =>
  api.post(`/api/transport-registrations/${id}/cancel/`);
export const getWaitlistStatus = () =>
  api.get("/api/transport-registrations/waitlist-status/");
export const getWaitlist = () => api.get("/api/waitlist/");
export const getWaitlistOverview = () => api.get("/api/waitlist/overview/");
export const fillEmptySeats = (routeId) =>
  api.post("/api/waitlist/fill-empty-seats/", routeId ? { route_id: routeId } : {});

// ── Super admin: admin accounts, roles, activity log ─────────────────────────
export const getAdminModules   = () => api.get("/api/admin-management/modules/");
export const getAdminUsers     = () => api.get("/api/admin-management/admins/");
export const createAdminUser   = (data) => api.post("/api/admin-management/admins/", data);
export const updateAdminUser   = (id, data) => api.patch(`/api/admin-management/admins/${id}/`, data);
export const getAdminRoles     = () => api.get("/api/admin-management/roles/");
export const createAdminRole   = (data) => api.post("/api/admin-management/roles/", data);
export const updateAdminRole   = (id, data) => api.patch(`/api/admin-management/roles/${id}/`, data);
export const deleteAdminRole   = (id) => api.delete(`/api/admin-management/roles/${id}/`);
// params: { actor, module, action, date_from, date_to, q, page, page_size }
export const getActivityLogs   = (params = {}) => api.get("/api/admin-management/activity-logs/", { params });

// ── Driver console ──
export const getDriverOverview = () => api.get("/api/driver/overview/");
export const sendDriverLocation = (data) => api.post("/api/driver/location/", data);