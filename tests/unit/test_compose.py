from finplan.config.compose import compose, deep_merge


def test_scalar_replace_and_dict_merge():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    out = compose(base, {"a": 9, "b": {"y": 3}})
    assert out == {"a": 9, "b": {"x": 1, "y": 3}}


def test_id_list_merge_by_id():
    base = {"expenses": [{"id": "living", "annual": 100}, {"id": "mortgage", "annual": 30}]}
    overlay = {"expenses": [{"id": "living", "annual": 120}]}
    out = compose(base, overlay)
    assert out["expenses"] == [{"id": "living", "annual": 120}, {"id": "mortgage", "annual": 30}]


def test_id_list_append_new():
    base = {"events": [{"id": "a", "cash": 1}]}
    out = compose(base, {"events": [{"id": "b", "cash": 2}]})
    assert [e["id"] for e in out["events"]] == ["a", "b"]


def test_id_list_remove():
    base = {"expenses": [{"id": "mortgage", "annual": 30}, {"id": "living", "annual": 100}]}
    out = compose(base, {"expenses": [{"id": "mortgage", "remove": True}]})
    assert out["expenses"] == [{"id": "living", "annual": 100}]


def test_people_merge_by_name():
    base = {"household": {"people": [{"name": "sam", "retirement_age": 62, "birth_year": 1985}]}}
    out = compose(base, {"household": {"people": [{"name": "sam", "retirement_age": 55}]}})
    assert out["household"]["people"] == [
        {"name": "sam", "retirement_age": 55, "birth_year": 1985}
    ]


def test_plain_list_replaces():
    base = {"policies": {"withdrawal": {"order": ["cash", "taxable"]}}}
    out = compose(base, {"policies": {"withdrawal": {"order": ["taxable"]}}})
    assert out["policies"]["withdrawal"]["order"] == ["taxable"]


def test_multiple_overlays_left_to_right():
    base = {"a": 1}
    assert compose(base, {"a": 2}, {"a": 3}) == {"a": 3}


def test_base_not_mutated():
    base = {"expenses": [{"id": "x", "annual": 1}]}
    compose(base, {"expenses": [{"id": "x", "annual": 2}]})
    assert base["expenses"][0]["annual"] == 1


def test_deep_merge_nested_id_lists_inside_dicts():
    base = {"outer": {"items": [{"id": "k", "v": {"a": 1, "b": 2}}]}}
    out = deep_merge(base, {"outer": {"items": [{"id": "k", "v": {"b": 9}}]}})
    assert out["outer"]["items"][0]["v"] == {"a": 1, "b": 9}


def test_aca_flag_merges_onto_existing_stream():
    # the aca_subsidized overlay pattern: flip the flag on a stream defined elsewhere
    base = {"expenses": [{"id": "pre-medicare-health", "annual": 24000,
                          "start": "retirement", "end": "age:alex:65"}]}
    out = compose(base, {"expenses": [{"id": "pre-medicare-health", "aca": True}]})
    assert out["expenses"] == [{"id": "pre-medicare-health", "annual": 24000,
                                "start": "retirement", "end": "age:alex:65",
                                "aca": True}]
