from pydantic import BaseModel, ConfigDict,Field
from datetime import datetime  # noqa: F401
from typing import List,Optional  # noqa: F401

# Data send by the users
#For Price Submission (including hierarchical location)
class PriceCreate(BaseModel):
    item_name:str
    location_name:str # e.g Market name(Fnacy Bazar)
    district: str #e.g< Kampur Metropolitian
    state: str # e.g, Assam
    price:float
    distance_miles:float
    
    
        # orm_mode = True
    model_config = ConfigDict(from_attributes=True)

class PriceUpdate(BaseModel):
    price: Optional[float] = None
    item_name: Optional[str] = None
    location_name: Optional[str] = None

# What data users will receive(Table view)
class DirectoryView(BaseModel):
    id: int
    item_id: int
    item_name:str
    unit:str
    price_modal:float
    price_range: str
    locality_full:str
    votes:int
    status: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class ForecastDay(BaseModel):
    date: datetime
    predicted_price: float
    yhat_lower: float
    yhat_upper: float

class PredictionResponse(BaseModel):
    item_id:int
    # location_id: int
    location_id: Optional[int] = None
    district_id: Optional[str] = None
    advice: str
    forecast_data: List[ForecastDay]

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str = Field(..., alias="fullName")
    role: str = "user"
    model_config = ConfigDict(populate_by_name=True)

class Token(BaseModel):
    access_token: str
    token_type: str
# Admin Login
class UserLogin(BaseModel):
    email:str
    password:str