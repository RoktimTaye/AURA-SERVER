from pydantic import BaseModel, ConfigDict
from datetime import datetime  # noqa: F401
from typing import List,Optional  # noqa: F401

# Data send by the users
class PriceCreate(BaseModel):
    item_name:str
    location_name:str
    price:float
    distance_miles:float
    
    class Config:
        # orm_mode = True
        model_config = ConfigDict(from_attributes=True)
# What data users will receive(Table view)
class DirectoryView(BaseModel):
    id:int
    item_name:str
    price_display:str
    range_miles:float
    area:str
    votes:int
    
    class Config:
        # orm_mode = True
        model_config = ConfigDict(from_attributes=True)
        
# Admin Login
class UserLogin(BaseModel):
    email:str
    password:str
