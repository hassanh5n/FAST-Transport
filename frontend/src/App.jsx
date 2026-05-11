import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/home";
import Login from "./pages/auth/login";
import Signup from "./pages/auth/signup";
import ForgotPassword from "./pages/auth/ForgotPassword";
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

// Protect staff-only routes
function StaffRoute({ children }) {
  const token = localStorage.getItem("access");
  const isStaff = localStorage.getItem("is_staff") === "true";
  if (!token) return <Navigate to="/login" replace />;
  if (!isStaff) return <Navigate to="/student/dashboard" replace />;
  return children;
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
        <Route path="/verify-otp" element={<OTPVerification />} />
        <Route path="/dashboard" element={<PrivateRoute><DashboardRedirect /></PrivateRoute>} />

        {/* Student routes */}
        <Route path="/student/dashboard" element={<StudentRoute><StudentDashboard /></StudentRoute>} />
        <Route path="/student/transport" element={<StudentRoute><StudentTransport /></StudentRoute>} />
        <Route path="/student/complaints" element={<StudentRoute><StudentComplaints /></StudentRoute>} />
        <Route path="/student/routes" element={<StudentRoute><ViewRoutes /></StudentRoute>} />
        <Route path="/student/transport-registrations" element={<StudentRoute><TransportRegistration /></StudentRoute>} />
        <Route path="/student/challan" element={<StudentRoute><StudentChallanPage /></StudentRoute>} />
        <Route path="/student/challan/:id" element={<StudentRoute><ChallanPage /></StudentRoute>} />
        <Route path="/student/map" element={<StudentRoute><StudentMap /></StudentRoute>} />
        <Route path="/student/route-change" element={<StudentRoute><StudentRouteChange /></StudentRoute>} /> {/* ✅ NEW */}

        {/* Admin routes */}
        <Route path="/admin/dashboard" element={<StaffRoute><AdminDashboard /></StaffRoute>} />
        <Route path="/admin/students" element={<StaffRoute><StudentsPage /></StaffRoute>} />
        <Route path="/admin/buses" element={<StaffRoute><BusesPage /></StaffRoute>} />
        <Route path="/admin/drivers" element={<StaffRoute><DriversPage /></StaffRoute>} />
        <Route path="/admin/routes" element={<StaffRoute><RoutesPage /></StaffRoute>} />
        <Route path="/admin/assignments" element={<StaffRoute><AssignmentsPage /></StaffRoute>} />
        <Route path="/admin/complaints" element={<StaffRoute><AdminComplaintsPage /></StaffRoute>} />
        <Route path="/admin/stops" element={<StaffRoute><StopsPage /></StaffRoute>} />
        <Route path="/admin/semesters" element={<StaffRoute><SemestersPage /></StaffRoute>} />
        <Route path="/admin/routestop" element={<StaffRoute><RouteStopsPage /></StaffRoute>} />
        <Route path="/admin/feeverifications" element={<StaffRoute><AdminFeeVerifications /></StaffRoute>} />
        <Route path="/admin/student-bus-assignments" element={<StaffRoute><StudentBusAssignmentsPage /></StaffRoute>} />
        <Route path="/admin/routechangerequests" element={<StaffRoute><AdminRouteChangeRequests /></StaffRoute>} /> {/* ✅ NEW */}

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;