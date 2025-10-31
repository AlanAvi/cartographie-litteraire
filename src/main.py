import os
import re
import json
import uuid
from datetime import datetime

from slugify import slugify
from file_converter import convert
from instructor import Mode
import instructor
from pydantic import BaseModel, Field
from typing import List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import Chroma

# ===================== CONFIG =====================
FICHIER_LIVRE = "../livres/candide.epub"
TITRE = "Candide"
AUTEUR = "Voltaire"
CHROMA_DIR = "chroma_db"
RELATIONS_DIR = "relations"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_MODEL = "llama3:8b"  # ou "llama3", "phi3", etc.

# ===================== SCHÉMAS PYDANTIC =====================
class Relation(BaseModel):
    target_name: str = Field(..., description="Nom du personnage cible (exact)")
    type: str = Field(..., description="Type de relation")
    evidence: Optional[str] = Field(None, description="Preuve")
    target_id: Optional[str] = Field(None, description="Résolu après fusion")

class Character(BaseModel):
    id: str = Field(default_factory=lambda: f"char_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Nom complet")
    aliases: List[str] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)

# ===================== INITIALISATION =====================
embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)
slug = slugify(TITRE)
db_path = os.path.join(CHROMA_DIR, slug)
os.makedirs(db_path, exist_ok=True)
os.makedirs(RELATIONS_DIR, exist_ok=True)

# --- Indexation ---
if not os.listdir(db_path):
    print(f"Indexation du livre '{TITRE}'...")
    texte = convert(FICHIER_LIVRE)
    texte = f"Titre: {TITRE}\nAuteur: {AUTEUR}\n\n{texte}"
    texte = texte.replace("\n\n", "\n").replace("\r", "")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=200,
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
from openai import OpenAI
import instructor
from langchain_community.llms import Ollama

# Ollama via OpenAI API
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
llm_instructor = instructor.from_openai(client, mode=Mode.JSON)


# Pour Q&A (garde LangChain)
llm = Ollama(model=OLLAMA_MODEL, temperature=0)

# ===================== FONCTIONS =====================
def is_name_in_text(name: str, text: str) -> bool:
    """
    Vérifie si un nom (ou un de ses aliases) apparaît littéralement dans le texte.
    Tolère les variations de casse, mais PAS les paraphrases.
    """
    if not name.strip():
        return False
    # Échappe les caractères spéciaux pour regex
    pattern = re.escape(name.strip())
    return bool(re.search(rf'\b{pattern}\b', text, re.IGNORECASE))

def extract_characters_progressively(vectordb, llm_instructor, titre, auteur, save_path):
    slug = slugify(titre)
    timestamp = datetime.now().strftime("%d%m%Y%H%M")
    out_file = os.path.join(save_path, f"{slug}_{timestamp}.json")

    all_characters = {}
    character_names = {}

    query = "personnages principaux relations famille amis ennemis couple travail braque sophie greg"
    docs = vectordb.similarity_search(query, k=40)

    print(f"Début de l'extraction sur {len(docs)} chunks...")

    for i, doc in enumerate(docs, 1):
        context = doc.page_content.strip()

        prompt = f"""
        EXTRACTION ULTRA-STRICTE DES PERSONNAGES — ZÉRO HALLUCINATION

        RÈGLES ABSOLUES :
        1. Tu NE DOIS EXTRAIRE QUE les noms qui APPARAISSENT MOT POUR MOT dans le texte.
        2. Si un nom n'est PAS écrit EXACTEMENT (même casse différente), IGNORE-LE.
        3. Tu NE DOIS RIEN INVENTER, NI DÉDUIRE, NI GÉNÉRALISER.
        4. Tu NE DOIS PAS proposer plus de 8 personnages par chunk.
        5. Si tu doutes → IGNORE.
        6. Si aucun personnage clair → retourne []

        EXEMPLE VALIDE :
        [
        {{
            "name": "Candide",
            "aliases": [],
            "relations": [{{ "target_name": "Pangloss", "type": "maître" }}]
        }}
        ]

        TEXTE À ANALYSER :
        \"\"\"{context}\"\"\"
        """

        try:
            new_chars: List[Character] = llm_instructor.messages.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=List[Character],
                max_tokens=2048,
                temperature=0
            )

            # === FUSION ===
            for char in new_chars:
                # VALIDER QUE LE NOM PRINCIPAL EXISTE DANS LE TEXTE
                if not is_name_in_text(char.name, context):
                    continue  # IGNORER CE PERSONNAGE

                norm_name = char.name.strip().lower()
                existing_id = character_names.get(norm_name)

                if existing_id:
                    existing = all_characters[existing_id]
                    # Valider chaque relation
                    valid_relations = []
                    for rel in char.relations:
                        if is_name_in_text(rel.target_name, context):
                            if not any(r.target_name.lower() == rel.target_name.lower() and r.type == rel.type for r in existing.relations):
                                valid_relations.append(rel)
                    existing.relations.extend(valid_relations)
                    existing.aliases = list(set(existing.aliases + char.aliases))
                else:
                    # Valider les relations du nouveau personnage
                    valid_relations = [
                        rel for rel in char.relations
                        if is_name_in_text(rel.target_name, context)
                    ]
                    char.relations = valid_relations
                    if not char.relations and len(char.aliases) == 0 and not is_name_in_text(char.name, context):
                        continue  # Ignorer les personnages isolés sans preuve

                    new_id = char.id
                    all_characters[new_id] = char
                    character_names[norm_name] = new_id
                    for alias in char.aliases:
                        if is_name_in_text(alias, context):
                            character_names[alias.strip().lower()] = new_id

            print(f"Chunk {i}/{len(docs)} → {len(all_characters)} personnages")

        except Exception as e:
            print(f"Erreur chunk {i} : {e}")
            continue

    # === RÉSOLUTION FINALE DES target_id ===
    print("Résolution finale des relations...")
    for char in all_characters.values():
        for rel in char.relations:
            if rel.target_id is None:
                target_norm = rel.target_name.strip().lower()
                target_id = character_names.get(target_norm)
                if target_id:
                    rel.target_id = target_id

    # === SUPPRESSION DES PERSONNAGES SANS RELATIONS ===
    filtered_characters = {
        cid: c for cid, c in all_characters.items() if len(c.relations) > 0
    }

    print(f"Personnages initiaux : {len(all_characters)} → après filtrage : {len(filtered_characters)}")

    # === EXPORT FINAL ===
    result = [
        {
            "id": cid,
            "nom_complet": c.name,
            "aliases": c.aliases,
            "relations": [
                {
                    "id": r.target_id,
                    "type_de_la_relation": r.type,
                    "evidence": r.evidence
                }
                for r in c.relations
                if r.target_id
            ]
        }
        for cid, c in filtered_characters.items()
    ]

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Extraction terminée : {len(filtered_characters)} personnages sauvegardés → {out_file}")
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
Réponds UNIQUEMENT à partir du contexte. Si tu ne sais pas, dis "Je ne sais pas".

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
    print("1 - Générer le JSON des personnages")
    print("2 - Lancer le Q&A interactif")
    choice = input("Entrez 1 ou 2 : ").strip()

    if choice == "1":
        extract_characters_progressively(vectordb, llm_instructor, TITRE, AUTEUR, RELATIONS_DIR)
    elif choice == "2":
        local_qa(vectordb, llm, TITRE, AUTEUR)
    else:
        print("Option invalide.")