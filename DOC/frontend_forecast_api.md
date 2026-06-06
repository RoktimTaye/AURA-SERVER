# Forecast API Integration Guide (Lazy Loading)

## Overview
The Forecast API has been updated to use **Lazy Loading**. This means that if a prediction for a specific item and district doesn't exist in the database, the backend will trigger the Machine Learning model to generate it *on the fly*.

**Important:** Because the ML model runs in real-time if data is missing, the API response might take **~3 to 5 seconds** to resolve. 

## API Endpoint
`GET /api/forecast/{item_id}?district={district_name}`

### Query Parameters
- `item_id` (Path variable): The ID of the item (e.g., 1 for Rice)
- `district` (Query variable): The name of the district (e.g., "Guwahati")

## How the Frontend Should Handle This

### 1. UI Loading State (Critical)
Since the request can take up to 5 seconds, you **must** implement a loading state. 
- Show a loading spinner, skeleton loader, or a message like *"Generating AI Price Forecast..."* while the fetch request is pending.
- Disable the "Predict" button or row click while loading to prevent duplicate requests.

### 2. Success Response
If the prediction is successful, you will receive a 200 OK with the following JSON structure:

```json
{
  "item_id": 1,
  "district": "Guwahati",
  "advice": "Wait to buy",
  "forecast": [
    {
      "date": "2026-06-07T00:00:00",
      "predicted_price": 45.5,
      "yhat_lower": 43.0,
      "yhat_upper": 48.0
    },
    {
      "date": "2026-06-08T00:00:00",
      "predicted_price": 44.2,
      "yhat_lower": 42.1,
      "yhat_upper": 46.5
    }
    // ... up to 7 days of forecast
  ]
}
```

**UI Mapping:**
- **`advice`**: Display this prominently (e.g., Green for "Buy Now", Red/Yellow for "Wait to buy").
- **`forecast` array**: Use this to plot your price trend chart. Plot `predicted_price` as the main line, and use `yhat_lower`/`yhat_upper` for a shaded confidence interval area if your charting library supports it.

### 3. Insufficient Data Response
If there isn't enough historical data for the ML model to generate a prediction, it will return a 200 OK with a message instead of the forecast data:

```json
{
  "message": "Insufficient data for forecast"
}
```

**UI Mapping:**
- Check if `response.message` exists. If it does, show a friendly empty state to the user: *"Not enough historical data available to generate a reliable forecast for this location."*
