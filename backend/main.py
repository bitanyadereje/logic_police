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

# ------------------------------------------------------------------
# URL article extraction
# ------------------------------------------------------------------
import trafilatura
# ------------------------------------------------------------------
# NLTK for robust sentence splitting
# ------------------------------------------------------------------
import nltk
from nltk.tokenize import sent_tokenize

try:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)
except Exception:
    pass

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
# 1. TEXT CLEANING
# ------------------------------------------------------------------
def clean_text(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation))
    return ' '.join(text.split())

def clean_article_text(text: str) -> str:
    """Clean article text while preserving paragraph structure."""
    text = re.sub(r'[ \t]+', ' ', text)       # collapse spaces, not newlines
    text = re.sub(r'\n{3,}', '\n\n', text)    # normalize paragraph breaks
    return text.strip()

# ------------------------------------------------------------------
# 2. ROBUST SENTENCE SPLITTING (NLTK)
# ------------------------------------------------------------------
def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    sentences = sent_tokenize(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentences = [s[0].upper() + s[1:] for s in sentences if len(s) > 0]
    return sentences

# ------------------------------------------------------------------
# 3. IMPROVED ARGUMENT EXTRACTION (paragraph-aware + commentary)
# ------------------------------------------------------------------
def extract_arguments(text: str) -> dict:
    # 1. PARAGRAPH-AWARE SPLITTING
    paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]

    sentence_data = []
    for p_idx, p_text in enumerate(paragraphs):
        sents = split_sentences(p_text)
        for s_idx, sent in enumerate(sents):
            sentence_data.append({
                "text": sent,
                "p_idx": p_idx,
                "is_last_p": p_idx == len(paragraphs) - 1,
                "is_first_p": p_idx == 0,
                "is_last_in_p": s_idx == len(sents) - 1
            })

    if not sentence_data:
        return {"error": "Text too short or unreadable."}

    n = len(sentence_data)

    # 2. CONCLUSION SCORING (Upgraded for Commentary)
    conclusion_scores = []
    for i, data in enumerate(sentence_data):
        sent = data["text"]
        lower = sent.lower()
        score = 0.0

        # Classic formal indicators
        if re.search(r'^(therefore|so|thus|hence)\b', lower):
            score += 4.0
        if re.search(r'\b(consequently|as a result|ultimately|in conclusion)\b', lower):
            score += 3.0

        # Stance markers (Commentary/Opinion)
        if re.search(r'\b(the reality is|the point is|the time is now|the bottom line is)\b', lower):
            score += 3.5
        if re.search(r'\b(we need to|we must|we should|it is time to|the solution is)\b', lower):
            score += 2.5

        # Paragraph structural weighting
        if data["is_last_p"]:
            score += 3.0
        if data["is_last_in_p"] and not data["is_first_p"]:
            score += 1.0

        # Penalties
        if re.search(r'^(they argue|critics say|opponents claim|some say)', lower):
            score -= 3.0
        if lower.startswith("however") or lower.startswith("but"):
            score -= 2.0
        if '"' in sent or "'" in sent:
            score -= 1.0

        # Length constraints
        word_count = len(sent.split())
        if 8 <= word_count <= 30:
            score += 1.0
        elif word_count < 5:
            score -= 3.0

        conclusion_scores.append((i, sent, score))

    # Identify Conclusion
    conclusion_scores.sort(key=lambda x: x[2], reverse=True)
    best_conc = conclusion_scores[0]

    if best_conc[2] < 1.0:
        conclusion_idx = n - 1
        conclusion = sentence_data[-1]["text"]
    else:
        conclusion_idx = best_conc[0]
        conclusion = best_conc[1]

    # 3. PREMISE SCORING
    premise_indices = [i for i in range(n) if i != conclusion_idx]

    premise_indicators = [
        "because", "since", "as", "given that", "for example", "according to",
        "shows", "found", "reported", "revealed", "furthermore", "moreover"
    ]

    evidence_boost = [
        "study", "research", "data", "evidence", "expert", "analyst",
        "stanford", "harvard", "oxford", "microsoft", "google", "%"
    ]

    fluff_indicators = [
        "good news", "let me tell you", "here's the thing", "meh", "fun!"
    ]

    premise_scores = []
    for idx in premise_indices:
        sent = sentence_data[idx]["text"]
        lower = sent.lower()

        if any(fluff in lower for fluff in fluff_indicators):
            continue

        score = 0
        for word in premise_indicators:
            if word in lower:
                score += 1.5
        for word in evidence_boost:
            if word in lower:
                score += 2.0

        if re.search(r"\b\d+%?\b", sent):
            score += 2.0

        # Giant Premise Splitter
        word_count = len(sent.split())
        if word_count > 60:
            parts = re.split(r'(?:;|:| - | \band\b | \bbut\b )', sent)
            if len(parts) > 1 and len(parts[0].split()) > 5:
                sent = parts[0].strip() + "."
                score -= 1.0

        if word_count < 4:
            score -= 2.0

        if score > 0:
            premise_scores.append((idx, sent, score))

    premise_scores.sort(key=lambda x: x[2], reverse=True)
    top_premises = premise_scores[:7]

            # Fallback: use ALL non-conclusion sentences as premises
    if not top_premises:
        top_premises = [
            (i, sentence_data[i]["text"], 0)
            for i in range(n)
            if i != conclusion_idx
        ]
    # Deduplicate and finalize
    seen = set()
    final_premises = []
    for idx, sent, _ in top_premises:
        if sent not in seen and sent != conclusion:
            seen.add(sent)
            final_premises.append(sent)

        # 4. MINIMUM-VIABLE-ARGUMENT CHECK (loosened)
    if len(final_premises) < 1:
        return {"error": "Argument too weak or unstructured to parse logically."}
    
    return {"premises": final_premises, "conclusion": conclusion}

