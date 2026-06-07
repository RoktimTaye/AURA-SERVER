from sqlalchemy.orm import Session
from typing import Optional
from . import models, schemas
from passlib.context import CryptContext
from sqlalchemy import or_

pwd_context = CryptContext(schemes=['pbkdf2_sha256'],
                           deprecated='auto')

def get_user_by_email(db:Session,email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db:Session, user: schemas.UserCreate):
    safe_password = user.password[:72]
    # hashed_password = pwd_context.hash(user.password)
    hashed_password = pwd_context.hash(safe_password)
    # db_user = models.User(email=user.email,hashed_password=hashed_password,role=user.role)
    db_user = models.User(email=user.email,full_name=user.full_name,hashed_password=hashed_password,role=user.role)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def verify_password(plain_password,hashed_passowrd):
    return pwd_context.verify(plain_password,hashed_passowrd)

def get_or_create_item(db: Session, item_name: str) -> models.Item:
    """Finds an item by name, or creates it if it doesn't exist."""
    item = db.query(models.Item).filter(models.Item.name == item_name).first()
    if not item:
        item = models.Item(name=item_name)
        db.add(item)
        db.commit()
        db.refresh(item)
    return item

def get_or_create_location(db: Session, location_name: str, district: str = None, state: str = None) -> models.Location:  # ty:ignore[invalid-parameter-default]
    """Finds a location by name, district, and state, or creates it if it doesn't exist."""
    query = db.query(models.Location).filter(models.Location.name == location_name)
    if district:
        query = query.filter(models.Location.district == district)
    if state:
        query = query.filter(models.Location.state == state)
    
    location = query.first()
    
    if not location:
        location = models.Location(name=location_name, district=district, state=state)
        db.add(location)
        db.commit()
        db.refresh(location)
    return location

def get_directory_data(db: Session, search_item: Optional[str] = None, search_district: Optional[str] = None, limit: int =100,offset: int = 0, is_admin: bool = False):
    # 1. Define the columns we want to select
    query = db.query(
        models.PriceEntry.id,
        models.Item.name.label("item_name"),
        models.Item.unit,
        models.PriceEntry.price.label("price_modal"),
        models.Location.district,
        models.Location.name.label("market_name"),
        models.PriceEntry.votes,
        models.PriceEntry.status,
        models.PriceEntry.timestamp,
        models.PriceEntry.item_id
    ).join(models.Item).join(models.Location)

    # 2. Apply base filters
    if not is_admin:
        query = query.filter(models.PriceEntry.status == "APPROVED")

    # 3. Apply optional search filters with trimming for robustness
    if search_item and search_item.strip():
        query = query.filter(models.Item.name.ilike(f"%{search_item.strip()}%"))
    if search_district and search_district.strip():
        query = query.filter(
            or_(
                models.Location.district.ilike(f"%{search_district.strip()}%"),
                models.Location.name.ilike(f"%{search_district.strip()}%")
            )
        )

    # 4. Get total count before applying limit/offset
    total_count = query.count()

    # 5. Determine Deterministic Sort Order (The Tie-Breaker)
    # We always include id.desc() to ensure the order never changes for identical votes
    if search_item or search_district:
        order = [models.PriceEntry.votes.desc(), models.PriceEntry.id.desc()]
    else:
        order = [models.PriceEntry.timestamp.desc(), models.PriceEntry.id.desc()]

    # 6. Get paginated results with the chosen order
    # Applying order_by with multiple columns for stability
    return query.order_by(*order).offset(offset).limit(limit).all(), total_count

def create_price_submission(db: Session, submission: schemas.PriceCreate, user_id: Optional[int] = None, role: str = "user", status: str = "APPROVED"):
    # The logic is now instantly readable thanks to the helper functions
    db_item = get_or_create_item(db, submission.item_name)
    db_loc = get_or_create_location(
        db, 
        submission.location_name, 
        district=submission.district, 
        state=submission.state
    )

    # Create the new price entry linking everything together
    db_entry = models.PriceEntry(
        item_id=db_item.id,
        location_id=db_loc.id,
        user_id=user_id,
        role=role,
        price=submission.price,
        distance_miles=submission.distance_miles,
        status=status
    )
    
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    
    return db_entry

def update_entry_vote(db: Session, entry_id: int, increment: bool = True):
    db_entry = db.query(models.PriceEntry).filter(models.PriceEntry.id == entry_id).first()
    
    if db_entry:
        if increment:
            db_entry.votes += 1
        else:
            db_entry.votes -= 1
            
        # FIX: Added commit and refresh so the vote actually saves to the database
        db.commit()
        db.refresh(db_entry)
        
    return db_entry
    
def delete_entry(db: Session, entry_id: int):
    db_entry = db.query(models.PriceEntry).filter(models.PriceEntry.id == entry_id).first()
    
    if db_entry:
        db.delete(db_entry)
        db.commit()
        return True
        
    return False

def update_entry_status(db: Session, entry_id: int, status: str):
    db_entry = db.query(models.PriceEntry).filter(models.PriceEntry.id == entry_id).first()
    
    if db_entry:
        db_entry.status = status  # ty:ignore[invalid-assignment]
        db.commit()
        db.refresh(db_entry)
        
    return db_entry

def update_entry(db: Session, entry_id: int, update_data: schemas.PriceUpdate):
    db_entry = db.query(models.PriceEntry).filter(models.PriceEntry.id == entry_id).first()
    if not db_entry:
        return None

    if update_data.price is not None:
        db_entry.price = update_data.price  # ty:ignore[invalid-assignment]
        
    if update_data.item_name is not None and update_data.item_name.strip():
        item = get_or_create_item(db, update_data.item_name.strip())
        db_entry.item_id = item.id

    if update_data.location_name is not None and update_data.location_name.strip():
        existing_loc = db.query(models.Location).filter(models.Location.id == db_entry.location_id).first()
        if existing_loc:
            location = get_or_create_location(db, update_data.location_name.strip(), existing_loc.district, existing_loc.state)  # ty:ignore[invalid-argument-type]
            db_entry.location_id = location.id

    db.commit()
    db.refresh(db_entry)
    return db_entry
