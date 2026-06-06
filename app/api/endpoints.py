from ..ml.module.pipeline import process_single_task
from datetime import timedelta, timezone,datetime
from fastapi import APIRouter, Depends,HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from ..import crud,schemas,models
from ..ml import engine as ml_engine
from dotenv import load_dotenv, find_dotenv
import jwt
import os
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, "..", "..", ".env")
load_dotenv(find_dotenv(env_path))
SECRET_KEY = os.getenv("SECRET_KEY","your-secret-key")
ALGORITHM = os.getenv("ALGORITHM","HS256")
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

@router.get("/directory")
def read_directory(district: Optional[str] = None, item: Optional[str] = None, db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    # Debug print to verify parameters reaching the backend
    print(f"SEARCH DEBUG: district='{district}', item='{item}'")
    
    # Explicitly use keyword arguments to prevent positional mismatch
    items_raw, total = crud.get_directory_data(
        db, 
        search_item=item, 
        search_district=district, 
        limit=limit, 
        offset=skip
    )
    
    formatted_data = []
    for entry in items_raw:
        formatted_data.append({
            "id": entry.id,
            "item_id": entry.item_id,
            "item_name": entry.item_name,
            "unit": entry.unit,
            "price_modal": entry.price_modal,
            "price_range": f"{int(entry.price_modal * 0.95)} - {int(entry.price_modal * 1.05)}",
            "district": entry.district,
            "locality_full": f"{entry.district} {entry.market_name}",
            "votes": entry.votes,
            "status": entry.status,
            "timestamp": entry.timestamp
        })
    
    # Return as an object
    return {"total": total, "items": formatted_data}

def get_current_user_info(token: str = Depends(oauth2_scheme)):
    if not token:
        return None
    try:
        payload = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        return {"email": payload.get("sub"),"role": payload.get("role")}
    except Exception:
        return None

@router.post("/upload")
def upload_price(submission: schemas.PriceCreate, db: Session = Depends(get_db),user_info: dict = Depends(get_current_user_info)):
    
    current_role = "user"
    current_user_id = None
    
    if user_info:
        current_role = user_info.get("role", "user")
        db_user = crud.get_user_by_email(db, user_info["email"])
        if db_user:
            current_user_id = db_user.id
    # Fetch historical data fro this specific item to check for anomalies
    historical_prices = db.query(models.PriceEntry.price).join(models.Item).filter(models.Item.name == submission.item_name).filter(models.PriceEntry.status == "APPROVED").all()
    # Convert SQL results to a simple list of numbers
    price_list = [p[0] for p in historical_prices]
    #ML logic to check if the new price is a "FAKE" or "EXTREME" outlier
    is_anomaly = ml_engine.detect_anomaly(submission.price,price_list)
    status = "FLAGGED" if is_anomaly else "APPROVED"
    ''' Saves the submission to the DB
    User ID is now passed dynamically through the endpoint '''
    return crud.create_price_submission(db,submission, user_id = current_user_id,role=current_role,status=status)

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
        # return {"message": "Insufficient data for forecast"}
        new_predictions = process_single_task(item_id,district,fast_mode=True,use_db=True)
    
        if not new_predictions:
            return {"message": "Insufficient data for forecast"}
    
                # Save newly generated predictions to the database                   
        for p_data in new_predictions:                                       
            new_forecast = models.Forecast(**p_data)                         
            db.add(new_forecast)                                             
        db.commit()                                                           
        # Fetch the newly saved predictions from the database to continue the flow                                                                           
        predictions = db.query(models.Forecast).filter(                      
            models.Forecast.item_id == item_id,                              
            models.Forecast.district == district                             
        ).order_by(models.Forecast.target_date.asc()).all()

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