# ------------------------------------------------------------------
# 4. FALLACY DETECTION
# ------------------------------------------------------------------
def detect_fallacies(premises: list, conclusion: str) -> list[dict]:
    text = " ".join(premises + [conclusion]).lower()
    fallacies = []

    patterns = {
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
# 5. FORMAL LOGIC TRANSLATION
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
# 6. SYLLOGISM DETECTION
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

        # Modus ponens - handle "if X, Y" and "if X then Y", plus tense variants
       # Modus ponens - handle "if X, Y" and "if X then Y", plus tense variants
    for p in premises:
        p_lower = p.lower().strip()
        if_match = re.match(r'if\s+(.+?)(?:\s+then)?\s*,\s*(.+)', p_lower)
        if not if_match:
            if_match = re.match(r'if\s+(.+?)\s+then\s+(.+)', p_lower)
        if if_match:
            # Strip punctuation from both parts (this was the bug)
            antecedent = clean_text(if_match.group(1).strip())
            consequent = clean_text(if_match.group(2).strip())

            other_premises = [op for op in premises if op != p]
            others_clean = clean_text(" ".join(other_premises))
            conc_clean = clean_text(conclusion)

            # Direct match
            if antecedent in others_clean and consequent in conc_clean:
                return True

            # Stem-based match for tense variations
            for w in antecedent.split():
                if w in ('it', 'is', 'the', 'a', 'an', 'that', 'this', 'are'):
                    continue
                stem = w
                if stem.endswith('ing'):
                    stem = stem[:-3]
                elif stem.endswith('s'):
                    stem = stem[:-1]
                if len(stem) > 3 and stem in others_clean:
                    if consequent in conc_clean:
                        return True

    return False
# ------------------------------------------------------------------
# 7. SYMPY CHECK
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
# 8. MAIN ANALYSIS PIPELINE (with error handling)
# ------------------------------------------------------------------
def analyze_argument(text: str) -> dict:
    extracted = extract_arguments(text)

    # Handle the minimum-viable-argument error
    if "error" in extracted:
        return {
            "error": extracted["error"],
            "premises": [],
            "conclusion": "",
            "formal_premises": [],
            "formal_conclusion": "",
            "valid": False,
            "fallacies": [],
        }

    premises = extracted.get("premises", [])
    conclusion = extracted.get("conclusion", "")

    if not premises or not conclusion:
        return {
            "error": "Could not extract a clear argument from this text.",
            "premises": [],
            "conclusion": "",
            "formal_premises": [],
            "formal_conclusion": "",
            "valid": False,
            "fallacies": [],
        }

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
# 9. URL ANALYSIS ENDPOINT
# ------------------------------------------------------------------
@app.post("/analyze_url")
def analyze_url(request: dict):
    url = request.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided")

    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"error": "Could not fetch the URL. The page might be behind a login or the site is blocking scrapers."}

        text = trafilatura.extract(downloaded)
        if not text or len(text) < 50:
            return {"error": "Could not extract enough text from the page."}

        text = clean_article_text(text)
        return analyze_argument(text)

    except Exception as e:
        return {"error": f"Failed to fetch or parse the URL: {str(e)}"}
# ------------------------------------------------------------------
# 10. API ENDPOINTS
# ------------------------------------------------------------------
@app.post("/deconstruct")
def deconstruct(request: DeconstructRequest):
    return analyze_argument(request.text)

@app.post("/test_fallacies")
def test_fallacies(request: DeconstructRequest):
    extracted = extract_arguments(request.text)
    if "error" in extracted:
        return {
            "premises": [],
            "conclusion": "",
            "fallacies": [],
            "error": extracted["error"],
        }
    premises = extracted.get("premises", [])
    conclusion = extracted.get("conclusion", "")
    fallacies = detect_fallacies(premises, conclusion)
    return {
        "premises": premises,
        "conclusion": conclusion,
        "fallacies": fallacies,
    }