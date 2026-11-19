"""Offline unit tests (no network): run with `python3 -m pytest tests -q` from the skill folder."""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import canonical_team, season_code  # noqa: E402
from fetch_data import american_to_decimal  # noqa: E402
from model import fit, markets_from_matrix  # noqa: E402
from odds_tools import analyse_market, devig, kelly_stake, overround  # noqa: E402
from slip import build_slip  # noqa: E402

BOOK = {"1": 1.80, "X": 3.60, "2": 4.50}


@pytest.mark.parametrize("method", ["multiplicative", "power", "shin"])
def test_devig_removes_margin(method):
    fair = devig(BOOK, method)
    assert sum(fair.values()) == pytest.approx(1.0, abs=1e-6)
    assert overround(BOOK) > 0


def test_power_devig_takes_more_margin_from_the_outsider():
    mult, power = devig(BOOK, "multiplicative"), devig(BOOK, "power")
    assert power["2"] < mult["2"]
    assert power["1"] > mult["1"]


def test_unknown_devig_method_raises():
    with pytest.raises(ValueError):
        devig(BOOK, "magic")


@pytest.mark.parametrize("us,dec", [(150, 2.5), (-200, 1.5), ("+100", 2.0), (None, None)])
def test_american_to_decimal(us, dec):
    assert american_to_decimal(us) == dec


def test_kelly_is_zero_without_edge_and_capped_with_edge():
    assert kelly_stake(0.40, 2.0) == 0.0
    assert kelly_stake(0.80, 2.0, fraction=1.0, cap=0.02) == 0.02


def test_surebet_and_outlier_are_flagged():
    books = {"A": {"1": 2.30, "X": 3.40, "2": 3.20}, "B": {"1": 2.00, "X": 3.90, "2": 3.90},
             "C": {"1": 2.05, "X": 3.40, "2": 3.80}}
    result = analyse_market("1X2", {"1": 0.45, "X": 0.27, "2": 0.28}, books)
    kinds = {a["tipo"] for a in result["allerte"]}
    assert "SUREBET" in kinds
    assert "QUOTA FUORI LINEA" in kinds


def test_fair_market_has_no_alerts():
    books = {"A": {"1": 1.90, "X": 3.50, "2": 4.20}, "B": {"1": 1.91, "X": 3.45, "2": 4.25}}
    result = analyse_market("1X2", devig(books["A"]), books)
    assert result["allerte"] == []


def test_markets_from_matrix_are_consistent():
    m = np.outer([0.3, 0.4, 0.3], [0.5, 0.3, 0.2])
    out = markets_from_matrix(m)
    assert sum(out["1X2"].values()) == pytest.approx(1.0)
    assert out["DC"]["1X"] == pytest.approx(out["1X2"]["1"] + out["1X2"]["X"])
    assert out["OU2.5"]["Over 2.5"] + out["OU2.5"]["Under 2.5"] == pytest.approx(1.0)


def test_model_ranks_the_stronger_team_first_and_applies_news():
    start, matches = date(2026, 1, 1), []
    for week in range(30):
        day = start + timedelta(days=7 * week)
        matches += [
            {"date": day, "comp": "I1", "home": "Forte", "away": "Debole", "hg": 3, "ag": 0, "hxg": 2.5, "axg": 0.4},
            {"date": day, "comp": "I1", "home": "Debole", "away": "Medio", "hg": 0, "ag": 1, "hxg": 0.7, "axg": 1.3},
            {"date": day, "comp": "I1", "home": "Medio", "away": "Forte", "hg": 1, "ag": 2, "hxg": 1.0, "axg": 1.8},
        ]
    model = fit(matches, as_of=start + timedelta(days=7 * 31))
    assert [r["team"] for r in model.ratings()] == ["Forte", "Medio", "Debole"]

    base = model.predict("Forte", "Debole", "I1")
    assert base["markets"]["1X2"]["1"] > 0.6
    hurt = model.predict("Forte", "Debole", "I1", {"Forte": {"attacco": -0.5}})
    assert hurt["xg_home"] == pytest.approx(base["xg_home"] * 0.75, rel=0.02)  # clipped to -25%


def test_unknown_team_raises_keyerror():
    model = fit([{"date": date(2026, 1, 1), "comp": "I1", "home": "A", "away": "B", "hg": 1, "ag": 0}], as_of=date(2026, 2, 1))
    with pytest.raises(KeyError):
        model.predict("A", "Zeta", "I1")


def test_names_and_seasons():
    assert canonical_team("Internazionale") == "Inter"
    assert canonical_team("AS Roma") == "Roma"
    assert canonical_team("US Lecce", {"Lecce", "Lazio"}) == "Lecce"
    assert season_code(date(2026, 11, 19)) == "2627"
    assert season_code(date(2027, 3, 1)) == "2627"


