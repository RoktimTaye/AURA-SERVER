import datetime
from sqlalchemy import Column,Integer,String,Float,DateTime,ForeignKey,UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
# from sqlalchemy.ext.declarative import declarative_base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer,primary_key=True,index=True)
    email = Column(String, unique=True,index=True)
    hashed_password = Column(String)
    role = Column(String,default="user") 
    
class Item(Base):
    __tablename__ = "items"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String,unique=True,index=True)
    unit = Column(String)
    
class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String,index=True)
    district = Column(String,index=True)
    state = Column(String,index=True)
    
    __table_args__ = (UniqueConstraint('name', 'district', 'state', name='_location_uc'),)
class PriceEntry(Base):
    
    # Primary keys and foreign keys
    __tablename__ = "price_entries"
    id = Column(Integer,primary_key=True,index=True)
    item_id = Column(Integer,ForeignKey("items.id"), index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), index=True)
    user_id = Column(Integer,ForeignKey("users.id"))
    
    # Price Entry table attributes (columns)
    price = Column(Float)
    distance_miles = Column(Integer,default=0)
    votes = Column(Integer,default=0)
    status = Column(String,default="APPROVED")
    timestamp = Column(DateTime,default=datetime.UTC, index=True)
    
    # Relationships to pull names easily
    item = relationship("Item")
    location = relationship("Location")

class Forecast(Base):
    __tablename__ = "forecasts"
    id = Column(Integer,primary_key=True,index=True)
    item_id = Column(Integer,ForeignKey("items.id"))
    location_id = Column(Integer,ForeignKey("locations.id"),nullable=True)
    district = Column(String,index=True)
    target_date = Column(DateTime)
    predicted_price = Column(Float)
    yhat_lower = Column(Float)
    yhat_upper = Column(Float)
    trend = Column(String)
    created_at = Column(DateTime,default=datetime.UTC)
    
    item = relationship("Item")
    location = relationship("Location")