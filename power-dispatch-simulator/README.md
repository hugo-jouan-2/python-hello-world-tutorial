# power-dispatch-simulator

Simulation du dispatch horaire d'une centrale simple à partir d'un prix de marché.

## Modèle

La centrale a trois états, et l'état est choisi heure par heure en fonction du prix :

| Prix (EUR/MWh)  | État | Production |
| --------------- | ---- | ---------- |
| `prix < 60`     | OFF  | 0 MW       |
| `60 <= prix < 80` | PMIN | 50 MW    |
| `prix >= 80`    | PMAX | 100 MW     |

Le coût variable est de 60 EUR/MWh, et le PnL horaire vaut :

```
PnL = (prix - 60) * production - co?t de d?marrage
```

## Installation

Prérequis : Python >= 3.11 et [Poetry](https://python-poetry.org/).

```bash
cd power-dispatch-simulator
poetry install
```

## Lancer l'exemple

Le jeu de données d'exemple est `data/prices.csv` (24 heures) :

```bash
poetry run power-dispatch
```

Avec un autre fichier de prix (CSV avec les colonnes `hour,price_eur_per_mwh`) :

```bash
poetry run power-dispatch chemin/vers/prices.csv
```

## Tests et lint

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format .
```

## Structure

```
src/power_dispatch/dispatch.py  logique métier (états, production, PnL, lecture CSV)
src/power_dispatch/cli.py       point d'entrée, affiche le tableau horaire et les totaux
data/prices.csv                 prix d'exemple sur 24 heures
tests/test_dispatch.py          tests pytest
```

## Contraintes temporelles et démarrages

`dispatch_day(prices, overrides=None)` conserve les seuils de prix ci-dessus,
mais suit maintenant les transitions entre OFF et ON (PMIN ou PMAX).

- Chaque passage OFF → PMIN ou PMAX coûte **500 EUR**, déduits du PnL
  de l'heure du démarrage, y compris à la première heure.
- Après un démarrage, la centrale reste ON au moins **3 heures**.
  Si le prix demande OFF pendant ce délai, elle produit à PMIN.
- Après un arrêt, elle reste OFF au moins **2 heures**.
- L'heure de transition compte comme première heure du délai.
  Un passage PMIN ↔ PMAX ne redémarre ni le compteur ni la centrale.

```text
PnL horaire = (prix - 60) × production - (500 si démarrage, sinon 0)
```

La centrale est initialement OFF avec son minimum OFF déjà satisfait.
La simulation ne prolonge pas les données : un démarrage en fin de série
peut laisser un engagement ON à poursuivre au-delà de l'horizon.
Chaque appel est une simulation indépendante.
La stratégie reste fondée sur les seuils, sans optimisation des profits futurs :
un démarrage peut donc rendre une heure déficitaire même avec un prix supérieur à 60.
Les fonctions unitaires `choose_state`, `hourly_pnl` et `dispatch_hour` conservent
leur calcul sans historique ; utiliser `dispatch_day` pour les contraintes et coûts de démarrage.

## Manual override

En Python, fournir un dictionnaire indexé par position horaire, à partir de zéro :

```python
from power_dispatch import State, dispatch_day, summarize

results = dispatch_day([90, 90, 40, 70], overrides={1: State.OFF, 2: "PMAX"})
print(summarize(results))
```

Valeurs acceptées : `OFF`, `PMIN`, `PMAX` (chaînes ou `State`). Une clé absente
ou une valeur `None` laisse agir la logique automatique.
Un override **prévaut sur les durées minimales** pour forcer effectivement l'état.
Une transition forcée initialise le compteur de la nouvelle phase ON/OFF ;
les heures suivantes sans override respectent ce compteur. Les coûts de démarrage
restent applicables. Les états invalides et indices hors série sont rejetés.
Les indices désignent les positions après tri du CSV par `hour`, comme dans
l'interface existante, et non les étiquettes originales du CSV.

Depuis la CLI, répéter l'option pour plusieurs heures :

```bash
poetry run power-dispatch --override 6=OFF --override 7=PMAX
poetry run power-dispatch chemin/vers/prices.csv --override 0=PMIN
```

Les heures dupliquées et overrides mal formés sont rejetés par la CLI.

## Résumé final

La CLI affiche l'énergie totale en MWh, le PnL net en EUR, le nombre de démarrages
et les heures OFF / PMIN / PMAX. Chaque ligne représente une heure complète.
L'API `summarize(results)` retourne ces valeurs dans un `DispatchSummary` ;
`HourlyDispatch.started` indique les démarrages. Les fonctions existantes
`total_production` et `total_pnl` restent disponibles.

Pour les 24 heures de l'exemple sans override : **1 100 MWh**, **24 900 EUR**,
**2 démarrages**, **9 / 8 / 7 heures OFF / PMIN / PMAX**.

Les tests couvrent les seuils existants, les deux types de démarrage, les durées
minimales, les transitions forcées, les erreurs d'override, l'horizon tronqué,
les résumés vides et la sortie CLI.