def test_slip_keeps_one_pick_per_match():
    row = {"p_modello": 0.6, "p_mercato": 0.55, "p_finale": 0.56, "quota_equa": 1.79, "book": "X"}
    analysis = {"partite": [{"partita": "A - B", "mercati": [
        {"mercato": "1X2", "righe": [{**row, "selezione": "1", "miglior_quota": 2.0, "ev": 0.12}]},
        {"mercato": "DC", "righe": [{**row, "selezione": "1X", "miglior_quota": 1.9, "ev": 0.06}]},
    ]}]}
    slip = build_slip(analysis, bankroll=100)
    assert len(slip["singole_valore"]) == 1
    assert slip["singole_valore"][0]["selezione"] == "1"
    assert slip["multipla"] is None


def test_double_chance_uses_the_1x2_consensus_and_never_flags_a_surebet():
    books = {"Snai": {"1X": 1.30, "X2": 1.60, "12": 1.25}}
    fair = {"1X": 0.70, "X2": 0.55, "12": 0.75}
    result = analyse_market("DC", {"1X": 0.72, "X2": 0.53, "12": 0.75}, books, fair_override=fair)
    assert result["fonte_mercato"] == "derivato da 1X2"
    assert all(a["tipo"] != "SUREBET" for a in result["allerte"])
    assert result["righe"][0]["p_mercato"] == 0.70

    alone = analyse_market("DC", {"1X": 0.72, "X2": 0.53, "12": 0.75}, books)
    assert alone["righe"][0]["p_mercato"] is None


def test_league_offset_keeps_a_small_league_champion_below_a_big_league_side():
    start, matches = date(2026, 1, 1), []
    for week in range(20):
        day = start + timedelta(days=7 * week)
        matches += [
            {"date": day, "comp": "BIG", "home": "Grande1", "away": "Grande2", "hg": 1, "ag": 1},
            {"date": day, "comp": "BIG", "home": "Grande2", "away": "Grande1", "hg": 1, "ag": 1},
            {"date": day, "comp": "SMALL", "home": "Piccola1", "away": "Piccola2", "hg": 4, "ag": 0},
            {"date": day, "comp": "SMALL", "home": "Piccola2", "away": "Piccola1", "hg": 0, "ag": 4},
        ]
        if week % 2 == 0:  # European ties: the small-league champion loses to the big-league side
            matches.append({"date": day, "comp": "UCL", "home": "Piccola1", "away": "Grande2", "hg": 0, "ag": 2})
            matches.append({"date": day, "comp": "UCL", "home": "Grande2", "away": "Piccola1", "hg": 2, "ag": 0})
    model = fit(matches, as_of=start + timedelta(days=150), domestic_comps=("BIG", "SMALL"))
    pred = model.predict("Grande2", "Piccola1", "UCL")["markets"]["1X2"]
    assert pred["1"] > pred["2"]


@pytest.mark.parametrize("espn,fd", [("Union St.-Gilloise", "St. Gilloise"), ("Celta Vigo", "Celta"),
                                     ("Vitória de Guimaraes", "Guimaraes"), ("Ajax Amsterdam", "Ajax")])
def test_european_spellings_map_to_football_data(espn, fd):
    assert canonical_team(espn) == fd


def test_combo_selections_are_consistent_and_calibrated_to_the_market():
    from combo import all_selections, calibrated_matrix

    fair = {"1": 0.60, "X": 0.24, "2": 0.16}
    matrix = calibrated_matrix(1.2, 1.2, -0.05, fair, (2.5, 0.55), model_weight=0.0)
    sel = all_selections(matrix)
    assert sel["Segno 1"] == pytest.approx(0.60, abs=0.01)
    assert sel["Over 2.5"] == pytest.approx(0.55, abs=0.02)
    assert sel["Segno 1"] + sel["Segno X"] + sel["Segno 2"] == pytest.approx(1.0)
    assert sel["1X + Over 1.5"] <= min(sel["Segno 1X"], sel["Over 1.5"])
    assert sel["GG"] + sel["NG"] == pytest.approx(1.0)


def test_three_slips_respect_tier_bands():
    from schedine import TIERS, build_three_slips

    match = {"partita": "A - B", "data": "2026-11-21", "modello": {"xg_home": 1.6, "xg_away": 0.9},
             "mercati": [{"mercato": "1X2", "consenso": {"1": 0.55, "X": 0.26, "2": 0.19},
                          "righe": [{"selezione": s, "p_modello": p, "p_mercato": p, "miglior_quota": 1 / p}
                                    for s, p in (("1", 0.55), ("X", 0.26), ("2", 0.19))]}]}
    analysis = {"modello": {"rho": -0.03}, "partite": [{**match, "partita": f"T{i} - U{i}"} for i in range(8)]}
    result = build_three_slips(analysis)
    for name, slip in result["schedine"].items():
        for leg in slip["selezioni"]:
            assert TIERS[name]["p_min"] <= leg["prob"] <= TIERS[name]["p_max"]
    assert result["schedine"]["facile"]["probabilita"] > result["schedine"]["difficile"]["probabilita"]
