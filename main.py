from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import Optional
from database import db
from models import NodoPremisa, NodoInteraccion, BountyCreate, VincularBounty, ReclamarBounty, UserCreate, UserLogin
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt
import jwt
from datetime import datetime, timedelta

app = FastAPI(title="MVP Anti-Polarización (Proyecto Buda)", version="0.1.0")

# --- CONFIGURACIÓN JWT Y CORS ---
SECRET_KEY = "Firma_Criptografica_Ultra_Secreta_Buda" # En producción, esto va en un .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # El token dura 1 semana



# Configuramos CORS para permitir que el frontend hable con el backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # <-- CAMBIO CRÍTICO: Apertura de la frontera
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# --- FUNCIONES DE SEGURIDAD ---
def crear_token_acceso(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

@app.on_event("startup")
def startup_db_client():
    print("Encendiendo motores...")
    # Ahora la conexión ocurre OBLIGATORIAMENTE al arrancar el servidor
    pg_status = db.connect_postgres()
    neo4j_status = db.connect_neo4j()
    print(f"Estado SQL: {pg_status}")
    print(f"Estado Grafo: {neo4j_status}")

@app.on_event("shutdown")
def shutdown_db_client():
    db.close_all()
    print("Conexiones cerradas de forma segura.")

@app.get("/")
def read_root():
    return {
        "estado": "El sistema central está en línea y conectado."
    }

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Mantiene la línea abierta
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/nodos/desplegar")
def desplegar_premisa(nodo: NodoPremisa):
    nuevo_node_id = db.crear_nodo_premisa(
        user_id=nodo.user_id, 
        premise=nodo.premise, 
        evidence_link=nodo.evidence_link
    )
    
    if not nuevo_node_id:
        return {"error": "Fallo la inyección en la red neuronal de ideas."}
        
    return {
        "status": "Premisa anclada exitosamente en el sistema", 
        "node_id": nuevo_node_id, 
        "premise": nodo.premise
    }

@app.post("/nodos/interactuar")
async def interactuar_con_premisa(interaccion: NodoInteraccion, user_id: str = Depends(verificar_token)):
    nuevo_node_id = db.crear_interaccion(
        user_id=user_id, parent_node_id=interaccion.parent_node_id, text=interaccion.text, relation_type=interaccion.relation_type, evidence_link=interaccion.evidence_link
    )
    if not nuevo_node_id: return {"error": "Fallo la interacción."}
    
    await manager.broadcast("UPDATE_MATRIX") # <-- EL GRITO AL FRONTEND
    return {"status": "Choque registrado", "node_id": nuevo_node_id}


@app.get("/nodos/mapa")
def obtener_mapa_fractal(root_id: Optional[str] = None, depth: int = 3):
    # Pasamos los parámetros opcionales directamente al gestor de base de datos
    mapa = db.obtener_mapa_debate(root_id=root_id, depth=depth)
    
    if not mapa:
        return {"error": "No se pudo extraer el segmento del árbol de debate."}
        
    return mapa

@app.post("/bounties/crear")
def lanzar_bounty(bounty: BountyCreate):
    nuevo_id = db.crear_bounty(
        title=bounty.title,
        description=bounty.description,
        reward_amount=bounty.reward_amount,
        deadline=bounty.deadline.isoformat()
    )
    
    if not nuevo_id:
        return {"error": "Fallo la transacción. El capital no pudo ser bloqueado en el sistema."}
        
    return {
        "status": "Contrato de consenso fondeado y activo",
        "bounty_id": nuevo_id,
        "reward": f"${bounty.reward_amount} USD"
    }

@app.get("/bounties/{bounty_id}")
def obtener_detalles_bounty(bounty_id: str):
    # Conectamos con Postgres y buscamos el contrato
    try:
        db._ensure_pg_connection()
        cursor = db.pg_conn.cursor()
        
        # Traemos el título, descripción y el dinero
        cursor.execute("""
            SELECT title, description, reward_amount, status 
            FROM Bounties 
            WHERE bounty_id = %s;
        """, (bounty_id,))
        
        bounty = cursor.fetchone()
        cursor.close()
        
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty no encontrado")
            
        return {
            "title": bounty[0],
            "description": bounty[1],
            "reward_amount": float(bounty[2]),
            "status": bounty[3]
        }
    except Exception as e:
        print(f"Error buscando bounty: {e}")
        raise HTTPException(status_code=500, detail="Error interno")

@app.post("/bounties/vincular")
def enlazar_bounty_con_premisa(vinculo: VincularBounty):
    exito = db.vincular_bounty_a_nodo(vinculo.bounty_id, vinculo.node_id)
    
    if not exito:
        return {"error": "Fallo la sincronización. Verifica que el ID del nodo exista en el grafo."}
        
    return {
        "status": "Incentivo anclado a la idea. Que comience la fricción cognitiva.",
        "bounty_id": vinculo.bounty_id,
        "node_id": vinculo.node_id
    }


@app.post("/bounties/resolver")
async def reclamar_recompensa(reclamo: ReclamarBounty, user_id: str = Depends(verificar_token)):
    nuevo_node_id = db.crear_interaccion(user_id=user_id, parent_node_id=reclamo.target_node_id, text=reclamo.synthesis_text, relation_type="SYNTHESIZES")
    if not nuevo_node_id: return {"error": "El argumento falló."}
    
    pago_exitoso = db.resolver_bounty(bounty_id=reclamo.bounty_id, winner_user_id=user_id, synthesis_node_id=nuevo_node_id)
    if not pago_exitoso: return {"error": "Contrato rechazado."}
    
    await manager.broadcast("UPDATE_MATRIX") # <-- EL GRITO AL FRONTEND
    return {"status": "CONSENSO ALCANZADO"}


@app.post("/auth/register")
def registrar_cuenta(user: UserCreate):
    password_bytes = user.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_pwd = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    nuevo_usuario = db.registrar_usuario(user.username, user.email, hashed_pwd)
    if not nuevo_usuario:
        return {"error": "No se pudo crear la cuenta."}
        
    token = crear_token_acceso({"sub": nuevo_usuario["user_id"]})
    return {"access_token": token, "user": nuevo_usuario}


@app.post("/auth/login")
def iniciar_sesion(user: UserLogin):
    db_user = db.obtener_usuario_por_username(user.username)
    if not db_user or not bcrypt.checkpw(user.password.encode('utf-8'), db_user["password_hash"].encode('utf-8')):
        return {"error": "Credenciales inválidas."}
        
    token = crear_token_acceso({"sub": db_user["user_id"]})
    return {"access_token": token, "user_id": db_user["user_id"], "username": db_user["username"]}

@app.post("/nodos/premisa")
async def crear_raiz(premisa: NodoPremisa, user_id: str = Depends(verificar_token)):
    node_id = db.crear_nodo_premisa(user_id=user_id, premise=premisa.premise, evidence_link=premisa.evidence_link)
    if not node_id:
        return {"error": "Fallo al colisionar la idea en la Matrix."}
        
    await manager.broadcast("UPDATE_MATRIX") # <-- EL GRITO AL FRONTEND
    return {"mensaje": "Premisa inyectada", "node_id": node_id}


@app.get("/usuarios/{user_id}/stats")
def obtener_estadisticas_agente(user_id: str):
    stats = db.obtener_stats_usuario(user_id)
    
    if not stats:
        return {"error": "Agente no encontrado en los registros financieros."}
        
    return stats