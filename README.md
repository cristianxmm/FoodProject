# Cafeteria Management System - Optibelt

A robust, web-based system developed in Python (Flask) to manage and track employee access to the company cafeteria using badge scanning (QR/Barcode). It features automated shift validation, a secure Human Resources administration panel, smart Excel report generation, and an offline-ready kiosk architecture.

## ✨ Key Features

* **Scanning Kiosk:** Fast and responsive interface for employees to scan their badges.
* **Offline-Ready Architecture (Tank Mode):** Frontend assets (Bootstrap, Icons, Chart.js) are bundled locally. The kiosk is 100% immune to internet outages and will continue to operate flawlessly on a local network.
* **Smart Validation:** Prevents duplicate meals by checking if an employee has already eaten during their current shift (Shift 1, Shift 2, or Shift 3).
* **Human Resources Panel:** A secure, password-protected dashboard displaying real-time daily consumption statistics and interactive charts.
* **Excel Export:** Generates detailed reports based on a date range, automatically calculating and tagging each record with its corresponding shift.
* **Production-Ready:** Powered by the `waitress` WSGI server, ensuring the application can handle multiple simultaneous scans without freezing or crashing.

## 🛠️ Technologies Used

* **Backend:** Python 3, Flask, Waitress
* **Database:** SQLite3 (`comedor.db`)
* **Data Processing:** Pandas
* **Frontend:** HTML5, CSS3, Bootstrap 5 (Hosted Locally), Chart.js (Hosted Locally)
* **Security:** Environment variables (`python-dotenv`), secure session management.

## 🚀 Installation and Setup Guide

**1. Clone the repository**
```bash
git clone https://github.com/cristianxmm/FoodProject.git
cd <repository-directory>
```

**2. Create and activate the Virtual Environment**
*On Windows:*
```bash
python -m venv .venv
.venv\Scripts\activate
```
*On macOS/Linux:*
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure Environment Variables**
Create a file named `.env` in the root directory of the project and add your secure credentials (this file is ignored by Git and will not be uploaded to GitHub):
```env
FLASK_SECRET_KEY=your_random_secret_key_here
RH_USER=your_hr_username
RH_PASS=your_hr_password
```

**5. Run the Application**
```bash
python app.py
```
The production server will start. You can access the system in your web browser at:
* **Scanning Kiosk (Employees):** `http://localhost:5000`
* **HR Dashboard:** `http://localhost:5000/rh`

## 📁 Database Structure (`comedor.db`)

The system relies on an SQLite database with two main tables:
* `Empleados` (Employees): Stores the personnel catalog (`id_employee`, `firstname`).
* `Consumos` (Consumptions): Logs every successful scan (`id_consumption`, `id_employee`, `date_hour`, `Metodo`).
```