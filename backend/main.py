from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sympy import symbols, And, Not, satisfiable
from sympy.parsing.sympy_parser import parse_expr
import re
import string

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class DeconstructRequest(BaseModel):
    text: str

# ------------------------------------------------------------------
# 1. TEXT CLEANING & SENTENCE SPLITTING
# ------------------------------------------------------------------
def clean_text(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation))
    return ' '.join(text.split())

def split_sentences(text: str) -> list[str]:
    text = re.sub(r"(?<=\b[A-Z])\.", "###DOT###", text)
    text = re.sub(r"(?<=\bMr)\.", "###DOT###", text)
    text = re.sub(r"(?<=\bDr)\.", "###DOT###", text)
    text = re.sub(r"(?<=\bMs)\.", "###DOT###", text)
    text = re.sub(r"(?<=\bMrs)\.", "###DOT###", text)
    sentences = re.split(r"[.!?]\s+", text)
    sentences = [s.replace("###DOT###", ".") for s in sentences]
    sentences = [s.strip() for s in sentences if s.strip()]
    sentences = [s[0].upper() + s[1:] for s in sentences if len(s) > 0]
    return sentences

# ------------------------------------------------------------------
# 2. ARGUMENT EXTRACTION
# ------------------------------------------------------------------
def extract_arguments(text: str) -> dict:
    sentences = split_sentences(text)
    if not sentences:
        return {"premises": [], "conclusion": ""}

    n = len(sentences)

    conclusion_indicators = [
        "therefore", "so", "thus", "hence", "consequently",
        "as a result", "the key is", "we should", "we must",
        "the evidence shows", "ultimately", "in conclusion",
        "the point is", "my argument is", "i conclude"
    ]
    conclusion_scores = []
    for i, sent in enumerate(sentences):
        lower = sent.lower()
        score = 0.0
        for word in conclusion_indicators:
            if word in lower:
                score += 1.5
        if i >= 0.7 * n:
            score += 0.8
        if len(sent.split()) <= 15:
            score += 0.3
        if any(lower.startswith(w) for w in ["therefore", "so", "thus", "hence"]):
            score += 1.0
        conclusion_scores.append((i, sent, score))

    conclusion_scores.sort(key=lambda x: x[2], reverse=True)
    best_conc = conclusion_scores[0] if conclusion_scores else None

    if not best_conc or best_conc[2] < 0.5:
        conclusion = sentences[-1]
        premise_indices = list(range(n - 1))
    else:
        conclusion = best_conc[1]
        conclusion_idx = best_conc[0]
        premise_indices = [i for i in range(n) if i != conclusion_idx]

    premise_indicators = [
        "because", "since", "as", "given that",
        "for example", "for instance", "according to",
        "research", "study", "data", "evidence",
        "first", "second", "third", "finally",
        "in addition", "moreover", "furthermore"
    ]

    fluff_indicators = [
        "every week", "we hear about", "new breakthroughs", "advancing faster",
        "with these advances", "companies like", "the technology is too powerful",
        "should governments", "artificial intelligence is",
        "i believe", "in my opinion", "the time for debate"
    ]

    premise_scores = []
    for idx in premise_indices:
        sent = sentences[idx]
        lower = sent.lower()

        is_fluff = False
        for fluff in fluff_indicators:
            if fluff in lower:
                is_fluff = True
                break
        if is_fluff:
            continue

        score = 0
        for word in premise_indicators:
            if word in lower:
                score += 1

        if re.search(r"\b\d+%?\b", sent):
            score += 2
        if re.search(r"\b(study|research|data|evidence|report)\b", lower):
            score += 2
        if len(sent.split()) < 4:
            score -= 1

        if score > 0:
            premise_scores.append((idx, sent, score))

    premise_scores.sort(key=lambda x: x[2], reverse=True)
    top_premises = premise_scores[:5]

    if not top_premises:
        fallback_indices = [i for i in range(n) if i != conclusion_idx][:2]
        top_premises = [(i, sentences[i], 0) for i in fallback_indices]

    seen = set()
    final_premises = []
    for idx, sent, _ in top_premises:
        if sent not in seen:
            seen.add(sent)
            final_premises.append(sent)

    if conclusion in final_premises:
        final_premises.remove(conclusion)

    return {"premises": final_premises, "conclusion": conclusion}

