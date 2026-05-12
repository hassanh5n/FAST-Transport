# FAST Transport — University Transport Management System

> **A full-stack web application for digitizing and streamlining university transport operations at FAST NUCES, Karachi.**

![Project Status](https://img.shields.io/badge/status-active-success.svg)
![Django](https://img.shields.io/badge/Django-6.0-092E20?logo=django)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)

---

## Introduction

**FAST Transport** is a transport management platform built for FAST NUCES to replace manual, paper-based processes with a modern digital system. It enables students to register for transport each semester, pay fees online, track buses in real-time, and manage route changes — while giving administrators a centralized dashboard for managing the entire fleet, verifying payments, and resolving complaints.

Built with **Django REST Framework** and **React (Vite)**, it follows a clean three-tier architecture with JWT authentication, role-based access control, and responsive design across all devices.

### 🌐 Live Access
[https://fast-transport.vercel.app](https://fast-transport.vercel.app)


---

## Key Features

### Authentication & Security
*   **JWT Authentication**: Secure token-based auth with automatic access token refresh.
*   **Email OTP Verification**: 6-digit OTP sent via Brevo SMTP for signup and password reset.
*   **Role-Based Access Control**: Separate Student and Admin portals with permission enforcement.
*   **NUCES Email Restriction**: Only `@nu.edu.pk` email addresses are accepted for student registration.

### Student Portal
*   **Semester Registration**: Register for transport each semester, select preferred stops, and get auto-assigned to the optimal route.
*   **Seat Allocation**: Automatic seat assignment based on availability, with waitlist management for full routes.
*   **Fee Payment**: Stripe-integrated challan system with OTP confirmation for secure payments.
*   **Live Bus Tracking**: Real-time GPS tracking with interactive MapLibre GL maps, OSRM road routing, and stop markers.
*   **Route Change Requests**: Request stop/route changes with auto-routing to the best-fit route.
*   **Complaints**: Submit, track, and receive updates on transport-related complaints.

### Admin Dashboard
*   **Analytics Overview**: Real-time stats — total students, active buses, pending complaints, unverified fees, and more.
*   **Fleet Management**: Full CRUD for buses, drivers, routes, stops, and route-stop assignments with morning/evening ETAs.
*   **Route Assignments**: Assign buses and drivers to routes per semester with seat capacity tracking.
*   **Fee Verification**: Review and verify student fee payments, triggering automatic registration approval.
*   **Complaint Resolution**: Respond to and resolve student complaints with status tracking.
*   **Route Change Approvals**: Approve or deny route change requests with real-time seat availability checks.
*   **PDF & CSV Exports**: Export route sheets, fee reports, and student assignment lists.

---

## Technology Stack

*   **Frontend**: [React 19](https://react.dev) with [Vite](https://vite.dev), React Router, Axios, Stripe.js
*   **Backend**: [Django 6](https://djangoproject.com), [Django REST Framework](https://www.django-rest-framework.org/), SimpleJWT
*   **Database**: [PostgreSQL](https://postgresql.org) (hosted on [Neon](https://neon.tech))
*   **Maps**: [MapLibre GL](https://maplibre.org) + OpenFreeMap tiles + OSRM routing engine
*   **Email**: [Brevo](https://brevo.com) SMTP for transactional emails (OTP, notifications)
*   **Payments**: [Stripe](https://stripe.com) sandbox for fee payment simulation
*   **Deployment**: Vercel (frontend) · Render (backend) · Neon (database)

---

## Installation & Setup

Follow these steps to get the project running on your local machine.

### Prerequisites
*   [Python 3.12+](https://python.org/downloads/)
*   [Node.js 18+](https://nodejs.org/)
*   [PostgreSQL 15+](https://postgresql.org/download/) installed and running

### 1. Clone the Repository
```bash
git clone https://github.com/hassanh5n/FAST-Transport.git
cd FAST-Transport
```

### 2. Configure Environment
Create a `.env` file in the project root:
```env
DJANGO_SECRET_KEY=your-secret-key
DATABASE_NAME=fasttransportdb
DATABASE_USER=postgres
DATABASE_PASSWORD=your-db-password
EMAIL_HOST_PASSWORD=your-brevo-smtp-key
VITE_API_BASE_URL=http://localhost:8000
```

### 3. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings.dev
python manage.py createsuperuser --settings=config.settings.dev
python manage.py runserver --settings=config.settings.dev
```

### 4. Frontend Setup
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```

The application should now be accessible at `http://localhost:5173`.

---

## Deployment 🚀

FAST Transport is deployed on multiple platforms for demo.

### ☁️ Architecture
*   **Frontend Hosting**: [Vercel](https://vercel.com) — React SPA with automatic builds from GitHub.
*   **Backend Hosting**: [Render](https://render.com) — Django API served via Gunicorn with WhiteNoise for static files.
*   **Database**: [Neon](https://neon.tech) — Serverless PostgreSQL with 0.5 GB free tier.
*   **Email Service**: [Brevo](https://brevo.com) — 300 free emails/day for OTP and notifications.

### 🔄 Deployment Pipeline
1.  Push to `main` branch on GitHub.
2.  **Vercel** auto-builds and deploys the React frontend.
3.  **Render** auto-builds the Django backend — runs migrations, collects static files, and creates the superuser from environment variables.

---

## Project Structure

```
FAST-Transport/
 ├── backend/
 │   ├── apps/transport/          # Models, Views, Serializers, Permissions
 │   │   └── management/commands/ # Custom management commands
 │   ├── config/settings/         # Split settings (base / dev / prod)
 │   ├── build.sh                 # Render deploy script
 │   └── requirements.txt
 ├── frontend/
 │   ├── src/pages/admin/         # 14 admin pages
 │   ├── src/pages/student/       # 9 student pages
 │   ├── src/pages/auth/          # Login, Signup, OTP, Password Reset
 │   ├── src/components/          # Reusable UI (PageShell, Table, Sidebar)
 │   ├── src/services/            # API client & service layer
 │   └── src/theme.js             # Design system tokens
 └── docker-compose.yml           # Local Docker setup (optional)
```

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1.  Fork the project
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## License

This project is for educational purposes. All rights reserved.

---
