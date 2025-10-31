import os
import fitz  # PyMuPDF
from ebooklib import epub
from bs4 import BeautifulSoup
import ebooklib

def pdf_to_txt(pdf_path):
    """
    Convertit un texte au format pdf en chaine de caractères.
    """
    texte = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            texte += page.get_text("text")
    return texte

def epub_to_txt(epub_path):
    """
    Convertit un texte au format epub en chaine de caractères.
    """
    book = epub.read_epub(epub_path)
    texte = ""
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_body_content(), "html.parser")
            texte += soup.get_text()
    return texte

def convert(chemin_entree):
    """
    Convertit un texte au format pdf, txt ou epub en chaine de caractères.
    """
    ext = os.path.splitext(chemin_entree)[1].lower()

    if ext == ".pdf":
        return pdf_to_txt(chemin_entree)
    elif ext == ".epub":
        return epub_to_txt(chemin_entree)
    elif ext == ".txt":
        with open(chemin_entree, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Format non pris en charge : {ext}")
