// Pages load on demand: the login page no longer downloads the map and chart libraries.
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
const Home = lazy(() => import("./pages/home"));
const Login = lazy(() => import("./pages/auth/login"));
const Signup = lazy(() => import("./pages/auth/signup"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));
const AdminDashboard = lazy(() => import("./pages/admin/dashboard"));
const StudentsPage = lazy(() => import("./pages/admin/students"));
const BusesPage = lazy(() => import("./pages/admin/buses"));
const DriversPage = lazy(() => import("./pages/admin/drivers"));
const RoutesPage = lazy(() => import("./pages/admin/routes"));
const RoutePlansPage = lazy(() => import("./pages/admin/RoutePlans"));
const AssignmentsPage = lazy(() => import("./pages/admin/assignments"));
const StudentDashboard = lazy(() => import("./pages/student/dashboard"));
const StudentTransport = lazy(() => import("./pages/student/transport"));
const StudentComplaints = lazy(() => import("./pages/student/complaints"));
const StopsPage = lazy(() => import("./pages/admin/stops"));
const SemestersPage = lazy(() => import("./pages/admin/semesters"));
const RouteStopsPage = lazy(() => import("./pages/admin/routestops"));
const ViewRoutes = lazy(() => import("./pages/student/ViewRoutes"));
const TransportRegistration = lazy(() => import("./pages/student/registeration"));
const ChallanPage = lazy(() => import("./pages/student/ChallanPage"));
const StudentChallanPage = lazy(() => import("./pages/student/StudentChallanPage"));
const AdminFeeVerifications = lazy(() => import("./pages/admin/AdminFeeVerifications"));
const StudentBusAssignmentsPage = lazy(() => import("./pages/admin/StudentBusAssignments"));
const OTPVerification = lazy(() => import("./pages/auth/OTPVerification"));
const StudentMap = lazy(() => import("./pages/student/StudentMap"));
const AdminComplaintsPage = lazy(() => import("./pages/admin/complaints"));
const NotFoundPage = lazy(() => import("./pages/NotFound"));
import AppFeedbackLayer from "./components/AppFeedbackLayer";
const StudentRouteChange = lazy(() => import("./pages/student/StudentRouteChange"));
const AdminRouteChangeRequests = lazy(() => import("./pages/admin/AdminRouteChangeRequests"));
const AdminExportPage = lazy(() => import("./pages/admin/AdminExport"));
const StudentIncidents = lazy(() => import("./pages/student/StudentIncidents"));
const AdminIncidents = lazy(() => import("./pages/admin/AdminIncidents"));
const RouteBuilder = lazy(() => import("./pages/admin/RouteBuilder"));
const AdminRouteDetail = lazy(() => import("./pages/admin/AdminRouteDetail"));
const AdminWaitlist = lazy(() => import("./pages/admin/AdminWaitlist"));
const AdminManagement = lazy(() => import("./pages/admin/AdminManagement"));
const ActivityLogs = lazy(() => import("./pages/admin/ActivityLogs"));
const DriverDashboard = lazy(() => import("./pages/driver/DriverDashboard"));
const DriverTrip = lazy(() => import("./pages/driver/DriverTrip"));
const DriverPassengers = lazy(() => import("./pages/driver/DriverPassengers"));
import { can, homePath, isSuperAdmin } from "./utils/permissions";

// Redirect /dashboard based on stored role
function DashboardRedirect() {
  return <Navigate to={homePath()} replace />;
}

// The login page: someone already signed in goes straight to their console.
// An expired session still lands there, and the API's 401 handling sends it to /login
// with the session cleared, so this cannot loop.
function GuestRoute({ children }) {
  return localStorage.getItem("access") ? <Navigate to={homePath()} replace /> : children;
}

// Protect any route that requires authentication
function PrivateRoute({ children }) {
  const token = localStorage.getItem("access");
  return token ? children : <Navigate to="/login" replace />;
}

// Protect staff-only routes.
//   module  – admin module key the page belongs to (see backend rbac.MODULES);
//             an array means "any of these".
//   superOnly – page is only for the super admin.
function StaffRoute({ children, module, superOnly = false }) {
  const token = localStorage.getItem("access");
  const isStaff = localStorage.getItem("is_staff") === "true";
  if (!token) return <Navigate to="/login" replace />;
  if (!isStaff) return <Navigate to={homePath()} replace />;
  if (superOnly && !isSuperAdmin()) return <NoAccess />;
  if (module && !can(module)) return <NoAccess />;
  return children;
}

function NoAccess() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'DM Sans', system-ui, sans-serif", padding: "16px" }}>
      <div style={{ textAlign: "center", maxWidth: "380px" }}>
        <h2 style={{ margin: "0 0 8px", color: "#0f1f2d" }}>No access</h2>
        <p style={{ margin: "0 0 18px", color: "#4a6178", fontSize: "14px" }}>
          Your admin role doesn't include this section. Ask the super admin if you need it.
        </p>
        <a href="/admin/dashboard" style={{ color: "#288dc4", fontWeight: 600 }}>Back to console</a>
      </div>
    </div>
  );
}

