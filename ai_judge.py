import os
import json
import google.generativeai as genai

def inicializar_ia():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ADVERTENCIA: GEMINI_API_KEY no encontrada en el entorno.")
        return
    genai.configure(api_key=api_key)

def evaluar_sintesis_logica(bounty_title: str, bounty_desc: str, sintesis_text: str) -> dict:
    inicializar_ia()
    
    # OBLIGAMOS A GEMINI A HABLAR SOLO EN JSON NATIVO
    # CAMBIAMOS A FLASH: Más rápido, siempre disponible en Free Tier, y sin bloqueos 404.
    model = genai.GenerativeModel(
        'gemini-1.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )
    
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
        response = model.generate_content(prompt_sistema)
        # Como forzamos application/json, ya no hay que limpiar Markdown
        return json.loads(response.text)
        
    except Exception as e:
        print(f"Falla en el procesamiento cognitivo de la IA: {e}")
        return {
            "decision": "REJECTED",
            "reasoning": "Fallo interno de telemetría en el motor de inferencia. El juez está fuera de línea."
        }