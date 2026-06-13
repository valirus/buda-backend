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
    """
    Evalúa si un argumento merece la liberación de los fondos del contrato.
    Retorna un diccionario con 'decision' (APPROVED/REJECTED) y 'reasoning'.
    """
    inicializar_ia()
    
    # Usamos el modelo Pro para máximo rigor lógico
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    prompt_sistema = f"""
    Actúa como un juez lógico implacable y experto en teoría de sistemas complejos.
    Se ha ofrecido una recompensa financiera para quien resuelva el siguiente problema (Bounty):
    
    TÍTULO DEL PROBLEMA: {bounty_title}
    CONDICIONES: {bounty_desc}

    Un agente del sistema ha propuesto la siguiente síntesis/solución para reclamar el dinero:
    
    ARGUMENTO DEL AGENTE: {sintesis_text}

    Tu tarea es evaluar la solidez de este argumento. Detecta falacias, falta de evidencia o si es simplemente "texto basura" (ej. "hola mundo") intentando robar los fondos.
    ¿El argumento aborda y resuelve genuinamente las condiciones del problema?

    Debes responder ÚNICAMENTE con un JSON válido y estricto, sin texto adicional, con esta estructura:
    {{
        "decision": "APPROVED" o "REJECTED",
        "reasoning": "Tu explicación lógica y analítica en máximo 3 líneas."
    }}
    """
    
    try:
        response = model.generate_content(prompt_sistema)
        texto_crudo = response.text.strip()
        
        # Limpieza por si el modelo envuelve el JSON en bloques de código Markdown
        if texto_crudo.startswith("```json"):
            texto_crudo = texto_crudo[7:-3].strip()
        elif texto_crudo.startswith("```"):
            texto_crudo = texto_crudo[3:-3].strip()
            
        resultado = json.loads(texto_crudo)
        return resultado
        
    except Exception as e:
        print(f"Falla en el procesamiento cognitivo de la IA: {e}")
        # Por seguridad financiera, si la IA falla, rechazamos la transacción
        return {
            "decision": "REJECTED",
            "reasoning": "Fallo interno de telemetría en el motor de inferencia. Intenta de nuevo."
        }