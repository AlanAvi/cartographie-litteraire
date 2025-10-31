# Cartographie Littéraires

Ce projet personnel a pour objectif de me permettre **d’apprendre et d’expérimenter** différentes technologies d’analyse de texte et de visualisation (LangChain, Ollama, embeddings, etc.).  
**La précision des résultats n’est pas la priorité pour le moment** : le but principal est pédagogique.

---

## Sommaire

1. [Présentation](#présentation)  
2. [Structure du projet](#structure-du-projet)  
3. [Installation](#installation)  
4. [Utilisation](#utilisation)  
5. [Exemple de sortie JSON](#exemple-de-sortie-json)  
6. [Fonctionnement détaillé](#fonctionnement-détaillé)  
7. [Dépendances principales](#dépendances-principales)  
8. [Limitations et remarques](#limitations-et-remarques)  

---

## Présentation

Le projet se décompose en deux étapes principales :  

1. **Extraction des relations** (`main.py`)  
   - Lit un roman (EPUB, PDF ou TXT).  
   - Identifie les **personnages** et leurs **relations** à l’aide d’un modèle de langage local (via Ollama).  
   - Sauvegarde les résultats au format **JSON**.

2. **Visualisation du graphe** (`graph_viewer.py`)  
   - Affiche les fichiers JSON sous forme de graphe interactif (NetworkX + Tkinter + Matplotlib).  
   - Permet de naviguer, déplacer les nœuds et voir la structure des relations.  

---

## Structure du projet

```
PAGAL/
│
├── livres/                      # Textes à analyser
│   ├── livre.epub
│   └── ...
│
├── src/                         # Code source principal
│   ├── file_converter.py
│   ├── graph_viewer.py
│   ├── main.py
│   │
│   ├── relations/               # JSON de sortie
│   │   ├── livre_241020250027.json
│   │   └── ...
│   │
│   └── chroma_db/               # Base Chroma (générée automatiquement)
│       └── livre/
│
├── .gitignore
└── README.md
```

---

## Installation

### 1. Cloner le projet
```bash
git clone <URL_DU_DEPOT>
cd PAGAL
```

### 2. Créer un environnement virtuel
```bash
python -m venv venv
```

### 3. Activer l'environnement virtuel
- **Linux / macOS** :  
```bash
source venv/bin/activate
```
- **Windows** :  
```bash
venv\Scripts\activate
```

### 4. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 5. Installer Ollama et le modèle
- Téléchargez Ollama : [https://ollama.com](https://ollama.com)  
- Chargez le modèle utilisé dans `main.py` (par défaut `llama3:8b`) :
```bash
ollama pull llama3:8b
```

---

## Utilisation

### Étape 1 — Extraction
Placez un fichier EPUB, PDF ou TXT dans le dossier `livres/`, puis lancez :
```bash
python src/main.py
```
Choisissez l’option :  
1. Générer le JSON des personnages et relations  
2. Lancer le Q&A interactif  

Le fichier JSON généré sera enregistré dans `src/relations/`.

### Étape 2 — Visualisation
Pour afficher les graphes :
```bash
python src/graph_viewer.py
```
- À gauche : la liste des fichiers JSON générés.  
- À droite : le graphe correspondant.  
- Les nœuds peuvent être déplacés à la souris.  
- Le programme met automatiquement à jour la liste si un nouveau fichier est ajouté.  

---

## Exemple de sortie JSON
```json
```json
[
  {
    "id": "char_1",
    "nom_complet": "Candide",
    "aliases": [],
    "relations": [
      {"id": "char_2", "type_de_la_relation": "amoureux", "evidence": null},
      {"id": "char_3", "type_de_la_relation": "mentor", "evidence": null}
    ]
  },
  {
    "id": "char_2",
    "nom_complet": "Cunégonde",
    "aliases": [],
    "relations": [
      {"id": "char_1", "type_de_la_relation": "amour", "evidence": null}
    ]
  },
  {
    "id": "char_3",
    "nom_complet": "Pangloss",
    "aliases": [],
    "relations": [
      {"id": "char_1", "type_de_la_relation": "maître", "evidence": null}
    ]
  }
]
```

---

## Fonctionnement détaillé

1. **Indexation du texte**  
   Le texte est découpé en fragments à l’aide de `RecursiveCharacterTextSplitter`.

2. **Vectorisation**  
   Les fragments sont convertis en vecteurs avec `SentenceTransformerEmbeddings` (modèle `all-MiniLM-L6-v2`).

3. **Extraction**  
   Le modèle de langage (`llama3:8b` via Ollama) identifie les personnages et leurs relations.

4. **Fusion et sauvegarde**  
   Les doublons sont fusionnés, puis les données sont sauvegardées dans un fichier JSON.

5. **Visualisation**  
   Les graphes sont affichés avec NetworkX et Matplotlib dans une interface Tkinter.

---

## Dépendances principales

- langchain  
- sentence-transformers  
- ollama  
- chromadb  
- ebooklib  
- beautifulsoup4  
- PyMuPDF (fitz)  
- networkx  
- matplotlib  
- tkinter  
