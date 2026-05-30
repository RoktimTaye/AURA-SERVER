from datetime import timedelta, timezone,datetime
from fastapi import APIRouter, Depends,HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..import crud,schemas,models
from ..ml import engine as ml_engine
from dotenv import load_dotenv, find_dotenv
import jwt
import os

router = APIRouter()

basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, "..", "..", ".env")
load_dotenv(find_dotenv(env_path))
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRES_MINUTES",30))
def create_access_token(data: dict,expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode,SECRET_KEY,algorithm=ALGORITHM)
        return encoded_jwt
@router.post("/signup")
def signup(user:schemas.UserCreate,db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db,email=user.email)
    if db_user:
        raise HTTPException(status_code=400,detail="Email already registered")
    return crud.create_user(db=db,user=user)

@router.post("/login")
def login(user_credentials: schemas.UserLogin,db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db,email=user_credentials.email)
    if not user or not crud.verify_password(user_credentials.password,user.hashed_password):
        raise HTTPException(status_code=401,detail="Invalid credentials")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
    access_token = create_access_token(data={"sub": user.email,"role":user.role},expires_delta=access_token_expires)
    '''Here Later JWT Token needed to be returned to the frontend, for now to test in postman we return a message'''
    # return {"message": "Login Sucessfull", "role": user.role}
    return {"access_token": access_token,"token_type": "bearer"}

@router.get("/directory", response_model=List[schemas.DirectoryView])
def read_directory(district: str = None, item: str = None, db: Session= Depends(get_db),skip: int = 0,limit: int = 100):  # ty:ignore[invalid-parameter-default]
    # data = crud.get_directory_data(db,search_item=item,search_district=district)
    
    #Pass pagination to CRUD
    data = crud.get_directory_data(db,search_item=item,search_district=district,limit=limit,offset=skip)
    formatted_data = []
    '''NOTICE: No more database queries inside this loop!
        We access 'min_price' and 'max_price' which were already fetched.'''
    for entry in data:
        '''Old Seperate Rough section'''
        # formatted_data.append({
        #     "id":entry.id,
        #     "item_name":entry.item_name,
        #     "price_display": f"{int(entry.min_price)}-{int(entry.max_price)} /{entry.unit}",
        #     "range_miles":entry.range_miles,
        #     "area": entry.area,
        #     "votes": entry.votes
        # })
        '''New Seperate code'''
        # range_stats = db.query(
        #     func.min(models.PriceEntry.price),
        #     func.max(models.PriceEntry.price)
        # ).join(models.Location).filter(
        #     models.PriceEntry.item_id == entry.item_id,
        #     models.Location.district == entry.district,
        #     models.PriceEntry.status == "APPROVED"
        # ).first()
        
        formatted_data.append({
            "id": entry.id,
            "item_name": entry.item_name,
            "unit": entry.unit,
            "price_modal": entry.price_modal,
            # "price_range": f"{int(range_stats[0])}-{int(range_stats[1])}" if range_stats[0] else"N/A",
            "price_range":
    # f"{int(range_stats[0])}-{int(range_stats[1])}"if range_stats and range_stats[0] is not None else "N/A"
    f"{int(entry.min_price)} - {int(entry.max_price)}" if entry.min_price is not None else "N/A",
            "locality_full": f"{entry.district} {entry.market_name}",
            "votes": entry.votes,
            "status": entry.status,
            "timestamp": entry.timestamp
        })
    return formatted_data

@router.post("/upload")
def upload_price(submission: schemas.PriceCreate, user_id: int, db: Session = Depends(get_db)):
    # Fetch historical data fro this specific item to check for anomalies
    historical_prices = db.query(models.PriceEntry.price).join(models.Item).filter(models.Item.name == submission.item_name).filter(models.PriceEntry.status == "APPROVED").all()
    # Convert SQL results to a simple list of numbers
    price_list = [p[0] for p in historical_prices]
    #ML logic to check if the new price is a "FAKE" or "EXTREME" outlier
    is_anomaly = ml_engine.detect_anomaly(submission.price,price_list)
    status = "FLAGGED" if is_anomaly else "APPROVED"
    ''' Saves the submission to the DB
    User ID is now passed dynamically through the endpoint '''
    return crud.create_price_submission(db,submission,user_id=user_id,status=status)

@router.put("/vote/{entry_id}")
def vote_entry(entry_id: int, upvote: bool = True, db:Session = Depends(get_db)):
    return crud.update_entry_vote(db,entry_id,increment=upvote)

#Fetch pre-computed Forecast
@router.get("/forecast/{item_id}")
# def get_item_forcast(item_id: int, location_id: int, db: Session = Depends(get_db)):
def get_item_forcast(item_id: int, district: str, db: Session = Depends(get_db)):
    # prices = db.query(
    #     models.PriceEntry.price,
    #     models.PriceEntry.timestamp
    #     ).filter(models.PriceEntry.item_id == item_id).filter(models.PriceEntry.status == "APPROVED").all()
    
    # prediction = ml_engine.generate_forcast(prices)
    
    # return {"item_id": item_id, "prediction": prediction}
    predictions = db.query(models.Forecast).filter(
        models.Forecast.item_id == item_id,
        models.Forecast.district == district
    ).order_by(models.Forecast.target_date.asc()).all()
    
    if not predictions:
        return {"message": "Insufficient data for forecast"}
    
    #Generate Dicision Support
    latest_price = predictions[0].predicted_price
    future_price = predictions[-1].predicted_price
    advice = "Buy Now" if future_price> latest_price else "Wait to buy"
    
    return {
        "item_id": item_id,
        "district": district,
        "advice": advice,
            "forecast": [{"date": p.target_date,
                            "predicted_price": p.predicted_price,
                            "yhat_lower": p.yhat_lower,
                            "yhat_upper": p.yhat_upper
                        }
                        for p in predictions]}

@router.delete("/admin/entry/{entry_id}")
def admin_delete(entry_id:int, db:Session = Depends(get_db)):
    #Completely removes bad entry from the database
    sucess = crud.delete_entry(db,entry_id)
    if not sucess:
        raise HTTPException(status_code=404,detail="Entry not found")
    return {"message": "Deleted sucessfully"}
