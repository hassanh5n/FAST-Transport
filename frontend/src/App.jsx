import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/home";
import Login from "./pages/auth/login";
import Signup from "./pages/auth/signup";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";
import AdminDashboard from "./pages/admin/dashboard";
import StudentsPage from "./pages/admin/students";
import BusesPage from "./pages/admin/buses";
import DriversPage from "./pages/admin/drivers";
import RoutesPage from "./pages/admin/routes";
import AssignmentsPage from "./pages/admin/assignments";
import StudentDashboard from "./pages/student/dashboard";
import StudentTransport from "./pages/student/transport";
import StudentComplaints from "./pages/student/complaints";
import StopsPage from "./pages/admin/stops";
import SemestersPage from "./pages/admin/semesters";
import RouteStopsPage from "./pages/admin/routestops";
import ViewRoutes from "./pages/student/ViewRoutes";
import TransportRegistration from "./pages/student/registeration";
import ChallanPage from "./pages/student/ChallanPage";
import StudentChallanPage from "./pages/student/StudentChallanPage";
import AdminFeeVerifications from "./pages/admin/AdminFeeVerifications";
import StudentBusAssignmentsPage from "./pages/admin/StudentBusAssignments";
import OTPVerification from "./pages/auth/OTPVerification";
import StudentMap from "./pages/student/StudentMap";
import AdminComplaintsPage from "./pages/admin/complaints";
import NotFoundPage from "./pages/NotFound";
import AppFeedbackLayer from "./components/AppFeedbackLayer";
import StudentRouteChange from "./pages/student/StudentRouteChange";          
import AdminRouteChangeRequests from "./pages/admin/AdminRouteChangeRequests";
import AdminExportPage from "./pages/admin/AdminExport";
import StudentIncidents from "./pages/student/StudentIncidents";
import AdminIncidents from "./pages/admin/AdminIncidents";
import RouteBuilder from "./pages/admin/RouteBuilder";
import AdminRouteDetail from "./pages/admin/AdminRouteDetail";
import AdminWaitlist from "./pages/admin/AdminWaitlist";
import AdminManagement from "./pages/admin/AdminManagement";
import ActivityLogs from "./pages/admin/ActivityLogs";
import { can, isSuperAdmin } from "./utils/permissions";

// Redirect /dashboard based on stored role
function DashboardRedirect() {
  const isStaff = localStorage.getItem("is_staff") === "true";
  return <Navigate to={isStaff ? "/admin/dashboard" : "/student/dashboard"} replace />;
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
  if (!isStaff) return <Navigate to="/student/dashboard" replace />;
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
        <a href="/admin/dashboard" style={{ color: "#288dc4", fontWeight: 600 }}>Back to dashboard</a>
      </div>
    </div>
  );
}

// Protect student-only routes — staff get redirected to their own dashboard
function StudentRoute({ children }) {
  const token = localStorage.getItem("access");
  const isStaff = localStorage.getItem("is_staff") === "true";
  if (!token) return <Navigate to="/login" replace />;
  if (isStaff) return <Navigate to="/admin/dashboard" replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AppFeedbackLayer />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
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

        {/* Admin routes */}
        <Route path="/admin/dashboard" element={<StaffRoute><AdminDashboard /></StaffRoute>} />
        <Route path="/admin/students" element={<StaffRoute module="students"><StudentsPage /></StaffRoute>} />
        <Route path="/admin/buses" element={<StaffRoute module="fleet"><BusesPage /></StaffRoute>} />
        <Route path="/admin/drivers" element={<StaffRoute module="fleet"><DriversPage /></StaffRoute>} />
        <Route path="/admin/routes" element={<StaffRoute module="routes"><RoutesPage /></StaffRoute>} />
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
    </BrowserRouter>
  );
}

export default App;
