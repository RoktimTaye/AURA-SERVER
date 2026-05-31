# Aura API Integration Guide for Frontend Developers

This document provides comprehensive details for the Aura Backend API to facilitate smooth frontend-backend integration.

## 1. Connection Overview

### Base URLs
- **Development**: `http://localhost:8000`
- **Production**: `https://api.aura-project.com` (Example - Update after deployment)

### API Prefix
All application-specific endpoints are prefixed with `/api`.

### Interactive Documentation
- **Swagger UI**: `/docs` (Best for testing)
- **ReDoc**: `/redoc` (Detailed documentation)

---

## 2. Authentication Flow

The API uses **JWT (JSON Web Tokens)** for secure access to protected endpoints (like price submission).

### Step 1: Signup
- **Endpoint**: `POST /api/signup`
- **Payload**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword"
  }
  ```

### Step 2: Login
- **Endpoint**: `POST /api/login`
- **Payload**: Same as signup.
- **Response**:
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "bearer"
  }
  ```

### Step 3: Authenticated Requests
Include the token in the `Authorization` header for protected endpoints:
```http
Authorization: Bearer <your_access_token>
```

---

## 3. Endpoint Reference

### 3.1 Directory & Price List
Fetch the latest price data with optional filtering and pagination.

- **URL**: `GET /api/directory`
- **Query Parameters**:
  - `district` (string): Filter by district name.
  - `item` (string): Filter by item name.
  - `skip` (int, default: 0): Offset for pagination.
  - `limit` (int, default: 100): Number of records to return.
- **Success Response**: `200 OK` (List of objects)
  ```json
  [
    {
      "id": 1,
      "item_name": "Petrol",
      "unit": "Litre",
      "price_modal": 105.5,
      "price_range": "102 - 108",
      "locality_full": "Kamrup Metropolitan Fancy Bazar",
      "votes": 15,
      "status": "APPROVED",
      "timestamp": "2024-03-20T12:00:00Z"
    }
  ]
  ```

### 3.2 Price Submission (Protected)
Submit a new price entry. The backend performs ML-based anomaly detection.

- **URL**: `POST /api/upload`
- **Auth Required**: Yes
- **Query Parameters**:
  - `user_id` (int): ID of the submitting user.
- **Request Body**:
  ```json
  {
    "item_name": "Diesel",
    "location_name": "Fancy Bazar",
    "district": "Kamrup Metropolitan",
    "state": "Assam",
    "price": 98.5,
    "distance_miles": 2.5
  }
  ```
- **Response Details**:
  - If the price is within normal ranges, `status` will be `APPROVED`.
  - If an anomaly is detected, `status` will be `FLAGGED`.

### 3.3 Voting
Upvote or downvote a price entry to help the community verify data.

- **URL**: `PUT /api/vote/{entry_id}`
- **Path Parameters**:
  - `entry_id` (int): The ID of the price entry.
- **Query Parameters**:
  - `upvote` (bool, default: `true`): `true` for upvote, `false` for downvote.

### 3.4 Price Forecasting
Get 7-day price predictions and AI-driven buying advice.

- **URL**: `GET /api/forecast/{item_id}`
- **Query Parameters**:
  - `district` (string): The district to get the forecast for.
- **Success Response**:
  ```json
  {
    "item_id": 1,
    "district": "Kamrup Metropolitan",
    "advice": "Wait to buy",
    "forecast": [
      {
        "date": "2024-03-21T00:00:00",
        "predicted_price": 104.2,
        "yhat_lower": 102.5,
        "yhat_upper": 105.9
      }
    ]
  }
  ```

### 3.5 Admin Delete
Remove fraudulent entries from the database.

- **URL**: `DELETE /api/admin/entry/{entry_id}`
- **Response**: `{"message": "Deleted successfully"}`

---

## 4. Technical Integration Tips

### Handling CORS
The backend is configured to allow all origins (`*`) by default in development. For production, ensure your frontend domain is added to the `allow_origins` list in `app/main.py`.

### Error Handling
The API returns standard HTTP status codes:
- `400 Bad Request`: Validation errors (e.g., missing fields).
- `401 Unauthorized`: Missing or invalid JWT token.
- `404 Not Found`: Resource does not exist.
- `500 Internal Server Error`: Server-side issues.

### State Management Recommendations
- **Caching**: Forecast data changes slowly (daily). Consider caching it on the frontend for the duration of the user session.
- **Optimistic UI**: When a user votes, you can update the vote count in the UI immediately while the request completes in the background.

### Deployment Checklist
1. Update `Base URL` in your frontend config.
2. Ensure `SECRET_KEY` and other environment variables are set on the hosting platform.
3. Verify that the frontend can reach the backend (check for HTTPS/SSL mixed content issues).

---
*Last Updated: May 2026*
