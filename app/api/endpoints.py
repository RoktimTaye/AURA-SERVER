from fastapi import APIRouter, Depends,HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..import crud,schemas,models
from ..ml import engine as ml_engine

router = APIRouter()

@router.get("/directory", response_model=List[schemas.DirectoryView])
def read_directory(district: str = None, item: str = None, db: Session= Depends(get_db)):  # ty:ignore[invalid-parameter-default]
    data = crud.get_directory_data(db,search_item=item,search_area=district)
    
    formatted_data = []
    for entry in data:
        formatted_data.append({
            "id":entry.id,
            "item_name":entry.item_name,
            "price_display": f"{int(entry.min_price)}-{int(entry.max_price)} /{entry.unit}",
            "range_miles":entry.range_miles,
            "area": entry.area,
            "votes": entry.votes
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

@router.get("/forcast/{item_id}")
def get_item_forcast(item_id: int,db: Session = Depends(get_db)):
    prices = db.query(
        models.PriceEntry.price,
        models.PriceEntry.timestamp
        ).filter(models.PriceEntry.item_id == item_id).filter(models.PriceEntry.status == "APPROVED").all()
    
    prediction = ml_engine.generate_forcast(prices)
    
    return {"item_id": item_id, "prediction": prediction}

@router.delete("/admin/entry/{entry_id}")
def admin_delete(entry_id:int, db:Session = Depends(get_db)):
    #Completely removes bad entry from the database
    sucess = crud.delete_entry(db,entry_id)
    if not sucess:
        raise HTTPException(status_code=404,detail="Entry not found")
    return {"message": "Deleted sucessfully"}