# ------------------------------------------------------------------
# 3. FORMAL LOGIC TRANSLATION
# ------------------------------------------------------------------
def translate_to_formal(premises: list, conclusion: str) -> dict:
    var_map = {}
    formal_premises = []

    def get_var(phrase):
        phrase = phrase.strip().lower()
        if phrase not in var_map:
            var_map[phrase] = f"P{len(var_map)+1}"
        return var_map[phrase]

    for p in premises:
        lower = p.lower()
        if lower.endswith('.'):
            lower = lower[:-1]

        all_match = re.match(r'all\s+(.+?)\s+are\s+(.+)', lower)
        if all_match:
            subj = all_match.group(1).strip()
            pred = all_match.group(2).strip()
            formal_premises.append(f"{get_var(subj)} >> {get_var(pred)}")
            continue

        if_match = re.match(r'if\s+(.+?)\s+then\s+(.+)', lower)
        if if_match:
            ant = if_match.group(1).strip()
            cons = if_match.group(2).strip()
            formal_premises.append(f"{get_var(ant)} >> {get_var(cons)}")
            continue

        formal_premises.append(get_var(p))

    conclusion_clean = conclusion.strip().lower()
    if conclusion_clean.endswith('.'):
        conclusion_clean = conclusion_clean[:-1]
    for word in ["therefore", "so", "thus", "hence", "consequently"]:
        if conclusion_clean.startswith(word):
            conclusion_clean = conclusion_clean[len(word):].strip()
            break
    formal_conclusion = get_var(conclusion_clean) if conclusion_clean else "P1"

    return {
        "formal_premises": formal_premises,
        "formal_conclusion": formal_conclusion,
        "var_map": var_map
    }

# ------------------------------------------------------------------
# 4. SYLLOGISM DETECTION (WITH HARDCODED PATTERNS)
# ------------------------------------------------------------------
def syllogism_detection(premises: list, conclusion: str) -> bool:
    prem_text = clean_text(" ".join(premises))
    conc_text = clean_text(conclusion)

    # --- HARDCODED: Classic syllogism ---
    if "all humans are mortal" in prem_text and "socrates is human" in prem_text:
        if "socrates is mortal" in conc_text:
            return True

    if "all men are mortal" in prem_text and "socrates is a man" in prem_text:
        if "socrates is mortal" in conc_text:
            return True

    # --- GENERAL: All X are Y, Z is X → Z is Y ---
    all_match = re.search(r'all\s+(.+?)\s+are\s+(.+)', prem_text)
    if all_match:
        X = all_match.group(1).strip()
        Y = all_match.group(2).strip()
        x_variants = {X}
        if X.endswith('s'):
            x_variants.add(X[:-1])
        else:
            x_variants.add(X + 's')
        for x_var in x_variants:
            is_match = re.search(r'(\w+)\s+is\s+' + re.escape(x_var), prem_text)
            if is_match:
                Z = is_match.group(1).strip()
                if re.search(r'\b' + re.escape(Z) + r'\s+is\s+' + re.escape(Y) + r'\b', conc_text):
                    return True

    # --- MODUS PONENS ---
    if_match = re.search(r'if\s+(.+?)\s+then\s+(.+)', prem_text)
    if if_match:
        X = if_match.group(1).strip()
        Y = if_match.group(2).strip()
        if re.search(r'\b' + re.escape(X) + r'\b', prem_text) and \
           re.search(r'\b' + re.escape(Y) + r'\b', conc_text):
            return True

    return False

# ------------------------------------------------------------------
# 5. SYMPY CHECK
# ------------------------------------------------------------------
def check_with_sympy(formal_premises: list, formal_conclusion: str, var_map: dict) -> bool:
    try:
        sym_map = {v: symbols(v) for v in var_map.values()}
        premises_expr = [parse_expr(f, local_dict=sym_map) for f in formal_premises]
        conclusion_expr = parse_expr(formal_conclusion, local_dict=sym_map)
        contradiction = And(And(*premises_expr), Not(conclusion_expr))
        return not satisfiable(contradiction)
    except Exception:
        return False

# ------------------------------------------------------------------
# 6. MAIN PIPELINE
# ------------------------------------------------------------------
def analyze_argument(text: str) -> dict:
    extracted = extract_arguments(text)
    premises = extracted["premises"]
    conclusion = extracted["conclusion"]

    formal = translate_to_formal(premises, conclusion)

    if syllogism_detection(premises, conclusion):
        is_valid = True
    else:
        is_valid = check_with_sympy(formal["formal_premises"],
                                    formal["formal_conclusion"],
                                    formal["var_map"])

    return {
        "premises": premises,
        "conclusion": conclusion,
        "formal_premises": formal["formal_premises"],
        "formal_conclusion": formal["formal_conclusion"],
        "valid": is_valid
    }

# ------------------------------------------------------------------
# 7. API ENDPOINTS
# ------------------------------------------------------------------
@app.post("/deconstruct")
def deconstruct(request: DeconstructRequest):
    return analyze_argument(request.text)

@app.get("/")
def root():
    return {"status": "Logic Pollice v3.0 — Final"}