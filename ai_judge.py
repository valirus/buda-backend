import os
import json
from google import genai
from google.genai import types

def evaluar_sintesis_logica(bounty_title: str, bounty_desc: str, sintesis_text: str) -> dict:
    # 1. Cargamos la llave directamente al inicializar el nuevo cliente
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR CRÍTICO: GEMINI_API_KEY no encontrada.")
        return {"decision": "REJECTED", "reasoning": "El Córtex está desconectado (Falta API Key)."}
        
    client = genai.Client(api_key=api_key)
    
    prompt_sistema = f"""
    Actúa como un juez lógico implacable. Se ha ofrecido una recompensa financiera para resolver este problema:
    TÍTULO: {bounty_title}
    CONDICIONES: {bounty_desc}

    Un agente ha propuesto esta solución para cobrar el dinero:
    ARGUMENTO: {sintesis_text}

    Tu tarea es evaluar la solidez. Si el usuario intenta robar el dinero con texto sin sentido (ej. "dame el dinero"), debes RECHAZARLO sin piedad.
    
    Responde ESTRICTAMENTE con esta estructura JSON:
    {{
        "decision": "APPROVED" o "REJECTED",
        "reasoning": "Explicación directa, fría y analítica de por qué apruebas o rechazas el argumento."
    }}
    """
    
    try:
        # 2. Llamada nativa del nuevo SDK de Google
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt_sistema,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
        
    except Exception as e:
        print(f"Falla en el procesamiento cognitivo de la IA: {e}")
        return {
            "decision": "REJECTED",
            "reasoning": "Fallo interno de telemetría en el motor de inferencia. El juez está fuera de línea."
        }