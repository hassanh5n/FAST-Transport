<div align="center">

# 🚌 FAST Transport

**University Transport Management System — FAST NUCES, Karachi**

A full-stack web application to digitize and streamline campus transport operations.

[![Django](https://img.shields.io/badge/Django-6.0-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white)](https://vite.dev)

[Live Demo →](https://fast-transport.vercel.app)

</div>

---

## 🎯 What It Does

| Students | Admins |
|---|---|
| Register for transport each semester | Manage buses, drivers, routes & stops |
| Auto-assigned seats (or waitlisted) | Verify fee payments |
| Pay fees via Stripe with OTP | Approve/deny route change requests |
| Track buses in real-time on a map | Resolve student complaints |
| Request route/stop changes | Export reports as PDF & CSV |
| File & track complaints | View analytics dashboard |

---

## 🛠️ Tech Stack

```
Frontend    →  React 19 · Vite · React Router · MapLibre GL · Stripe.js
Backend     →  Django 6 · DRF · SimpleJWT · Gunicorn · WhiteNoise
Database    →  PostgreSQL (Neon)
Email       →  Brevo SMTP (OTP verification)
Maps        →  MapLibre GL + OpenFreeMap + OSRM routing
Deployment  →  Vercel (frontend) · Render (backend) · Neon (database)
```

---

## 🚀 Quick Start

### Backend
```bash
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings.dev
python manage.py createsuperuser --settings=config.settings.dev
python manage.py runserver --settings=config.settings.dev
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables
Create `.env` in the project root:
```env
DJANGO_SECRET_KEY=your-secret-key
DATABASE_NAME=fasttransportdb
DATABASE_USER=postgres
DATABASE_PASSWORD=your-password
EMAIL_HOST_PASSWORD=your-brevo-key
VITE_API_BASE_URL=http://localhost:8000
```

---

## 📁 Structure

```
├── backend/
│   ├── apps/transport/     # Models, Views, Serializers, Permissions
│   ├── config/settings/    # Split settings (base / dev / prod)
│   └── build.sh            # Render deploy script
├── frontend/
│   ├── src/pages/admin/    # 14 admin pages
│   ├── src/pages/student/  # 9 student pages
│   ├── src/pages/auth/     # Login, Signup, OTP, Password Reset
│   ├── src/components/     # Reusable UI (PageShell, Table, Sidebar)
│   └── src/theme.js        # Design system tokens
```

---

## 🔐 Key Features

- **JWT auth** with auto token refresh
- **Email OTP** for signup & password reset
- **Role-based access** — Student vs Admin
- **Live GPS tracking** with real-time bus markers
- **Automatic seat allocation** with waitlist fallback
- **Stripe sandbox payments** with OTP confirmation
- **Responsive design** — works on mobile & desktop
- **PDF exports** — route sheets, fee reports

---

## 👥 Team

Built as a Software Engineering course project at **FAST NUCES, Karachi**.

---

<div align="center">
<sub>© 2026 FAST-NUCES · Transport Management System</sub>
</div>