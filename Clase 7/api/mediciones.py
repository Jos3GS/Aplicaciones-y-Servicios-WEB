from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from crud import medicion as crud
from database import get_db
from schemas.mediciones import MedicionesCreate, MedicionesResponse, MedicionesUpdate

router = APIRouter(prefix="/mediciones", tags=["Mediciones"])

@router.get("", response_model=list[MedicionesResponse])
def listar_mediciones(db: Session = Depends(get_db)):
    return crud.get_all(db)

@router.get("/{id}", response_model=MedicionesResponse)
def obtener_medicion(id: int, db: Session = Depends(get_db)):
    medicion = crud.get(db, id)
    if medicion is None:
        raise HTTPException(status_code=404, detail="La medición no existe")
    return medicion

@router.post("", response_model=MedicionesResponse, status_code=status.HTTP_201_CREATED)
def agregar_medicion(data: MedicionesCreate, db: Session = Depends(get_db)):
    return crud.create(db, data)

@router.put("/{id}", response_model=MedicionesResponse)
def reemplazar_medicion(id: int, data: MedicionesCreate, db: Session = Depends(get_db)):
    medicion = crud.get(db, id)
    if medicion is None:
        raise HTTPException(status_code=404, detail="La medición no existe")
    return crud.update(db, medicion, MedicionesUpdate(**data.model_dump()))

@router.patch("/{id}", response_model=MedicionesResponse)
def actualizar_medicion(id: int, data: MedicionesUpdate, db: Session = Depends(get_db)):
    medicion = crud.get(db, id)
    if medicion is None:
        raise HTTPException(status_code=404, detail="La medición no existe")
    return crud.update(db, medicion, data)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_medicion(id: int, db: Session = Depends(get_db)):
    medicion = crud.get(db, id)
    if medicion is None:
        raise HTTPException(status_code=404, detail="La medición no existe")
    crud.delete(db, medicion)
