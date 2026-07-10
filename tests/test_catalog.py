from app.catalog import GAMES, public_catalog


def test_catalog_contains_official_number_games() -> None:
    assert set(GAMES) == {"dlt", "pl3", "pl5", "qxc", "ssq", "fc3d", "qlc", "kl8"}
    catalog = public_catalog()
    assert {issuer["id"] for issuer in catalog["issuers"]} == {"sports", "welfare"}
    assert len(catalog["games"]) == 8


def test_happy8_has_ten_official_pick_options() -> None:
    assert [play.ticket_size for play in GAMES["kl8"].plays] == list(range(1, 11))
