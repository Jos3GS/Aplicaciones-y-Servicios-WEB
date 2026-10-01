from sqlalchemy import select
from sqlalchemy.orm import Session
from models.mediciones import Mediciones
from schemas.mediciones import MedicionesCreate, MedicionesUpdate

def get_all(db: Session) -> list[Mediciones]:
    return list(db.scalars(select(Mediciones).order_by(Mediciones.id)).all())

def get(db: Session, id: int) -> Mediciones | None:
    return db.get(Mediciones, id)

def create(db: Session, data: MedicionesCreate) -> Mediciones:
    medicion = Mediciones(**data.model_dump())
    db.add(medicion)
    db.commit()
    db.refresh(medicion)
    return medicion

def update(db: Session, medicion: Mediciones, data: MedicionesUpdate) -> Mediciones:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(medicion, field, value)
    db.commit()
    db.refresh(medicion)
    return medicion

def delete(db: Session, medicion: Mediciones) -> None:
    db.delete(medicion)
    db.commit()

