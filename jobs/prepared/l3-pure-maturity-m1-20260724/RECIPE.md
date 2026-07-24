# L3-PURE maturité M1 — préflight HOME

Parent immuable : C0 A-G3 de `ccx33-0790-l3-pure-c0-a-v1`.

Le préflight `home-0936` vérifie les trois corpus historiques et leurs sidecars,
construit 8cf, installe NumPy `1.26.4` et SciPy `1.14.1` dans un environnement
virtuel propre au job, génère 20 000 records sous Q00 et exécute un mini-fit
warm-starté. Il publie débit, ETA 2M et pic RSS.

Il ne produit aucun candidat M1 et n’autorise aucune promotion.

Le job `home-0937-l3-pure-m1-train-v1` exécute ensuite les trois bras sur le
parent immuable C0 A-G3 : F500 reçoit la tranche fraîche commune de 500k,
F2M reçoit cette même tranche plus 1,5M frais, et R2M reçoit cette même tranche
plus exactement les corpus C0 G1-G3 et leurs sidecars JSM. Les splits sont
groupés par ouverture. La recette est WDL terminal, 8cf/Q00, départs standards,
sans TOP3 ni reweight V2. Après le diagnostic `home-0938` (`MAXITER` à 60),
la reprise `home-0939` réutilise les sources fraîches 0937 vérifiées, porte le
budget à 200 et exige le statut de convergence `success` fourni par SciPy.
Atteindre ce nouveau plafond reste un échec. Aucun bras n’est promu.
