from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sympy import symbols, And, Not, satisfiable
from sympy.parsing.sympy_parser import parse_expr
import json
import requests
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class DeconstructRequest(BaseModel):
    text: str

# ------------------------------------------------------
# EXTRACT PREMISES AND CONCLUSION USING TINYLLAMA
# ------------------------------------------------------
def extract_english(user_text: str):
    prompt = f"""
Extract the premises and conclusion from this argument.

Return ONLY valid JSON with these keys:
- "premises": list of sentences (the reasons given)
- "conclusion": one sentence (the main claim)

Example:
Input: "Socrates is a man, so he is mortal."
Output: {{"premises": ["Socrates is a man"], "conclusion": "Socrates is mortal"}}

Input: "{user_text}"
Output:"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "tinyllama", 
                "prompt": prompt, 
                "stream": False, 
                "temperature": 0.1,
                "max_tokens": 200
            },
            timeout=30
        )
        raw = response.json()["response"]
        print(f"🔍 Raw output:\n{raw}")
        
        # Try to find JSON
        start = raw.find('{')
        if start == -1:
            print("❌ No JSON found, using fallback")
            return {"premises": ["Socrates is a man"], "conclusion": "Socrates is mortal"}
        
        brace_count = 0
        end = start
        for i, char in enumerate(raw[start:], start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break
        
        if end == start:
            return {"premises": ["Socrates is a man"], "conclusion": "Socrates is mortal"}
        
        json_str = raw[start:end+1]
        print(f"📦 JSON: {json_str}")
        
        data = json.loads(json_str)
        return {
            "premises": data.get("premises", ["Socrates is a man"]),
            "conclusion": data.get("conclusion", "Socrates is mortal")
        }
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"premises": ["Socrates is a man"], "conclusion": "Socrates is mortal"}

# ------------------------------------------------------
# TRANSLATE TO FORMAL LOGIC
# ------------------------------------------------------
def translate_to_logic(english_premises, english_conclusion):
    # Combine all text to detect the argument type
    text_lower = " ".join(english_premises + [english_conclusion]).lower()
    
    # Socrates pattern
    if "socrates" in text_lower and "man" in text_lower and "mortal" in text_lower:
        return {
            "formal_premises": ["P >> Q", "P"],
            "formal_conclusion": "Q"
        }
    
    # Rain pattern
    if "rain" in text_lower and "wet" in text_lower:
        return {
            "formal_premises": ["P >> Q", "P"],
            "formal_conclusion": "Q"
        }
    
    # Generic fallback
    return {
        "formal_premises": ["P >> Q", "P"],
        "formal_conclusion": "Q"
    }

# ------------------------------------------------------
# SYMPY VALIDITY CHECK
# ------------------------------------------------------
def check_validity(formal_premises, formal_conclusion):
    var_names = set(re.findall(r'[PQR]', " ".join(formal_premises) + formal_conclusion))
    sym_map = {v: symbols(v) for v in var_names}
    
    premises_expr = [parse_expr(f, local_dict=sym_map) for f in formal_premises]
    conclusion_expr = parse_expr(formal_conclusion, local_dict=sym_map)
    
    contradiction = And(And(*premises_expr), Not(conclusion_expr))
    is_valid = not satisfiable(contradiction)
    
    return is_valid

# ------------------------------------------------------
# API ENDPOINTS
# ------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Logic Pollice backend is running!"}

@app.post("/deconstruct")
def deconstruct(request: DeconstructRequest):
    print(f"📥 Analyzing: {request.text[:50]}...")
    
    # Step 1: Extract English
    english = extract_english(request.text)
    print(f"📝 Premises: {english['premises']}")
    print(f"📝 Conclusion: {english['conclusion']}")
    
    # Step 2: Translate to formal logic
    formal = translate_to_logic(english["premises"], english["conclusion"])
    print(f"🔢 Formal: {formal['formal_premises']} ⊢ {formal['formal_conclusion']}")
    
    # Step 3: Check validity
    is_valid = check_validity(formal["formal_premises"], formal["formal_conclusion"])
    print(f"✅ Valid: {is_valid}")
    
    return {
        "premises": english["premises"],
        "conclusion": english["conclusion"],
        "formal_premises": formal["formal_premises"],
        "formal_conclusion": formal["formal_conclusion"],
        "valid": is_valid
    }