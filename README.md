# Aura: Price Transparency & ML Forecasting Platform

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=FastAPI&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791.svg?style=flat&logo=postgresql&logoColor=white)
![ML](https://img.shields.io/badge/ML-Prophet%20%7C%20NumPy%20%7C%20Pandas-orange.svg)   

**Aura** is a powerful backend system designed to bring price transparency to local communities. It allows users to report and track the prices of essential groceries, while leveraging Machine Learning to detect anomalies (spam protection) and forecast future price trends.

---

## KEY FEATURES

- **Real-time Price Reporting**: Crowdsourced price submissions for various items and locations.
- **ML Anomaly Detection**: Automated flagging of suspicious price entries using Z-Score statistical analysis (3σ threshold).
- **Price Forecasting**: 7-day price predictions powered by **Meta's Prophet** time-series model.
- **Community-Driven Verification**: A voting system that enables the community to validate reported prices.
- **Dynamic Directory**: Search and filter price entries by district and item name.
- **JWT Authentication**: Secure user registration and login functionality.
- **Admin Dashboard & Management**: Specialized endpoints for platform analytics, entry moderation, and data management.
- **Industry Standard API**: Built with FastAPI, featuring automatic Swagger/OpenAPI documentation.

---

## 🛠 TECH STACK

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous Python)
- **Database**: [PostgreSQL](https://www.postgresql.org/) (via [Neon Serverless](https://neon.tech/))
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
- **Machine Learning**: 
  - [Prophet](https://facebook.github.io/prophet/) (Time-series forecasting)
  - [NumPy](https://numpy.org/) (Statistical anomaly detection)
  - [Pandas](https://pandas.pydata.org/) (Data manipulation)
- **Validation**: [Pydantic](https://docs.pydantic.dev/)
- **Security**: JWT (JSON Web Tokens)

---

## 📂 Project Structure

```text
.
├── app/
│   ├── api/            # API Route definitions & Endpoints
│   ├── ml/             # ML Engine (Anomaly detection & Forecasting)
│   │   ├── engine.py   # Core ML logic
│   │   └── pipeline.py # ML training pipelines
│   ├── crud.py         # Database CRUD operations
│   ├── database.py     # SQLAlchemy configuration
│   ├── main.py         # FastAPI application entry point
│   ├── models.py       # SQLAlchemy database models
│   └── schemas.py      # Pydantic data schemas
├── DOC/                # Architectural & API Documentation
├── Test/               # Database seeding and evaluation scripts
├── .github/workflows/  # CI/CD pipelines
├── requirements.txt    # Project dependencies
└── README.md           # You are here
```

---

## ⚙️ Getting Started

### Prerequisites
- Python 3.11 or higher
- PostgreSQL (Local or Neon.tech)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/aura-backend.git
   cd aura-backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Create a `.env` file in the root directory (or `app/`):
   ```env
   DATABASE_URL=postgresql://user:password@ep-host.region.aws.neon.tech/dbname?sslmode=require
   ```

### Running the Application

Start the development server with hot-reload:
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

---

## 📖 API Documentation

Once the server is running, you can access the interactive documentation:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Core Endpoints Summary
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Health check endpoint |
| `POST` | `/api/signup` | Register a new user |
| `POST` | `/api/login` | Authenticate user and receive JWT |
| `GET` | `/api/directory` | Fetch filtered list of price entries |
| `POST` | `/api/upload` | Submit a new price (Triggers Anomaly Detection) |
| `PUT` | `/api/vote/{entry_id}` | Upvote/Downvote a price entry |
| `GET` | `/api/forecast/{item_id}` | Get 7-day price predictions |

### Admin Endpoints Summary
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/admin/stats` | Fetch overall data statistics |
| `GET` | `/api/admin/analytics` | Fetch advanced analytics & recent activity |
| `PUT` | `/api/admin/entry/{entry_id}` | Edit an existing price entry |
| `PUT` | `/api/admin/entry/{entry_id}/status` | Update approval status of an entry |
| `DELETE` | `/api/admin/entry/{entry_id}` | Delete a price entry permanently |

---

## 🧠 Machine Learning Integration

### Anomaly Detection (Z-Score)
Every submission is analyzed against historical data. If the submitted price exceeds **3 standard deviations** from the mean, it is marked as `FLAGGED` and excluded from the public directory until reviewed by an admin.

### Time-Series Forecasting
Using **Facebook Prophet**, the system analyzes seasonal trends and historical fluctuations to provide a 7-day price outlook. 
*Note: A minimum of 10 data points is required for a valid forecast.*

---

## 🧪 Testing & Data
The `Test/` directory contains several utility scripts:
- `seed_dataset2.py`: Bulk imports government dataset records.
- `evaluate_ml_performance.py`: Generates residual plots and performance metrics for the ML models.
