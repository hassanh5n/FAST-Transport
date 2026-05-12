# 🚌 FAST Transport Management System

A full-stack web application for managing university transport operations at FAST NUCES, Karachi. Built with **Django REST Framework** and **React (Vite)**.

> **Live Demo:** [Frontend](https://fast-transport.vercel.app) · [API](https://fast-transport-api.onrender.com)

---

## ✨ Features

### Student Portal
- **Semester Registration** — Register for transport each semester, select stops, auto-assigned routes
- **Seat Allocation** — Automatic seat assignment with waitlist management
- **Fee Payment** — Stripe-integrated challan generation with OTP verification
- **Route Change Requests** — Request stop/route changes, auto-routed to best-fit route
- **Live Bus Tracking** — Real-time GPS tracking with MapLibre GL maps
- **View Routes** — Browse all routes, stops, ETAs, and driver info
- **Complaints** — Submit and track transport-related complaints
- **Transport Card** — Digital transport ID with QR code

### Admin Dashboard
- **Analytics Dashboard** — Real-time stats (students, buses, routes, pending actions)
- **Bus Management** — CRUD for buses with capacity and occupancy tracking
- **Driver Management** — Assign drivers, track availability and license info
- **Route & Stop Management** — Create routes, assign stops with morning/evening ETAs
- **Route Assignments** — Assign buses + drivers to routes per semester
- **Semester Management** — Create/activate semesters, manage registration windows
- **Fee Verification** — Review and verify student fee payments
- **Complaint Resolution** — Respond to and resolve student complaints
- **Route Change Approvals** — Approve/deny route change requests with seat availability check
- **Student Bus Assignments** — View all student-to-bus mappings
- **PDF & CSV Exports** — Export route sheets, fee reports, and student lists

### Authentication & Security
- **JWT Authentication** with auto-refresh
- **Email OTP Verification** (signup + password reset) via Brevo SMTP
- **Role-based Access Control** (Student vs Admin)
- **NUCES Email Restriction** — Only `@nu.edu.pk` emails for student signup

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite, React Router, Axios, MapLibre GL, Stripe.js |
| **Backend** | Django 6, Django REST Framework, SimpleJWT |
| **Database** | PostgreSQL (Neon in production) |
| **Email** | Brevo (Sendinblue) SMTP |
| **Maps** | MapLibre GL + OpenFreeMap tiles + OSRM routing |
| **Deployment** | Vercel (frontend) + Render (backend) + Neon (database) |

---

## 📁 Project Structure

```
FAST-Transport/
├── backend/
│   ├── apps/transport/          # Main Django app
│   │   ├── models.py            # 15+ models (Student, Bus, Route, etc.)
│   │   ├── views.py             # API views & business logic
│   │   ├── serializers.py       # DRF serializers
│   │   ├── permissions.py       # Role-based permissions
│   │   ├── seatallocation.py    # Seat allocation algorithm
│   │   └── management/commands/ # Custom management commands
│   ├── config/
│   │   └── settings/            # Split settings (base/dev/prod)
│   ├── build.sh                 # Render build script
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI (PageShell, Table, Sidebar, etc.)
│   │   ├── pages/
│   │   │   ├── admin/           # 14 admin pages
│   │   │   ├── student/         # 9 student pages
│   │   │   └── auth/            # Login, Signup, OTP, Forgot/Reset Password
│   │   ├── services/            # API client & service layer
│   │   ├── theme.js             # Design system tokens
│   │   └── utils/               # Hooks (useBreakpoint, etc.)
│   ├── vercel.json              # SPA routing config
│   └── vite.config.js
└── docker-compose.yml           # Local Docker setup
```

---

## 🚀 Local Development

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL 15+

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

# Create database
psql -U postgres -c "CREATE DATABASE fasttransportdb;"

# Run migrations
python manage.py migrate --settings=config.settings.dev

# Create admin user
python manage.py createsuperuser --settings=config.settings.dev

# Start server
python manage.py runserver --settings=config.settings.dev
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DATABASE_NAME=fasttransportdb
DATABASE_USER=postgres
DATABASE_PASSWORD=your-db-password

# Frontend
VITE_API_BASE_URL=http://localhost:8000

# Email (Brevo SMTP)
EMAIL_HOST_PASSWORD=your-brevo-smtp-key
```

---

## 🌐 Deployment

Deployed on free-forever platforms:

| Service | Platform | Purpose |
|---|---|---|
| Frontend | [Vercel](https://vercel.com) | React SPA hosting |
| Backend | [Render](https://render.com) | Django API (gunicorn + whitenoise) |
| Database | [Neon](https://neon.tech) | Managed PostgreSQL |
| Email | [Brevo](https://brevo.com) | Transactional SMTP (300/day free) |

See the full deployment guide in the project docs.

---

## 📊 Database Schema

The system uses 15+ interconnected models:

- **StudentProfile** — Extended user profile (roll number, department, batch)
- **Semester** — Academic semesters with registration windows
- **Route / Stop / RouteStop** — Transport network with ETAs
- **Bus / Driver** — Fleet management
- **RouteAssignment** — Bus + Driver + Route per semester
- **SemesterRegistration** — Student transport enrollment
- **TransportRegistration** — Registration with fee tracking
- **SeatAllocation / Waitlist** — Automated seat management
- **Challan / FeeVerification** — Payment lifecycle
- **Complaint** — Issue tracking with admin resolution
- **RouteChangeRequest** — Stop/route change workflow
- **Notification** — In-app notification system
- **OTPVerification** — Email verification tokens

---

## 👥 Team

Developed as a Software Engineering course project at **FAST NUCES, Karachi**.

---

## 📄 License

This project is for educational purposes. All rights reserved.