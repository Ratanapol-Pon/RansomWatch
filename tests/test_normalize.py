from packages.scraper.normalize import normalize_name


def test_strips_thai_and_english_suffixes():
    assert normalize_name("Siam Stabilizers and Chemicals Co., Ltd. / SSC") == (
        "siam stabilizers and chemicals ssc"
    )
    assert normalize_name("Bangkok Airways PCL") == "bangkok airways"
    assert normalize_name("บริษัท ตัวอย่าง จำกัด") == "บริษัท ตัวอย่าง"
    assert normalize_name("ABC (Thailand) มหาชน") == "abc thailand"


def test_collapses_punctuation_and_whitespace():
    assert normalize_name("  Foo-Bar,  Inc.! ") == "foo bar inc"
    assert normalize_name("A   B") == "a b"


def test_empty_and_none():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""
