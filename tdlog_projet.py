import numpy as np
import matplotlib.pyplot as plt 
from scipy.stats import poisson


"""
Les scores ELO sont stockés sous forme de dictionnaire
"""
HOME_BONUS = 100
ELO = {
    "AEK" : 1695,
    "Arsenal" : 2047,
    "Aston Villa" : 1899,
    "Atleti" : 1910,
    "Dortmund" : 1899,
    "Barcelona" : 2032,
    "Bayern" : 2046,
    "Bodo Glim" : 1779,
    "Brugge" : 1839,
    "Como" : 1838,
    "Fenerbahçe" : 1779, 
    "Feyenoord" : 1716,
    "Galatasaray" : 1824,
    "Inter" : 1949,
    "LASK" : 1643,
    "Leipzig" : 1832,
    "Lens" : 1779,
    "Lille" : 1780,
    "Liverpool" : 1937,
    "Man City" : 2002,
    "Man Und" : 1851,
    "Napoli" : 1818,
    "PSG" : 1989,
    "Porto" : 1843,
    "PSV" : 1782,
    "Real Betis" : 1829,
    "Real Madrid" : 2001,
    "Roma" : 1865,
    "Bratislava" : 1541,
    "Sabah" : 1558,
    "Shakhtar" : 1687,
    "Slavia Praha" : 1744,
    "Sporting CP" : 1863,
    "Viking" : 1715, 
    "Villareal" : 1789
}


"""
Definition des fonctions de base
"""

def win_exp(elo1 : float, elo2 : float) -> float:
    x = -(elo1-elo2)/400
    W = 1/(1+10**x)
    return W

#field est un int qui vaut 0 par défaut lorsque le match est en lieu neutre, 1 a domicile pour le team 1 et 2 sinon
def lam_neutral(W: float) -> float:
    if W <= 0.9:
        return 3.90388*W**4 - 0.58486*W**3 - 2.98315*W**2 + 3.13160*W + 0.33193
    d = W - 0.9
    return 308097.45501*d**4 - 42803.04696*d**3 + 2116.35304*d**2 - 9.61869*d + 2.86899


def lam_home(W_host: float) -> float:
    if W_host <= 0.9:
        return -5.42301*W_host**4 + 15.49728*W_host**3 - 12.6499*W_host**2 + 5.36198*W_host + 0.22863
    d = W_host - 0.9
    return 231098.16153*d**4 - 30953.10199*d**3 + 1347.51495*d**2 - 1.63074*d + 2.54747


def lam_away(W_host: float) -> float:   # attention : W de l'HÔTE
    if W_host < 0.1:
        d = W_host - 0.1
        return 90173.57949*d**4 + 10064.38612*d**3 + 218.6628*d**2 - 11.06198*d + 2.28291
    return -1.25010*W_host**4 - 1.99984*W_host**3 + 6.54946*W_host**2 - 5.83979*W_host + 2.80352


def lambdas(team1: str, team2: str, field: int = 0) -> tuple[float, float]:
    """field : 0 = neutre, 1 = team1 à domicile, 2 = team2 à domicile."""
    if field == 0:
        W = win_exp(ELO[team1], ELO[team2])
        return lam_neutral(W), lam_neutral(1 - W)

    if field == 1:
        W_host = win_exp(ELO[team1] + HOME_BONUS, ELO[team2])
        return lam_home(W_host), lam_away(W_host)

    if field == 2:
        W_host = win_exp(ELO[team2] + HOME_BONUS, ELO[team1])
        return lam_away(W_host), lam_home(W_host)

    raise ValueError("field doit valoir 0, 1 ou 2")


def match(team1 : str, team2 : str, field = 0) -> (float, float):

    lam_a, lam_b = lambdas(team1, team2, field)

    rng = np.random.default_rng()
    buts_a = rng.poisson(lam_a)
    buts_b = rng.poisson(lam_b)

    return buts_a, buts_b


"""
TEST DE COHERENCE
"""

print(ELO["PSG"])
print(win_exp(ELO["PSG"], ELO["Real Madrid"]))
print(win_exp(ELO["Real Madrid"], ELO["PSG"]))


D = []
P = []
M = []
field = 1
for k in range(100000):
    
    a, b = match("PSG", "Real Madrid", field)
    if a > b :
        P.append(1)
    if b > a :
        M.append(1)
    D.append(a-b)

print(np.mean(D))
print(len(P)/100000)
print(len(M)/100000)

print("FIN")