import json
import os
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import ttk
import threading
import time
import sys
import signal


# === Dossier contenant les JSON ===
DOSSIER_JSON = "relations"

# === Création de la fenêtre principale ===
root = tk.Tk()
root.title("Explorateur de Graphes JSON")
root.state('zoomed')  # Plein écran

stop_monitor = False

# === Frame principale ===
main_frame = ttk.Frame(root)
main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# === Barre latérale : liste des fichiers ===
list_frame = ttk.LabelFrame(main_frame, text=" Fichiers JSON ", padding=10)
list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

listbox = tk.Listbox(list_frame, font=("Consolas", 10), width=40)
listbox.pack(fill=tk.BOTH, expand=True)

scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
listbox.config(yscrollcommand=scrollbar.set)

# === Zone du graphe ===
canvas_frame = ttk.Frame(main_frame)
canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

fig, ax = plt.subplots(figsize=(12, 8))
canvas = FigureCanvasTkAgg(fig, master=canvas_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# === Variables globales ===
G = nx.Graph()
pos = {}
selected_node = None
node_labels = {}
edge_labels = {}
current_file = None

# === Mise à jour du graphe ===
def update_graph():
    global pos, node_labels, edge_labels
    ax.clear()

    if len(G.nodes) == 0:
        ax.text(0.5, 0.5, "Aucun graphe chargé", ha='center', va='center', transform=ax.transAxes, fontsize=16)
        canvas.draw()
        return

    # Layout fixe ou réutilisé
    if not pos or len(pos) != len(G.nodes):
        pos = nx.spring_layout(G, k=10.0/len(G)**0.5, iterations=50, seed=42)

    degrees = dict(G.degree())
    node_sizes = [500 * (1 + degrees[n]**0.8) for n in G.nodes()]

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color='lightblue', node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.6, width=1.5)
    nx.draw_networkx_labels(G, pos, labels=node_labels, ax=ax, font_size=9, font_weight='bold')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=ax, font_color='red', font_size=7)

    ax.set_title(os.path.basename(current_file) if current_file else "Graphe", fontsize=14)
    canvas.draw()

# === Chargement d'un fichier JSON ===
def load_json_file(filepath):
    global G, pos, node_labels, edge_labels, current_file
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        G = nx.Graph()
        for person in data:
            node_id = person["id"]
            label = person.get("nom_complet", node_id)
            G.add_node(node_id, label=label)
            for rel in person.get("relations", []):
                G.add_edge(node_id, rel["id"], label=rel.get("type_de_la_relation", ""))

        node_labels = {n: G.nodes[n].get('label', n) for n in G.nodes}
        edge_labels = nx.get_edge_attributes(G, 'label')
        current_file = filepath
        pos = {}  # Forcer recalcul du layout
        update_graph()
    except Exception as e:
        ax.clear()
        ax.text(0.5, 0.5, f"Erreur:\n{e}", ha='center', va='center', transform=ax.transAxes, fontsize=12, color='red')
        canvas.draw()

# === Mise à jour de la liste des fichiers ===
def update_file_list():
    if not os.path.exists(DOSSIER_JSON):
        return

    files = sorted([f for f in os.listdir(DOSSIER_JSON) if f.endswith(".json")])
    current_selection = listbox.curselection()

    listbox.delete(0, tk.END)
    for file in files:
        listbox.insert(tk.END, file)

    # Restaurer la sélection si possible
    if current_selection and current_selection[0] < len(files):
        listbox.selection_set(current_selection[0])
        if current_file and os.path.basename(current_file) == files[current_selection[0]]:
            return  # déjà chargé

    # Charger le premier fichier au démarrage
    if files and listbox.size() > 0:
        listbox.selection_set(0)
        first_file = os.path.join(DOSSIER_JSON, files[0])
        if current_file != first_file:
            load_json_file(first_file)

# === Clic sur un fichier ===
def on_file_select(event):
    selection = listbox.curselection()
    if not selection:
        return
    filename = listbox.get(selection[0])
    filepath = os.path.join(DOSSIER_JSON, filename)
    if current_file != filepath:
        load_json_file(filepath)

listbox.bind('<<ListboxSelect>>', on_file_select)

# === Interactions : déplacer les nœuds ===
def on_press(event):
    global selected_node
    if event.inaxes != ax or not pos:
        return
    for node, (x, y) in pos.items():
        dist = (event.xdata - x)**2 + (event.ydata - y)**2
        if dist < 0.02:
            selected_node = node
            break

def on_release(event):
    global selected_node
    selected_node = None

def on_motion(event):
    global selected_node
    if selected_node is None or event.inaxes != ax or not pos:
        return
    pos[selected_node] = (event.xdata, event.ydata)
    update_graph()

fig.canvas.mpl_connect('button_press_event', on_press)
fig.canvas.mpl_connect('button_release_event', on_release)
fig.canvas.mpl_connect('motion_notify_event', on_motion)

# === Thread de surveillance du dossier ===
def monitor_folder():
    global stop_monitor
    last_files = set()
    while not stop_monitor:
        if not os.path.exists(DOSSIER_JSON):
            time.sleep(2)
            continue
        try:
            current_files = set(f for f in os.listdir(DOSSIER_JSON) if f.endswith(".json"))
            if current_files != last_files:
                last_files = current_files
                root.after(0, update_file_list)
        except Exception as e:
            pass  # ignore erreurs temporaires
        time.sleep(2)

def on_closing():
    global stop_monitor
    stop_monitor = True
    time.sleep(0.1)  # attendre que le thread s'arrête
    root.quit()      # arrête mainloop
    root.destroy()   # détruit la fenêtre
    sys.exit(0)      # quitte Python proprement

# === LIAISON À LA FERMETURE ===
root.protocol("WM_DELETE_WINDOW", on_closing)

# Lancer la surveillance en arrière-plan
threading.Thread(target=monitor_folder, daemon=True).start()

# === Initialisation ===
update_file_list()

# === Lancement ===
root.mainloop()