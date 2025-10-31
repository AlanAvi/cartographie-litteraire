import os
import re
import json
import uuid
from datetime import datetime
from slugify import slugify
from file_converter import convert
from pydantic import BaseModel, Field
from typing import List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama

# ===================== CONFIG =====================
FICHIER_LIVRE = "../livres/UnAnimalSauvage.epub"
TITRE = "Un Animal Sauvage"
AUTEUR = "Joel Dicker"
CHROMA_DIR = "chroma_db"
RELATIONS_DIR = "relations"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_MODEL = "llama3:8b"

# ===================== SCHÉMAS =====================
class Relation(BaseModel):
    target_name: str
    type: str
    evidence: Optional[str] = None

class Character(BaseModel):
    id: str = Field(default_factory=lambda: f"char_{uuid.uuid4().hex[:8]}")
    name: str
    relations: List[Relation] = Field(default_factory=list)

# ===================== INITIALISATION =====================
embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)
slug = slugify(TITRE)
db_path = os.path.join(CHROMA_DIR, slug)
os.makedirs(db_path, exist_ok=True)
os.makedirs(RELATIONS_DIR, exist_ok=True)

# --- Indexation du livre ---
if not os.listdir(db_path):
    print(f"Indexation du livre '{TITRE}'...")
    texte = convert(FICHIER_LIVRE)
    texte = f"Titre: {TITRE}\nAuteur: {AUTEUR}\n\n{texte}".replace("\r", "")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=8000,
        chunk_overlap=800,
        separators=["\n\n", "\n", ".", "!", "?"]
    )
    chunks = splitter.split_text(texte)
    docs = [{"text": c, "metadata": {"titre": TITRE, "auteur": AUTEUR}} for c in chunks]

    vectordb = Chroma(persist_directory=db_path, embedding_function=embeddings)
    vectordb.add_texts([d["text"] for d in docs], metadatas=[d["metadata"] for d in docs])
    vectordb.persist()
    print("Indexation terminée.")
else:
    print(f"Base '{slug}' trouvée.")
    vectordb = Chroma(persist_directory=db_path, embedding_function=embeddings)

# ===================== LLM =====================
llm = Ollama(model=OLLAMA_MODEL, temperature=0)

# ===================== FONCTIONS =====================
def extract_names_from_text(context: str, llm: Ollama) -> List[str]:
    """Extraction simple des noms de personnages présents dans le texte"""
    prompt = f"""
Tu es un extracteur de personnages littéraires.  
Trouve tous les personnages nommés explicitement dans ce texte (prénoms, noms, surnoms importants).
Ne crée rien. Ne répète pas de noms.  
Retourne uniquement une liste JSON simple.

Exemple :
["Greg", "Sophie", "Antoine"]

Texte :
\"\"\"{context}\"\"\"
"""
    response = llm.invoke(prompt)
    try:
        names = json.loads(response.strip())
        if isinstance(names, list):
            return [n.strip() for n in names if isinstance(n, str) and n.strip()]
        return []
    except Exception:
        return []


def extract_relations_between_characters(context: str, characters: List[str], llm: Ollama) -> List[Character]:
    """Analyse les relations entre personnages dans un chunk donné"""
    if not characters:
        return []

    joined_names = ", ".join(characters)
    prompt = f"""
Tu es un expert en analyse littéraire.  
Voici un extrait de roman contenant les personnages suivants : {joined_names}.  

Ta tâche : trouver toutes les relations explicites ou implicites (familiales, amoureuses, professionnelles, amicales, conflictuelles...) entre eux.
Utilise uniquement les indices clairs du texte (phrases, verbes d’action, dialogues...).
Ne crée rien si le texte ne montre pas la relation.

Format JSON strict :
[
  {{
    "name": "Nom exact du personnage",
    "relations": [
      {{ "target_name": "Autre personnage", "type": "type de relation", "evidence": "phrase du texte" }}
    ]
  }}
]

Texte :
\"\"\"{context}\"\"\"
"""
    response = llm.invoke(prompt)
    try:
        data = json.loads(response.strip())
        result = []
        for d in data:
            if isinstance(d, dict) and "name" in d:
                result.append(Character(**d))
        return result
    except Exception:
        return []


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ'-]", "", name.lower().strip())


def merge_characters(characters: List[Character]) -> List[Character]:
    """Fusionne les personnages avec des noms similaires"""
    merged = {}
    for char in characters:
        norm = normalize_name(char.name)
        if norm not in merged:
            merged[norm] = char
        else:
            merged[norm].relations.extend(char.relations)
    return list(merged.values())


def extract_characters_and_relations(vectordb, llm, titre, auteur, save_path):
    slug = slugify(titre)
    timestamp = datetime.now().strftime("%d%m%Y%H%M")
    out_file = os.path.join(save_path, f"{slug}_{timestamp}.json")

    # ==== PASS 1 : EXTRACTION DES PERSONNAGES ====
    print("Pass 1 — Extraction des personnages...")
    docs = vectordb.similarity_search("personnages principaux, relations, famille, amis", k=40)
    all_names = set()
    for i, doc in enumerate(docs, 1):
        names = extract_names_from_text(doc.page_content, llm)
        all_names.update(names)
        print(f"Chunk {i}/{len(docs)} → +{len(names)} noms trouvés")
    print(f"Total personnages détectés : {len(all_names)}\n")

    # ==== PASS 2 : EXTRACTION DES RELATIONS ====
    print("Pass 2 — Analyse des relations...")
    all_characters: List[Character] = []
    for i, doc in enumerate(docs, 1):
        chars = extract_relations_between_characters(doc.page_content, list(all_names), llm)
        all_characters.extend(chars)
        print(f"Chunk {i}/{len(docs)} → {len(chars)} ensembles de relations détectés")

    merged_characters = merge_characters(all_characters)

    # Nettoyage : suppression des persos sans relations
    filtered = [c for c in merged_characters if c.relations]
    print(f"\nPersonnages finaux : {len(filtered)} sur {len(merged_characters)} retenus")

    # Sauvegarde JSON
    result = [
        {
            "id": c.id,
            "nom_complet": c.name,
            "relations": [
                {
                    "target_name": r.target_name,
                    "type_de_relation": r.type,
                    "evidence": r.evidence
                } for r in c.relations
            ]
        } for c in filtered
    ]
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Extraction terminée : {len(filtered)} personnages sauvegardés → {out_file}")
    return out_file


def local_qa(vectordb, llm, titre, auteur):
    print(f"Q&A sur '{titre}' — tape 'exit' pour quitter")
    while True:
        q = input("\nQuestion : ").strip()
        if q.lower() in {"exit", "quit"}:
            break
        docs = vectordb.similarity_search(q, k=5)
        context = "\n\n".join([d.page_content for d in docs])

        prompt = f"""
Réponds uniquement à partir du contexte. Si tu ne sais pas, dis "Je ne sais pas".

Contexte :
{context}

Question : {q}
Réponse :
"""
        answer = llm.invoke(prompt)
        print(f"\n{answer.strip()}\n" + "-" * 50)


# ===================== MENU =====================
if __name__ == "__main__":
    print("\nChoisissez une option :")
    print("1 - Générer le JSON des personnages et relations")
    print("2 - Lancer le Q&A interactif")
    choice = input("Entrez 1 ou 2 : ").strip()

    if choice == "1":
        extract_characters_and_relations(vectordb, llm, TITRE, AUTEUR, RELATIONS_DIR)
    elif choice == "2":
        local_qa(vectordb, llm, TITRE, AUTEUR)
    else:
        print("Option invalide.")
