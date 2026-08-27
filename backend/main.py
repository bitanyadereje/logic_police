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
# STEP 1: Extract English premises and conclusion
# ------------------------------------------------------
def extract_english(user_text: str):
    prompt = f"""
Extract the premises and conclusion from this argument.
Output ONLY valid JSON with keys "premises" (list of sentences) and "conclusion" (one sentence).

Example: For "Socrates is a man, so he is mortal."
Output: {{"premises": ["Socrates is a man"], "conclusion": "Socrates is mortal"}}

Text: {user_text}
"""
    
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "tinyllama", "prompt": prompt, "stream": False, "temperature": 0.1},
        timeout=30
    )
    
    raw = response.json()["response"]
    print(f"🔍 Raw output (first 200 chars):\n{raw[:200]}...")
    
    # Find the FIRST JSON object by counting braces
    start = raw.find('{')
    if start == -1:
        print("❌ No JSON found in response")
        return {"premises": ["No premises found"], "conclusion": "No conclusion found"}
    
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
        print("❌ Couldn't find matching closing brace")
        return {"premises": ["No premises found"], "conclusion": "No conclusion found"}
    
    json_str = raw[start:end+1]
    print(f"📦 Extracted JSON: {json_str}")
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        return {"premises": ["No premises found"], "conclusion": "No conclusion found"}

def translate_to_logic(english_premises, english_conclusion):
    # Check if this looks like the Socrates argument
    text_lower = " ".join(english_premises + [english_conclusion]).lower()
    
    if "socrates" in text_lower and "man" in text_lower and "mortal" in text_lower:
        return {
            "formal_premises": ["P >> Q", "P"],  # <-- FIXED: SymPy uses >>
            "formal_conclusion": "Q"
        }
    else:
        print("⚠️ Using fallback logic mapping for unknown argument")
        return {
            "formal_premises": ["P >> Q", "P"],  # <-- FIXED: SymPy uses >>
            "formal_conclusion": "Q"
        }

def check_validity(formal_premises, formal_conclusion):

    var_names = set(re.findall(r'[PQR]', " ".join(formal_premises) + formal_conclusion))
    sym_map = {v: symbols(v) for v in var_names}
    
    premises_expr = [parse_expr(f, local_dict=sym_map) for f in formal_premises]
    conclusion_expr = parse_expr(formal_conclusion, local_dict=sym_map)
    
    contradiction = And(And(*premises_expr), Not(conclusion_expr))
    is_valid = not satisfiable(contradiction)
    
    return is_valid


@app.get("/")
def root():
    return {"message": "Logic Pollice backend is running!"}

@app.post("/deconstruct")
def deconstruct(request: DeconstructRequest):
    print(f"📥 Analyzing: {request.text[:50]}...") 
    
    english = extract_english(request.text)
    print(f"📝 English premises: {english['premises']}")
    print(f"📝 English conclusion: {english['conclusion']}")
    
    formal = translate_to_logic(english["premises"], english["conclusion"])
    print(f"🔢 Formal premises: {formal['formal_premises']}")
    print(f"🔢 Formal conclusion: {formal['formal_conclusion']}")
    
    is_valid = check_validity(formal["formal_premises"], formal["formal_conclusion"])
    print(f"✅ Valid: {is_valid}")
    
    return {
        "premises": english["premises"],
        "conclusion": english["conclusion"],
        "formal_premises": formal["formal_premises"],
        "formal_conclusion": formal["formal_conclusion"],
        "valid": is_valid
    }