# Aura: Backend & ML Architecture Documentation

This document provides a comprehensive overview of the Aura backend architecture, its data flow, and the integration of Machine Learning (ML) components. This is intended to serve as the foundation for building an automated ML pipeline.

---

## 1. System Overview

Aura is a price transparency platform that allows users to report and track local prices of items. The system consists of a FastAPI backend, a PostgreSQL database (hosted on Neon), and an ML engine for anomaly detection and price forecasting.

### Key Technologies
- **Backend Framework:** FastAPI (Python)
- **Database:** PostgreSQL (Neon Serverless)
- **ORM:** SQLAlchemy
- **ML Libraries:** Facebook Prophet (Forecasting), NumPy (Anomaly Detection), Pandas (Data Manipulation)
- **Validation:** Pydantic

---

## 2. Backend Architecture

The backend follows a modular structure to separate concerns:

### `app/main.py`
The entry point of the application. It initializes the FastAPI app, sets up CORS middleware, and includes API routers.

### `app/database.py`
Handles database connection pooling using SQLAlchemy and defines the base class for models. It uses a Neon PostgreSQL connection string.

### `app/models.py`
Defines the database schema:
- **`User`**: User authentication and roles (admin/user).
- **`Item`**: Inventory of items (e.g., Rice, Milk) with units.
- **`Location`**: Geographic areas where prices are reported.
- **`PriceEntry`**: The core data record linking items, locations, and users with price, distance, votes, and status (APPROVED/FLAGGED).

### `app/schemas.py`
Pydantic models for data validation and serialization:
- `PriceCreate`: For incoming price submissions.
- `DirectoryView`: For formatted output of the directory.
- `UserLogin`: For authentication.

### `app/crud.py`
Contains database operation logic (Create, Read, Update, Delete). It abstracts the SQL queries from the API endpoints.

---

## 3. Machine Learning (ML) Integration

The ML logic is housed in `app/ml/engine.py` and is integrated directly into the API flow.

### A. Anomaly Detection (Real-time)
- **Method:** Z-Score Outlier Detection.
- **Trigger:** Executed during the `POST /api/upload` process.
- **Logic:**
    - Calculates the mean and standard deviation of historical approved prices for an item.
    - If the new price is > 3 standard deviations from the mean (Z-Score > 3), it is flagged.
- **Status:** Integrated. Any entry with `status="FLAGGED"` is excluded from the public directory until reviewed.

### B. Price Forecasting (On-demand)
- **Method:** Facebook Prophet (Time-series analysis).
- **Trigger:** Executed during the `GET /api/forcast/{item_id}` request.
- **Logic:**
    - Requires at least 10 data points.
    - Trains a Prophet model on daily and weekly seasonality.
    - Predicts prices for the next 7 days.
- **Status:** Integrated. Returns predicted values (`yhat`) and timestamps.

---

## 4. API Data Flow

### Data Submission Pipeline
1. **Frontend** sends a `PriceCreate` payload to `/api/upload`.
2. **Backend** fetches historical approved prices for the specific item.
3. **ML Engine** runs `detect_anomaly`.
4. **CRUD** saves the entry with status `APPROVED` or `FLAGGED`.

### Data Consumption Pipeline
1. **Frontend** requests `/api/directory` with optional filters (item, district).
2. **CRUD** executes a grouped SQL query to find min/max prices and aggregate votes for `APPROVED` entries.
3. **Backend** formats the data into `DirectoryView` and returns it to the UI.

### Forecast Pipeline
1. **Frontend** requests `/api/forcast/{item_id}`.
2. **Backend** fetches all `APPROVED` price entries for the item.
3. **ML Engine** runs `generate_forcast` using Prophet.
4. **Backend** returns a list of 7-day predictions.

---

## 5. ML Pipeline Automation Goals

To move towards a fully automated ML pipeline, the following steps are envisioned:

### 1. Model Retraining Automation
- Currently, Prophet models are trained on-the-fly. For scale, we should:
    - Periodically pre-calculate forecasts and store them in a cache or a specific table.
    - Implement a trigger-based retraining (e.g., every 50 new submissions).

### 2. Anomaly Detection Refinement
- Improve the Z-Score threshold based on domain-specific price volatility.
- Implement a "Human-in-the-loop" (HITL) system where admins can review FLAGGED entries to improve the detection model.

### 3. Deployment & CI/CD (GitHub Actions Plan)
To fully automate the build, test, and deployment lifecycle, a robust CI/CD pipeline using **GitHub Actions** will be implemented. This ensures that both the backend APIs and ML models are rigorously tested before reaching production.

#### A. Continuous Integration (CI) Strategy
The CI workflow will trigger on every push and pull request to the `main` branch.
- **Environment Setup:** Provision a Python 3.11 environment.
- **Dependency Management:** Install required packages (`fastapi`, `prophet`, `pytest`, `sqlalchemy`, etc.) via a `requirements.txt` or `Pipfile`.
- **Code Quality:** Run linting tools (e.g., `ruff`, `flake8`, or `black`) to enforce PEP 8 standards.
- **Automated Testing:** 
  - Execute unit tests using `pytest`.
  - Validate core API endpoints (e.g., `/api/directory`, `/api/upload`).
  - Test ML logic separately, mocking the database to ensure the anomaly detection and forecasting functions return expected structural outputs.

#### B. Continuous Deployment (CD) Strategy
The CD workflow will trigger automatically upon a successful merge to the `main` branch.
- **Containerization (Docker):**
  - Create a `Dockerfile` based on `python:3.11-slim`.
  - Install system dependencies required by ML libraries (`build-essential`, `libpq-dev`, `gcc`).
  - Build and tag the Docker image.
- **Artifact Registry:** Push the built Docker image to a registry like GitHub Container Registry (GHCR) or Docker Hub.
- **Deployment:** Automatically deploy the new container to a cloud hosting provider (e.g., AWS, Render, Railway).
- **Environment Variables:** Securely inject secrets (e.g., `DATABASE_URL`) from GitHub Secrets into the deployment environment.

This GitHub Actions setup guarantees that any changes to the ML pipeline or backend logic are safely validated and seamlessly deployed without manual intervention.

---

## 6. Directory Structure
```text
C:\Users\Raktim\Desktop\UNIVERSITY PROJECT\AURA\server\
├── app/
│   ├── api/
│   │   └── endpoints.py      # API routes
│   ├── ml/
│   │   ├── engine.py         # ML Logic (Prophet, NumPy)
│   │   └── models/           # (Placeholder for saved models)
│   ├── crud.py               # DB operations
│   ├── database.py           # DB connection
│   ├── main.py               # Entry point
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # Pydantic schemas
│   └── .env                  # Environment variables
├── seed_db.py                # Script to populate initial data
└── BACKEND_API.md            # API Documentation
```
