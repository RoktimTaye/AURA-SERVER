# Aura Backend API Documentation v1.0

Welcome to the **Aura Backend API** documentation. This document is designed to provide frontend developers with all the necessary information to integrate the Aura web/mobile application with the backend services.

## Table of Contents
1. [General Information](#general-information)
2. [Authentication](#authentication)
3. [Base URL](#base-url)
4. [Endpoint Reference](#endpoint-reference)
    - [Health Check](#health-check)
    - [Directory View](#directory-view)
    - [Price Submission](#price-submission)
    - [Voting System](#voting-system)
    - [Price Forecasting](#price-forecasting)
    - [Admin Operations](#admin-operations)
5. [Data Models (Schemas)](#data-models-schemas)
6. [Response Codes](#response-codes)

---

## General Information
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL (SQLAlchemy ORM)
- **Content-Type**: `application/json`
- **CORS**: Enabled for all origins (`*`)

## Authentication
Currently, the API uses a simple `user_id` parameter for identification in certain endpoints.
*Note: In production, this should be replaced with JWT-based authentication.*

## Base URL
Development: `http://localhost:8000`
API Prefix: `/api` (most endpoints reside here)

## Interactive Documentation
FastAPI automatically generates interactive documentation for this API:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs) (Best for testing endpoints)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc) (Best for viewing detailed specs)

---

## Endpoint Reference

### Health Check
Check if the backend services are online.

- **URL**: `/`
- **Method**: `GET`
- **Auth Required**: No
- **Response**:
    ```json
    {
      "status": "Online",
      "message": "Aura is running"
    }
    ```

### Directory View
Fetch a list of items with their price ranges, locations, and community votes.

- **URL**: `/api/directory`
- **Method**: `GET`
- **Auth Required**: No
- **Query Parameters**:
    - `district` (string, optional): Filter by location name.
    - `item` (string, optional): Filter by item name (supports partial match).
- **Success Response**: `200 OK`
    ```json
    [
      {
        "id": 1,
        "item_name": "Petrol",
        "price_display": "105-110 /Litre",
        "range_miles": 5.0,
        "area": "Downtown",
        "votes": 12
      }
    ]
    ```

### Price Submission
Submit a new price entry for an item at a specific location. Includes ML-based anomaly detection.

- **URL**: `/api/upload`
- **Method**: `POST`
- **Auth Required**: Yes (`user_id` query parameter)
- **Query Parameters**:
    - `user_id` (integer, required): ID of the submitting user.
- **Request Body**:
    ```json
    {
      "item_name": "Diesel",
      "location_name": "Westside Station",
      "price": 98.5,
      "distance_miles": 2.5
    }
    ```
- **Success Response**: `200 OK`
    - Returns the created entry object.
    - *Note*: If the ML engine detects an anomaly, the entry status will be set to `FLAGGED` instead of `APPROVED`.

### Voting System
Upvote or downvote a price entry to verify its accuracy.

- **URL**: `/api/vote/{entry_id}`
- **Method**: `PUT`
- **Auth Required**: No
- **Path Parameters**:
    - `entry_id` (integer): The ID of the price entry.
- **Query Parameters**:
    - `upvote` (boolean, default: `true`): Set to `false` for a downvote.
- **Success Response**: `200 OK`
    ```json
    {
      "id": 1,
      "votes": 13,
      ...
    }
    ```

### Price Forecasting
Get predicted price trends for a specific item based on historical data.

- **URL**: `/api/forcast/{item_id}`
- **Method**: `GET`
- **Auth Required**: No
- **Path Parameters**:
    - `item_id` (integer): The ID of the item.
- **Success Response**: `200 OK`
    ```json
    {
      "item_id": 1,
      "prediction": [
        {"timestamp": "2024-03-20T12:00:00", "price": 106.5},
        ...
      ]
    }
    ```

### Admin Operations
Administrative tools for managing the database.

#### Delete Entry
Completely remove a bad or fraudulent entry.

- **URL**: `/api/admin/entry/{entry_id}`
- **Method**: `DELETE`
- **Auth Required**: No (Currently unrestricted)
- **Path Parameters**:
    - `entry_id` (integer): ID of the entry to delete.
- **Success Response**: `200 OK`
    ```json
    {
      "message": "Deleted successfully"
    }
    ```
- **Error Response**: `404 Not Found` if entry does not exist.

---

## Data Models (Schemas)

### PriceCreate
Used for POST `/api/upload`.
| Field | Type | Description |
| :--- | :--- | :--- |
| `item_name` | string | Name of the commodity (e.g., "Petrol") |
| `location_name` | string | Name of the station/area |
| `price` | float | Current price |
| `distance_miles`| float | Distance from user's current location |

### DirectoryView
Returned by GET `/api/directory`.
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | integer | Entry ID |
| `item_name` | string | Item name |
| `price_display` | string | Formatted range: "min-max /unit" |
| `range_miles` | float | Recorded distance |
| `area` | string | Location name |
| `votes` | integer | Net community votes |

---

## Response Codes
The API uses standard HTTP status codes:

- `200 OK`: Request succeeded.
- `201 Created`: Resource created successfully.
- `400 Bad Request`: Validation error or invalid input.
- `404 Not Found`: The requested resource does not exist.
- `500 Internal Server Error`: Something went wrong on the server side.

---

## Technical Insights for Frontend
To help with UI design and state management:

### Price Forecasting Logic
- **Requirement**: Minimum of **10 historical data points** are required for a forecast to be generated. If fewer points exist, the `prediction` field will be an empty list `[]`.
- **Output**: Returns predicted prices for the **next 7 days**.
- **Model**: Uses Meta's Prophet model with daily and weekly seasonality.

### Anomaly Detection (Spam Protection)
- **Logic**: Uses Z-Score calculation based on historical price averages.
- **Threshold**: Any price submission more than **3 standard deviations** from the mean is automatically flagged.
- **UI Impact**: If a submission returns a status of `FLAGGED`, you might want to show a toast message to the user: *"Your submission is under review by the community due to unusual price data."*

---

## Development Setup

### 1. Environment Variables
Create a `.env` file in the `app/` directory:
```env
DATABASE_URL=postgresql://user:password@localhost/dbname
```

### 2. Run the Backend
Ensure you are in the root directory and your virtual environment is active:
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

---
*Generated by Gemini CLI Agent*
