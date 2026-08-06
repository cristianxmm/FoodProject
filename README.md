# Cafeteria Management System - Optibelt

A robust, web-based system developed in Python (Flask) to manage and track employee access to the company cafeteria using badge scanning (QR/Barcode). Designed for a Raspberry Pi 5 dual-screen deployment, it features kernel-level barcode scanning independent of UI focus, automated shift validation, a live kitchen dashboard, a secure Human Resources panel, smart Excel report generation, and an offline-ready kiosk architecture.

## ✨ Key Features

* **Focus-Free Hardware Scanning (`evdev`):** Uses Linux kernel input events (`/dev/input/`) to capture Honeywell 1250g barcode scans in the background, eliminating UI focus issues or accidental keyboard inputs.
* **Dual-View Architecture:** Simultaneous support for front-end employee scanning kiosk and back-end kitchen/LNC live dashboard.
* **Offline-Ready Architecture (Tank Mode):** Frontend assets (Bootstrap 5, Icons, Chart.js) are bundled locally. The system is 100% immune to internet outages and operates seamlessly on a local network.
* **Smart Shift Validation:** Prevents duplicate meal claims by automatically checking shift timeframes (Shift 1, Shift 2, and Shift 3).
* **Kitchen / LNC Dashboard (`/lnc`):** Live-updating monitor displaying real-time meal counts and recent scans, with a manual override option for special authorizations.
* **Human Resources Panel (`/rh`):** A secure, password-protected dashboard displaying daily consumption statistics, shift distributions, and live activity tables.
* **Automatic Excel Import & Export:** Populate the employee database directly from an Excel sheet (`empleados.xlsx`) and generate filtered consumption reports tagged by shift.
* **Production-Ready WSGI:** Powered by `waitress` and multi-threading to handle background hardware monitoring and concurrent web requests reliably.

## 🛠️ Technologies Used

* **Backend:** Python 3, Flask, Waitress WSGI, `evdev` (Linux input handling), `threading`
* **Data Processing & Database:** SQLite3 (`comedor.db`), Pandas, OpenPyXL
* **Frontend:** HTML5, CSS3, Bootstrap 5 (Hosted Locally), Bootstrap Icons (Hosted Locally), JavaScript (AJAX Polling)
* **Hardware:** Raspberry Pi 5, Honeywell 1250g USB Scanner
* **Security & Config:** Environment variables (`python-dotenv`), secure session management

## 🚀 Installation and Setup Guide

### 1. System Prerequisites (Linux / Raspberry Pi OS)
Install required build tools for Python header files and C compilers (necessary for compiling `evdev`):
```bash
sudo apt update
sudo apt install -y build-essential python3-dev python3-venv git

```

### 2. Clone the Repository

```bash
git clone [https://github.com/cristianxmm/FoodProject.git](https://github.com/cristianxmm/FoodProject.git)
cd FoodProject

```

### 3. Create and Activate Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate

```

### 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt

```

### 5. Configure Environment Variables

Create a `.env` file in the root directory of the project:

```env
SECRET_KEY=your_random_secret_key_here
RH_USER=your_hr_username
RH_PASS=your_hr_password

```

### 6. Import Employees & Initialize Database

Place your employee catalog in the root folder as `empleados.xlsx`. The file must contain the headers `ID`, `First Name`, and `Last Name`.

Run the database initializer:

```bash
python3 init_db.py

```

### 7. Grant Hardware Permissions for the Scanner

To allow Python to read `/dev/input/` events without requiring `sudo`:

```bash
sudo usermod -aG input $USER
newgrp input

```

### 8. Run the Application

```bash
python3 app.py

```

The server will start using Waitress. You can access the system at:

* **Employee Kiosk (Front Display):** `http://localhost:5000`
* **Kitchen Dashboard (Back Display):** `http://localhost:5000/lnc`
* **HR Administration Panel:** `http://localhost:5000/rh`

## 📁 Database Structure (`comedor.db`)

The system uses SQLite with foreign key enforcement enabled:

* **`Empleados` (Employees):** Personnel catalog populated from `empleados.xlsx`.
* `id_employee` (`TEXT PRIMARY KEY`): Badge/Nómina ID (preserves leading zeros).
* `firstname` (`TEXT`): Full name (concatenated `First Name` + `Last Name`).


* **`Consumos` (Consumptions):** Logs of all successful meal transactions.
* `id_consumption` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `id_employee` (`TEXT`, Foreign Key -> `Empleados.id_employee`)
* `date_hour` (`TEXT`): Timestamp of the scan (`YYYY-MM-DD HH:MM:SS`).
* `Metodo` (`TEXT`): Method of entry (`escaner`, `manual`, or `Manual (Autorizado)`).



```

```