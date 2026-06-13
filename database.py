import os
import psycopg2
from neo4j import GraphDatabase
from dotenv import load_dotenv
import uuid
from datetime import datetime

# Cargar las credenciales ocultas
load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.pg_conn = None
        self.neo4j_driver = None

    def connect_postgres(self):
        try:
            self.pg_conn = psycopg2.connect(
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT"),
                dbname=os.getenv("PG_DB"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD")
            )
            return "PostgreSQL Conectado."
        except Exception as e:
            return f"Error en PostgreSQL: {e}"

    def connect_neo4j(self):
        try:
            uri = os.getenv("NEO4J_URI")
            user = os.getenv("NEO4J_USER")
            password = os.getenv("NEO4J_PASSWORD")
            self.neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
            # Verificamos la conexión
            self.neo4j_driver.verify_connectivity()
            return "Neo4j Conectado."
        except Exception as e:
            return f"Error en Neo4j: {e}"
        
    def _ensure_pg_connection(self):
        # 1. Si no hay conexión o se cerró explícitamente
        if self.pg_conn is None or self.pg_conn.closed != 0:
            self.connect_postgres()
        else:
            # 2. Hacemos un ping silencioso. Si Neon cortó el cable por inactividad, fallará y reconectamos.
            try:
                cur = self.pg_conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
            except Exception:
                print("Reconectando a PostgreSQL (Cable cortado por inactividad)...")
                self.connect_postgres()
    
    def registrar_usuario(self, username: str, email: str, password_hash: str):
        try:
            self._ensure_pg_connection()
            cursor = self.pg_conn.cursor()
            # Usamos el esquema que ya definiste en schema_relacional.sql
            query = """
            INSERT INTO Users (username, email, password_hash)
            VALUES (%s, %s, %s) RETURNING user_id, username;
            """
            cursor.execute(query, (username, email, password_hash))
            user = cursor.fetchone()
            self.pg_conn.commit()
            cursor.close()
            return {"user_id": str(user[0]), "username": user[1]}
        except Exception as e:
            self.pg_conn.rollback() # Vital: deshacer si hay error (ej. usuario duplicado)
            print(f"Error al registrar usuario en Postgres: {e}")
            return None

    def obtener_usuario_por_username(self, username: str):
        try:
            self._ensure_pg_connection()
            cursor = self.pg_conn.cursor()
            query = "SELECT user_id, username, password_hash FROM Users WHERE username = %s;"
            cursor.execute(query, (username,))
            user = cursor.fetchone()
            cursor.close()
            
            if user:
                # Devolvemos un diccionario fácil de leer para main.py
                return {"user_id": str(user[0]), "username": user[1], "password_hash": user[2]}
            return None
        except Exception as e:
            print(f"Error al buscar usuario en Postgres: {e}")
            return None
        
    def obtener_stats_usuario(self, user_id: str):
        try:
            self._ensure_pg_connection()
            cursor = self.pg_conn.cursor()
            query = "SELECT wallet_balance, cognitive_score FROM Users WHERE user_id = %s;"
            cursor.execute(query, (user_id,))
            stats = cursor.fetchone()
            cursor.close()
            
            if stats:
                return {
                    "wallet_balance": float(stats[0]), 
                    "cognitive_score": float(stats[1])
                }
            return None
        except Exception as e:
            print(f"Error al leer estadísticas en Postgres: {e}")
            return None
        
    def crear_nodo_premisa(self, user_id: str, premise: str, evidence_link: str = None):
        # Generamos un ID único universal para este argumento y la hora exacta
        node_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Cypher: Si el usuario no existe, lo crea (MERGE). Luego crea la idea (CREATE) 
        # y finalmente dibuja la flecha (relación) de que el usuario POSTEÓ la idea.
        query = """
        MERGE (u:User {user_id: $user_id})
        CREATE (n:NodeA {
            node_id: $node_id, 
            text: $premise, 
            evidence_link: $evidence_link, 
            created_at: $timestamp,
            state: 'OPEN'
        })
        CREATE (u)-[:POSTED]->(n)
        RETURN n.node_id AS node_id
        """
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(
                    query, 
                    user_id=user_id, 
                    node_id=node_id, 
                    premise=premise, 
                    evidence_link=evidence_link, 
                    timestamp=timestamp
                )
                record = result.single()
                return record["node_id"]
        except Exception as e:
            print(f"Error al escribir en el grafo: {e}")
            return None
        
    def obtener_mapa_debate(self, root_id: str = None, depth: int = 3):
        if not root_id:

            # CONSULTA MACRO: Inyectamos la extracción del link empírico
            query = """
            MATCH (n:NodeA)
            OPTIONAL MATCH (b:Bounty)-[:SEEKS_SOLUTION]->(n)
            WITH n, collect(DISTINCT b.bounty_id) AS bounty_ids
            WITH collect(DISTINCT {id: n.node_id, text: n.text, created_at: n.created_at, bounties: bounty_ids, evidence_link: n.evidence_link}) AS nodes
            OPTIONAL MATCH (a:NodeA)-[r]->(b:NodeA)
            WITH nodes, collect(DISTINCT {source: a.node_id, target: b.node_id, type: type(r)}) AS links
            RETURN nodes, links
            """
            params = {}
        else:
            # VECINDAD TOPOLÓGICA: Hacemos lo mismo para el árbol seleccionado
            query = """
            MATCH (root:NodeA {node_id: $root_id})
            OPTIONAL MATCH path = (root)-[*..%d]-(n:NodeA)
            WITH root, collect(DISTINCT n) + root AS total_nodes
            UNWIND total_nodes AS n
            WITH DISTINCT n AS unique_nodes
            OPTIONAL MATCH (b:Bounty)-[:SEEKS_SOLUTION]->(unique_nodes)
            WITH unique_nodes, collect(DISTINCT b.bounty_id) AS bounty_ids
            WITH collect({id: unique_nodes.node_id, text: unique_nodes.text, created_at: unique_nodes.created_at, bounties: bounty_ids, evidence_link: unique_nodes.evidence_link}) AS nodes
            OPTIONAL MATCH (a:NodeA)-[r]->(b:NodeA)
            WHERE a.node_id IN [x IN nodes | x.id] AND b.node_id IN [x IN nodes | x.id]
            WITH nodes, collect(DISTINCT {source: a.node_id, target: b.node_id, type: type(r)}) AS links
            RETURN nodes, links
            """ % depth
            params = {"root_id": root_id}
            
            
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, **params)
                record = result.single()
                
                if not record:
                    return {"nodes": [], "links": []}
                    
                # Filtramos enlaces rotos o huérfanos
                links = [link for link in record["links"] if link["source"] is not None]
                
                return {
                    "nodes": record["nodes"],
                    "links": links
                }
        except Exception as e:
            print(f"Error en la extracción topológica del grafo: {e}")
            return None
    
    def crear_interaccion(self, user_id: str, parent_node_id: str, text: str, relation_type: str, evidence_link: str = None):
        # 1. Validamos que el tipo de relación sea legítimo para evitar hackeos
        relaciones_permitidas = ['SUPPORTS', 'REFUTES', 'SYNTHESIZES']
        if relation_type not in relaciones_permitidas:
            print("Intento de inyección o tipo de relación inválida.")
            return None

        node_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # 2. Cypher: Buscamos el nodo padre, creamos el nodo hijo y trazamos 
        # la flecha de relación matemática entre ambos.
        query = f"""
        MATCH (parent:NodeA {{node_id: $parent_node_id}})
        MERGE (u:User {{user_id: $user_id}})
        CREATE (n:NodeA {{
            node_id: $node_id, 
            text: $text, 
            evidence_link: $evidence_link, 
            created_at: $timestamp,
            state: 'OPEN'
        }})
        CREATE (u)-[:POSTED]->(n)
        CREATE (n)-[:{relation_type}]->(parent)
        RETURN n.node_id AS node_id
        """
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(
                    query, 
                    user_id=user_id,
                    parent_node_id=parent_node_id,
                    node_id=node_id, 
                    text=text, 
                    evidence_link=evidence_link, 
                    timestamp=timestamp
                )
                record = result.single()
                # Si record es None, significa que el parent_node_id no existía
                return record["node_id"] if record else None
        except Exception as e:
            print(f"Error en la fricción cognitiva: {e}")
            return None

    def close_all(self):
        if self.pg_conn:
            self.pg_conn.close()
        if self.neo4j_driver:
            self.neo4j_driver.close()

    def crear_bounty(self, title: str, description: str, reward_amount: float, deadline: str):
        try:
            self._ensure_pg_connection()
            # Abrimos el cursor para hablar con PostgreSQL
            cursor = self.pg_conn.cursor()
            
            # 1. Buscamos al primer sponsor disponible (nuestro Inversor Cero)
            cursor.execute("SELECT sponsor_id FROM Sponsors LIMIT 1;")
            sponsor = cursor.fetchone()
            
            if not sponsor:
                print("Error: No hay Sponsors registrados en el sistema.")
                return None
                
            sponsor_id = sponsor[0]
            
            # 2. Preparamos la inyección del Bounty
            query = """
            INSERT INTO Bounties (sponsor_id, title, description, reward_amount, deadline)
            VALUES (%s, %s, %s, %s, %s) RETURNING bounty_id;
            """
            
            # Ejecutamos pasando los parámetros de forma segura (para evitar SQL Injection)
            cursor.execute(query, (sponsor_id, title, description, reward_amount, deadline))
            
            # Capturamos el ID del Bounty recién creado
            nuevo_bounty_id = cursor.fetchone()[0]
            
            # 3. CONFIRMAMOS LA TRANSACCIÓN (Sin esto, no se guarda nada en SQL)
            self.pg_conn.commit()
            cursor.close()
            
            return nuevo_bounty_id
            
        except Exception as e:
            # Si algo falla (ej. letras en lugar de números), deshacemos todo
            self.pg_conn.rollback()
            print(f"Error en transacción SQL (Bounty): {e}")
            return None
        
    def vincular_bounty_a_nodo(self, bounty_id: str, node_id: str):
        # Cypher: Buscamos la premisa, creamos el nodo del Bounty 
        # y trazamos la flecha que indica que este dinero busca solucionar este problema.
        query = """
        MATCH (n:NodeA {node_id: $node_id})
        MERGE (b:Bounty {bounty_id: $bounty_id})
        MERGE (b)-[:SEEKS_SOLUTION]->(n)
        RETURN b.bounty_id AS bounty_id
        """
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, bounty_id=bounty_id, node_id=node_id)
                record = result.single()
                return record["bounty_id"] if record else None
        except Exception as e:
            print(f"Error inyectando el Bounty en el grafo: {e}")
            return None
        
    def resolver_bounty(self, bounty_id: str, winner_user_id: str, synthesis_node_id: str):
        try:
            self._ensure_pg_connection()
            cursor = self.pg_conn.cursor()
            
            # 1. Verificamos que el Bounty exista y siga abierto
            cursor.execute("SELECT reward_amount, status FROM Bounties WHERE bounty_id = %s;", (bounty_id,))
            bounty = cursor.fetchone()
            
            if not bounty or bounty[1] != 'OPEN':
                print("El Bounty no existe o ya fue resuelto.")
                return False
                
            reward = bounty[0]
            
            # 2. Cerramos el contrato del Bounty
            cursor.execute("""
                UPDATE Bounties 
                SET status = 'SOLVED', synthesis_node_id = %s 
                WHERE bounty_id = %s;
            """, (synthesis_node_id, bounty_id))
            
            # 3. Transferimos los fondos usando el UUID correcto (user_id en lugar de username)
            cursor.execute("""
                UPDATE Users 
                SET wallet_balance = wallet_balance + %s, cognitive_score = cognitive_score + 10
                WHERE user_id = %s;
            """, (reward, winner_user_id))
            
            # 4. Registramos la transacción para la auditoría (ahora incluyendo al ganador)
            cursor.execute("""
                INSERT INTO Transactions (bounty_id, user_id, amount, transaction_type)
                VALUES (%s, %s, %s, 'BOUNTY_PAYOUT');
            """, (bounty_id, winner_user_id, reward))
            
            # EL GOLPE DE MARTILLO: Confirmamos los cambios
            self.pg_conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            self.pg_conn.rollback() # Si algo falla, nadie pierde dinero
            print(f"Error en el pago del Bounty: {e}")
            return False

# Instancia global para usar en toda la API
db = DatabaseManager()