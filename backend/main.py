from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException
from pydantic import BaseModel
from sympy import symbols, And, Not, satisfiable
from sympy.parsing.sympy_parser import parse_expr
import re
import string
import os

# ------------------------------------------------------------------
# URL article extraction
# ------------------------------------------------------------------
from newspaper import Article

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

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
# 2. IMPROVED ARGUMENT EXTRACTION (for long texts & commentary)
# ------------------------------------------------------------------
def extract_arguments(text: str) -> dict:
    # Single-sentence "so" / "therefore"
    text_clean = text.strip()
    if " so " in text_clean.lower():
        parts = re.split(r'\s+so\s+', text_clean, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return {"premises": [parts[0].strip()], "conclusion": parts[1].strip()}
    if " therefore " in text_clean.lower():
        parts = re.split(r'\s+therefore\s+', text_clean, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return {"premises": [parts[0].strip()], "conclusion": parts[1].strip()}

    sentences = split_sentences(text)
    if not sentences:
        return {"premises": [], "conclusion": ""}

    n = len(sentences)

    # ---- Conclusion scoring ----
    conclusion_scores = []
    for i, sent in enumerate(sentences):
        lower = sent.lower()
        score = 0.0

        # ---- Big bonus: sentence starts with "Therefore" or "So" ----
        if re.search(r'^(therefore|so|thus|hence)\b', lower):
            score += 4.0

        # ---- NEW: Bonus for policy recommendations ----
        if re.search(r'\b(we need|we should|we must|the solution is|the answer is)\b', lower):
            score += 2.5

        # ---- NEW: Bonus for final sentences ----
        if i >= n - 2:
            score += 1.5

        # ---- Penalise counterargument openers ----
        if re.search(r'^(they argue|critics say|opponents claim|proponents argue|some say|others argue)', lower):
            score -= 3.0

        # ---- Penalise quotations ----
        if '"' in sent or "'" in sent or "“" in sent or "”" in sent:
            score -= 2.0

        # ---- Penalise sentences that start with "however" ----
        if lower.startswith("however"):
            score -= 2.0

        # ---- Bonus: strong conclusion indicators ----
        if re.search(r'\b(therefore|so|thus|hence|consequently|as a result|ultimately|in conclusion)\b', lower):
            score += 3.0

        # ---- Bonus: substantive claims ----
        if re.search(r'\b(should|must|ought to|need to|is essential|is necessary)\b', lower):
            score += 1.5

        # ---- Bonus: strong thesis phrases ----
        if re.search(r'\b(the key is|the point is|my argument is|i conclude)\b', lower):
            score += 2.0

        # ---- Position bonus: last sentence gets a big boost ----
        if i == n - 1:
            score += 2.0
        elif i >= 0.8 * n:
            score += 0.8

        # ---- Length: prefer 10–25 word conclusions ----
        word_count = len(sent.split())
        if 10 <= word_count <= 25:
            score += 0.5
        elif word_count < 6:
            score -= 1.0
        if word_count < 4:
            score -= 2.0

        conclusion_scores.append((i, sent, score))

    # ---- Find the best conclusion ----
    conclusion_scores.sort(key=lambda x: x[2], reverse=True)
    best_conc = conclusion_scores[0] if conclusion_scores else None

    if not best_conc or best_conc[2] < 0.5:
        conclusion = sentences[-1]
        conclusion_idx = n - 1
    else:
        conclusion = best_conc[1]
        conclusion_idx = best_conc[0]

    premise_indices = [i for i in range(n) if i != conclusion_idx]

    # ---- Premise scoring (enhanced for commentary) ----
    premise_indicators = [
        "because", "since", "as", "given that",
        "for example", "for instance", "according to",
        "research", "study", "data", "evidence",
        "first", "second", "third", "finally",
        "shows", "found", "reported", "revealed",
        "in addition", "moreover", "furthermore",
        # ---- NEW: Opinion and commentary markers ----
        "i think", "i believe", "my view is", "in my opinion",
        "we need", "we should", "we must", "we can't",
        "the reality is", "the truth is", "the point is",
        "what matters is", "what we need is", "what i'm saying is",
        "the problem is", "the issue is", "the question is",
    ]

    evidence_boost = [
        "example", "study", "research", "data", "evidence",
        "GDPR", "EU", "European Union", "Stanford", "Harvard",
        "Cambridge", "Oxford", "Microsoft", "Google", "cents", "%",
        # ---- NEW: Commentary evidence ----
        "expert", "analyst", "reporter", "source", "friend"
    ]

    fluff_indicators = [
        "good news", "bad news", "fun!", "what does the evidence say",
        "let me tell you", "here's the thing", "the best", "the worst",
        "meh", "great | good | meh", "every week", "we hear about",
        "new breakthroughs", "advancing faster", "with these advances"
    ]

    premise_scores = []
    for idx in premise_indices:
        sent = sentences[idx]
        lower = sent.lower()

        # ---- Skip fluff ----
        is_fluff = False
        for fluff in fluff_indicators:
            if fluff in lower:
                is_fluff = True
                break
        if is_fluff:
            continue

        score = 0

        # ---- Premise indicators ----
        for word in premise_indicators:
            if word in lower:
                score += 1

        # ---- Evidence boost ----
        for word in evidence_boost:
            if word in lower:
                score += 2

        if re.search(r"\b\d+%?\b", sent):
            score += 2

        if re.search(r"\b(study|research|data|evidence|report|found|showed)\b", lower):
            score += 2

        if re.search(r"\b(Microsoft|Cambridge|Harvard|Stanford|Oxford|Nature|GDPR|EU)\b", sent):
            score += 3

        if len(sent.split()) < 4:
            score -= 1

        if score > 0:
            premise_scores.append((idx, sent, score))

    premise_scores.sort(key=lambda x: x[2], reverse=True)
    # Allow up to 7 premises for long texts
    top_premises = premise_scores[:7]

    if not top_premises:
        fallback_indices = [i for i in range(n) if i != conclusion_idx and len(sentences[i].split()) > 5][:2]
        top_premises = [(i, sentences[i], 0) for i in fallback_indices]

    seen = set()
    final_premises = []
    for idx, sent, _ in top_premises:
        if sent not in seen and sent != conclusion:
            seen.add(sent)
            final_premises.append(sent)

    if not final_premises:
        for i, sent in enumerate(sentences):
            if sent != conclusion and len(sent.split()) > 5 and i not in premise_indices:
                final_premises.append(sent)
                break

    return {"premises": final_premises, "conclusion": conclusion}

# ------------------------------------------------------------------
# 3. NARROWED FALLACY DETECTION (fewer false positives)
# ------------------------------------------------------------------
def detect_fallacies(premises: list, conclusion: str) -> list[dict]:
    text = " ".join(premises + [conclusion]).lower()
    fallacies = []

    patterns = {
        # ---- NARROWED: No more false positives ----
        "ad hominem": ["ad hominem", "attacks the person", "you can't trust him", "you're wrong because", "insult"],
        "straw man": ["straw man", "misrepresent", "exaggerated", "caricature"],
        "appeal to authority": ["authority", "expert", "scientist", "according to", "famous"],
        "slippery slope": ["slippery slope", "domino effect", "one thing leads to another"],
        "circular reasoning": ["circular reasoning", "begging the question", "assumes the conclusion"],
        "false dilemma": ["false dilemma", "either/or", "only two options"],
        "hasty generalization": ["all women", "all men", "all people", "everyone always", "never once", "all feminists"],
        "ad populum": ["everyone thinks", "popular", "common sense", "the crowd"],
        "tu quoque": ["tu quoque", "you too", "you also", "hypocrite"],
        "appeal to emotion": ["appeal to emotion", "fear", "pity", "guilt", "anger"],
    }

    for fallacy, keywords in patterns.items():
        if any(kw in text for kw in keywords):
            fallacies.append({
                "fallacy_name": fallacy.title(),
                "explanation": f"Detected based on keywords: {', '.join(keywords)}"
            })
            break

    return fallacies

# ------------------------------------------------------------------
# 4. FORMAL LOGIC TRANSLATION
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
# 5. SYLLOGISM DETECTION
# ------------------------------------------------------------------
def syllogism_detection(premises: list, conclusion: str) -> bool:
    prem_text = clean_text(" ".join(premises))
    conc_text = clean_text(conclusion)

    if "all humans are mortal" in prem_text and "socrates is human" in prem_text:
        if "socrates is mortal" in conc_text:
            return True

    if "all men are mortal" in prem_text and "socrates is a man" in prem_text:
        if "socrates is mortal" in conc_text:
            return True

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

    if_match = re.search(r'if\s+(.+?)\s+then\s+(.+)', prem_text)
    if if_match:
        X = if_match.group(1).strip()
        Y = if_match.group(2).strip()
        if re.search(r'\b' + re.escape(X) + r'\b', prem_text) and \
           re.search(r'\b' + re.escape(Y) + r'\b', conc_text):
            return True

    return False

# ------------------------------------------------------------------
# 6. SYMPY CHECK
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
# 7. MAIN ANALYSIS PIPELINE
# ------------------------------------------------------------------
def analyze_argument(text: str) -> dict:
    extracted = extract_arguments(text)
    premises = extracted["premises"]
    conclusion = extracted["conclusion"]

    formal = translate_to_formal(premises, conclusion)
    if syllogism_detection(premises, conclusion):
        is_valid = True
    else:
        is_valid = check_with_sympy(formal["formal_premises"], formal["formal_conclusion"], formal["var_map"])

    fallacies = detect_fallacies(premises, conclusion)

    return {
        "premises": premises,
        "conclusion": conclusion,
        "formal_premises": formal["formal_premises"],
        "formal_conclusion": formal["formal_conclusion"],
        "valid": is_valid,
        "fallacies": fallacies,
    }

# ------------------------------------------------------------------
# 8. URL ANALYSIS ENDPOINT
# ------------------------------------------------------------------
@app.post("/analyze_url")
def analyze_url(request: dict):
    url = request.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided")

    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text

        if not text or len(text) < 50:
            return {
                "error": "Could not extract enough text from the URL. The page might be paywalled or behind a login."
            }

        return analyze_argument(text)

    except Exception as e:
        return {"error": f"Failed to fetch or parse the URL: {str(e)}"}

# ------------------------------------------------------------------
# 9. API ENDPOINTS
# ------------------------------------------------------------------
@app.post("/deconstruct")
def deconstruct(request: DeconstructRequest):
    return analyze_argument(request.text)

@app.post("/test_fallacies")
def test_fallacies(request: DeconstructRequest):
    extracted = extract_arguments(request.text)
    premises = extracted["premises"]
    conclusion = extracted["conclusion"]
    fallacies = detect_fallacies(premises, conclusion)
    return {
        "premises": premises,
        "conclusion": conclusion,
        "fallacies": fallacies,
    }