// Protect student-only routes — staff and drivers go to their own dashboard
function StudentRoute({ children }) {
  const token = localStorage.getItem("access");
  if (!token) return <Navigate to="/login" replace />;
  if (homePath() !== "/student/dashboard") return <Navigate to={homePath()} replace />;
  return children;
}

// Protect driver-only routes
function DriverRoute({ children }) {
  const token = localStorage.getItem("access");
  if (!token) return <Navigate to="/login" replace />;
  if (homePath() !== "/driver/dashboard") return <Navigate to={homePath()} replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AppFeedbackLayer />
      <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-otp" element={<OTPVerification />} />
        <Route path="/dashboard" element={<PrivateRoute><DashboardRedirect /></PrivateRoute>} />

        {/* Student routes */}
        <Route path="/student/dashboard" element={<StudentRoute><StudentDashboard /></StudentRoute>} />
        <Route path="/student/transport" element={<StudentRoute><StudentTransport /></StudentRoute>} />
        <Route path="/student/complaints" element={<StudentRoute><StudentComplaints /></StudentRoute>} />
        <Route path="/student/routes" element={<StudentRoute><ViewRoutes /></StudentRoute>} />
        <Route path="/student/routes-map" element={<StudentRoute><ViewRoutes /></StudentRoute>} />
        <Route path="/student/transport-registrations" element={<StudentRoute><TransportRegistration /></StudentRoute>} />
        <Route path="/student/challan" element={<StudentRoute><StudentChallanPage /></StudentRoute>} />
        <Route path="/student/challan/:id" element={<StudentRoute><ChallanPage /></StudentRoute>} />
        <Route path="/student/map" element={<StudentRoute><StudentMap /></StudentRoute>} />
        <Route path="/student/incidents" element={<StudentRoute><StudentIncidents /></StudentRoute>} />
        <Route path="/student/route-change" element={<StudentRoute><StudentRouteChange /></StudentRoute>} /> {/* ✅ NEW */}

        {/* Driver routes */}
        <Route path="/driver/dashboard" element={<DriverRoute><DriverDashboard /></DriverRoute>} />
        <Route path="/driver/trip" element={<DriverRoute><DriverTrip /></DriverRoute>} />
        <Route path="/driver/passengers" element={<DriverRoute><DriverPassengers /></DriverRoute>} />

        {/* Admin routes */}
        <Route path="/admin/dashboard" element={<StaffRoute><AdminDashboard /></StaffRoute>} />
        <Route path="/admin/students" element={<StaffRoute module="students"><StudentsPage /></StaffRoute>} />
        <Route path="/admin/buses" element={<StaffRoute module="fleet"><BusesPage /></StaffRoute>} />
        <Route path="/admin/drivers" element={<StaffRoute module="fleet"><DriversPage /></StaffRoute>} />
        <Route path="/admin/routes" element={<StaffRoute module="routes"><RoutesPage /></StaffRoute>} />
        <Route path="/admin/route-plans" element={<StaffRoute module="routes"><RoutePlansPage /></StaffRoute>} />
        <Route path="/admin/routes/:id" element={<StaffRoute module="routes"><AdminRouteDetail /></StaffRoute>} />
        <Route path="/admin/routes/:id/edit" element={<StaffRoute module="routes"><RouteBuilder /></StaffRoute>} />
        <Route path="/admin/routes/:id/builder" element={<StaffRoute module="routes"><RouteBuilder /></StaffRoute>} />
        <Route path="/admin/assignments" element={<StaffRoute module="fleet"><AssignmentsPage /></StaffRoute>} />
        <Route path="/admin/complaints" element={<StaffRoute module="complaints"><AdminComplaintsPage /></StaffRoute>} />
        <Route path="/admin/stops" element={<StaffRoute module="routes"><StopsPage /></StaffRoute>} />
        <Route path="/admin/semesters" element={<StaffRoute module="semesters"><SemestersPage /></StaffRoute>} />
        <Route path="/admin/routestop" element={<StaffRoute module="routes"><RouteStopsPage /></StaffRoute>} />
        <Route path="/admin/feeverifications" element={<StaffRoute module="fees"><AdminFeeVerifications /></StaffRoute>} />
        <Route path="/admin/student-bus-assignments" element={<StaffRoute module="seats"><StudentBusAssignmentsPage /></StaffRoute>} />
        <Route path="/admin/waitlist" element={<StaffRoute module="seats"><AdminWaitlist /></StaffRoute>} />
        <Route path="/admin/routechangerequests" element={<StaffRoute module="route_requests"><AdminRouteChangeRequests /></StaffRoute>} />
        <Route path="/admin/incidents" element={<StaffRoute module="incidents"><AdminIncidents /></StaffRoute>} />
        <Route path="/admin/export" element={<StaffRoute module="export"><AdminExportPage /></StaffRoute>} />

        {/* Super admin only */}
        <Route path="/admin/admins" element={<StaffRoute superOnly><AdminManagement /></StaffRoute>} />
        <Route path="/admin/activity-logs" element={<StaffRoute superOnly><ActivityLogs /></StaffRoute>} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;