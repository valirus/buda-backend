from datetime import datetime
from pydantic import BaseModel
from typing import Optional

class NodoPremisa(BaseModel):  # Por ahora usaremos un texto simple hasta integrar el login real
    premise: str  # El argumento o idea central
    evidence_link: Optional[str] = None  # Un link opcional para respaldar la idea
    
class NodoInteraccion(BaseModel):
    parent_node_id: str  # El ID de la idea que estamos respondiendo
    text: str            # El argumento de respuesta
    relation_type: str   # SOLO puede ser: 'SUPPORTS', 'REFUTES' o 'SYNTHESIZES'
    evidence_link: Optional[str] = None

class BountyCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    deadline: datetime

class VincularBounty(BaseModel):
    bounty_id: str
    node_id: str

class ReclamarBounty(BaseModel):
    bounty_id: str
    target_node_id: str # El problema raíz que está sintetizando
    synthesis_text: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str