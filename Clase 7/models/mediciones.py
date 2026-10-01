from datetime import datetime

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class Mediciones(Base):
    __tablename__ = "mediciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    estudiante_id: Mapped[int] = mapped_column(Integer, ForeignKey("estudiantes.id"), nullable=False)
    variable: Mapped[str] = mapped_column(String(50), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
