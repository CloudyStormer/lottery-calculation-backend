from app.catalog import GAMES, public_catalog


def test_catalog_contains_official_number_games() -> None:
    assert set(GAMES) == {"dlt", "pl3", "pl5", "qxc", "ssq", "fc3d", "qlc", "kl8"}
    catalog = public_catalog()
    assert {issuer["id"] for issuer in catalog["issuers"]} == {"sports", "welfare"}
    assert len(catalog["games"]) == 8


def test_happy8_has_ten_official_pick_options() -> None:
    assert [play.ticket_size for play in GAMES["kl8"].plays] == list(range(1, 11))


def test_single_ticket_probability_facts_are_not_confused_with_outcome_types() -> None:
    assert "17,721,088" in GAMES["ssq"].plays[0].odds_text
    assert "2,035,800" in GAMES["qlc"].plays[0].odds_text
    assert "6 / 1000" in GAMES["fc3d"].plays[2].odds_text
    assert "并非单注中奖率" in GAMES["fc3d"].plays[2].odds_text
