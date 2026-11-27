"""Creator pages: the store, the manage key, the API and the team's script.

Every test runs against both store backends.
"""

import hashlib
import json
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import creator_store
import quest_store
import rate_limit
from curated_quests import CURATED_CITIES
from main import app, origins
from models import Quest
from scripts.creator_page import main as script
from tests.test_quest_store import _FakeDocument, _FakeFirestore, _FakeSnapshot


class _Snapshot(_FakeSnapshot):
    def __init__(self, doc_id: str, data: dict | None) -> None:
        super().__init__(data)
        self.id = doc_id


class _Document(_FakeDocument):
    """Adds what creator pages use: list transforms, get_all and stream."""

    def get(self):
        return _Snapshot(self._key[1], self._docs.get(self._key))

    def update(self, data: dict) -> None:
        from google.cloud.firestore_v1.transforms import ArrayRemove, ArrayUnion

        plain = {}
        for field, value in data.items():
            if isinstance(value, (ArrayUnion, ArrayRemove)):
                super().update({})  # raises NotFound for a missing document
                current = list(self._docs[self._key].get(field) or [])
                if isinstance(value, ArrayUnion):
                    current += [v for v in value.values if v not in current]
                else:
                    current = [v for v in current if v not in value.values]
                self._docs[self._key][field] = current
            else:
                plain[field] = value
        super().update(plain)


class _Firestore(_FakeFirestore):
    def collection(self, name: str):
        return SimpleNamespace(
            document=lambda doc_id: _Document(self.docs, (name, doc_id)),
            stream=lambda: [
                _Snapshot(key[1], data)
                for key, data in list(self.docs.items())
                if key[0] == name
            ],
        )

    def get_all(self, refs):
        # Real Firestore promises no order.
        return [ref.get() for ref in reversed(list(refs))]


@pytest.fixture(autouse=True, params=["sqlite", "firestore"])
def store(request, tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_STORE_BACKEND", request.param)
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quests.db"))
    fake = _Firestore()
    monkeypatch.setattr("quest_store.firestore_client", lambda: fake)

    def everything_stored() -> str:
        if request.param == "firestore":
            return json.dumps({"/".join(k): v for k, v in fake.docs.items()})
        return b"".join(p.read_bytes() for p in tmp_path.glob("quests.db*")).decode(
            "latin-1"
        )

    return SimpleNamespace(backend=request.param, dump=everything_stored)


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _quest(title: str = "Evening out", **changes) -> Quest:
    base = CURATED_CITIES[0].quests[0].model_dump()
    return Quest.model_validate({**base, "title": title, **changes})


def _shared(title: str = "Evening out", **changes) -> str:
    return quest_store.store_quest(_quest(title, **changes))


def _page(handle: str = "priya", name: str = "Priya") -> str:
    return creator_store.create_creator(handle, name)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _add(client, token: str, short_id: str):
    return client.post(
        "/api/creator/me/quests", headers=_auth(token), json={"short_id": short_id}
    )


# ── Handles ──


@pytest.mark.parametrize("handle", ["abc", "priya-eats", "a1b", "x" * 30, "99-bites"])
def test_good_handles(handle):
    assert creator_store.handle_problem(handle) is None


@pytest.mark.parametrize(
    "handle",
    ["", "ab", "x" * 31, "-abc", "abc-", "Priya", "pri_ya", "pri ya", "pri.ya", "priya\n", "préya"],
)
def test_bad_handles(handle):
    assert creator_store.handle_problem(handle)
    with pytest.raises(ValueError):
        creator_store.create_creator(handle, "Name")


@pytest.mark.parametrize(
    "handle",
    ["admin", "manage", "api", "by", "quest", "create", "moodyeat", "official", "support", "help"],
)
def test_reserved_handles(handle):
    with pytest.raises(ValueError):
        creator_store.create_creator(handle, "Name")


def test_a_handle_can_only_be_taken_once():
    first = _page()
    with pytest.raises(creator_store.HandleTaken):
        _page()
    assert creator_store.creator_for_token(first) is not None


# ── The manage key ──


def test_the_key_is_32_random_bytes_and_only_its_hash_is_stored(store):
    token = _page()
    handle, secret = token.split(".", 1)
    assert handle == "priya"
    # 32 bytes in URL-safe base64 without padding.
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", secret)
    assert _page("other").split(".", 1)[1] != secret
    dumped = store.dump()
    assert secret not in dumped
    assert hashlib.sha256(token.encode()).hexdigest() in dumped


def test_keys_are_compared_in_constant_time(monkeypatch):
    token = _page()
    compared = []
    real = creator_store.hmac.compare_digest
    monkeypatch.setattr(
        creator_store.hmac,
        "compare_digest",
        lambda a, b: compared.append((a, b)) or real(a, b),
    )
    assert creator_store.creator_for_token(token) is not None
    assert creator_store.creator_for_token(token + "x") is None
    assert len(compared) == 2


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Basic {token}",
        "{token}",
        "Bearer priya.wrong-secret-wrong-secret-wrong-secret-123",
        "Bearer {token}x",
        "Bearer nobody.{secret}",
        "Bearer other.{secret}",
        "Bearer {secret}",
        "Bearer ../../etc.{secret}",
    ],
)
def test_anything_but_the_right_key_gets_a_401(client, header):
    token = _page()
    _page("other")
    headers = {}
    if header is not None:
        headers["Authorization"] = header.format(token=token, secret=token.split(".")[1])
    for method, path, body in [
        ("GET", "/api/creator/me", None),
        ("PATCH", "/api/creator/me", {"bio": "hacked"}),
        ("POST", "/api/creator/me/quests", {"short_id": _shared()}),
        ("DELETE", "/api/creator/me/quests/abcd2345", None),
    ]:
        res = client.request(method, path, headers=headers, json=body)
        assert res.status_code == 401, (method, path)
        assert res.json()["detail"]["code"] == "bad_key"
        assert "doesn't work" in res.json()["detail"]["message"]
    page = creator_store.get_creator("priya")
    assert page.bio == "" and page.quest_ids == ()


def test_rotating_stops_the_old_key(client):
    old = _page()
    new = creator_store.rotate_token("priya")
    assert new != old
    assert client.get("/api/creator/me", headers=_auth(old)).status_code == 401
    assert client.get("/api/creator/me", headers=_auth(new)).status_code == 200
    assert creator_store.rotate_token("nobody") is None


def test_the_key_is_never_logged_or_sent_back(client, caplog):
    caplog.set_level(logging.DEBUG)
    token = _page()
    secret = token.split(".")[1]
    short_id = _shared()
    bodies = [
        client.get("/api/creator/me", headers=_auth(token)).text,
        _add(client, token, short_id).text,
        client.patch("/api/creator/me", headers=_auth(token), json={"bio": "b"}).text,
        client.get("/api/creators/priya").text,
        client.get("/api/creator/me", headers=_auth(token + "x")).text,
    ]
    token_hash = creator_store.get_creator("priya").token_hash
    for text in bodies:
        assert secret not in text and token_hash not in text
    ours = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert not [m for m in ours if secret in m]


def test_my_page_is_not_cached(client):
    res = client.get("/api/creator/me", headers=_auth(_page()))
    assert res.headers["cache-control"] == "no-store"


# ── Adding and removing quests ──


def test_added_quests_are_listed_newest_first(client):
    token = _page()
    ids = [_shared(f"Quest {n}") for n in range(3)]
    for short_id in ids:
        assert _add(client, token, short_id).json()["added"] is True
    titles = [q["title"] for q in client.get("/api/creators/priya").json()["quests"]]
    assert titles == ["Quest 2", "Quest 1", "Quest 0"]
    mine = client.get("/api/creator/me", headers=_auth(token)).json()
    assert [q["short_id"] for q in mine["quests"]] == ids[::-1]


def test_a_duplicate_is_ignored(client):
    token = _page()
    first, second = _shared("First"), _shared("Second")
    _add(client, token, first)
    _add(client, token, second)
    res = _add(client, token, first)
    assert res.status_code == 200
    assert res.json()["added"] is False
    # Not moved to the top either.
    assert [q["title"] for q in res.json()["page"]["quests"]] == ["Second", "First"]


def test_a_quest_that_does_not_exist_is_a_clear_error(client):
    res = _add(client, _page(), "abcd2345")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "quest_not_found"
    assert "no quest at that link" in res.json()["detail"]["message"]


def test_something_that_is_not_an_id_is_refused(client):
    assert _add(client, _page(), "../secrets").status_code == 422


def test_the_fifty_first_quest_is_refused(client):
    token = _page()
    ids = [_shared(f"Quest {n}") for n in range(51)]
    for short_id in ids[:50]:
        creator_store.add_quest("priya", short_id)
    res = _add(client, token, ids[50])
    assert res.status_code == 409
    assert res.json()["detail"] == {
        "code": "page_full",
        "message": "Your page has 50 quests, the most it can hold. Remove one to add another.",
    }
    assert len(creator_store.get_creator("priya").quest_ids) == 50
    # One already there is still just a duplicate, not an error.
    assert _add(client, token, ids[0]).json()["added"] is False
    client.delete(f"/api/creator/me/quests/{ids[0]}", headers=_auth(token))
    assert _add(client, token, ids[50]).json()["added"] is True


def test_removing_a_quest_keeps_its_share_link(client):
    token = _page()
    short_id = _shared("Still shared")
    _add(client, token, short_id)
    res = client.delete(f"/api/creator/me/quests/{short_id}", headers=_auth(token))
    assert res.status_code == 200 and res.json()["quests"] == []
    assert client.get("/api/creators/priya").json()["quests"] == []
    assert client.get(f"/api/quest/stored/{short_id}").status_code == 200
    # Removing it twice is harmless.
    again = client.delete(f"/api/creator/me/quests/{short_id}", headers=_auth(token))
    assert again.status_code == 200


def test_a_taken_down_quest_leaves_the_public_page(client):
    token = _page()
    doomed, kept = _shared("Doomed"), _shared("Kept")
    _add(client, token, doomed)
    _add(client, token, kept)
    quest_store.delete_quest(doomed)
    public = client.get("/api/creators/priya").json()["quests"]
    assert [q["title"] for q in public] == ["Kept"]
    mine = client.get("/api/creator/me", headers=_auth(token)).json()["quests"]
    assert [(q["short_id"], q["available"]) for q in mine] == [(kept, True), (doomed, False)]


# ── What the pages show ──


def test_reading_a_page_never_counts_a_quest_view(client):
    token = _page()
    short_id = _shared()
    _add(client, token, short_id)
    for _ in range(3):
        client.get("/api/creators/priya")
        client.get("/api/creator/me", headers=_auth(token))
    assert quest_store.fetch_quest(short_id, count_view=False).views == 0


def test_open_counts_and_page_views_are_for_the_owner_only(client):
    token = _page()
    short_id = _shared()
    _add(client, token, short_id)
    client.get(f"/api/quest/stored/{short_id}")
    client.get(f"/api/quest/stored/{short_id}")
    client.get("/api/creators/priya")
    client.get("/api/creators/priya?count_view=false")
    client.get("/api/creators/PRIYA")

    mine = client.get("/api/creator/me", headers=_auth(token)).json()
    assert mine["quests"][0]["opens"] == 2
    assert mine["page_views"] == 2

    public = client.get("/api/creators/priya").json()
    assert set(public) == {"handle", "display_name", "bio", "instagram", "quests"}
    assert set(public["quests"][0]) == {"short_id", "title", "made_by", "intro", "stops"}
    assert set(public["quests"][0]["stops"][0]) == {"name", "note"}


def test_only_words_someone_typed_are_shown(client):
    token = _page()
    base = CURATED_CITIES[0].quests[0].model_dump()
    stops = base["stops"]
    stops[0] = {**stops[0], "why_this_place": "Sit upstairs.", "note_by_creator": True}
    own = _shared("Mine", narrative="My intro.", narrative_by_creator=True, stops=stops, created_by="Rahul")
    automatic = _shared("Automatic")
    _add(client, token, automatic)
    _add(client, token, own)

    mine, auto = client.get("/api/creators/priya").json()["quests"]
    assert mine["intro"] == "My intro."
    assert mine["made_by"] == "Rahul"
    assert [s["note"] for s in mine["stops"]][:2] == ["Sit upstairs.", None]
    assert auto["intro"] is None
    assert all(s["note"] is None for s in auto["stops"])


def test_an_unknown_page_is_a_marked_404(client):
    for handle in ["nobody", "admin", "NOT_A_HANDLE"]:
        res = client.get(f"/api/creators/{handle}")
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "creator_not_found"


def test_profile_edits_are_tidied_and_limited(client):
    token = _page()
    res = client.patch(
        "/api/creator/me",
        headers=_auth(token),
        json={"display_name": "  Priya\n Eats ", "bio": "Coffee\r\nfirst.", "instagram": "@priya.eats_"},
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["display_name"], body["bio"], body["instagram"]) == (
        "Priya Eats",
        "Coffee first.",
        "priya.eats_",
    )
    # Only what is sent changes; an empty string clears.
    res = client.patch("/api/creator/me", headers=_auth(token), json={"instagram": ""})
    assert res.json()["instagram"] == "" and res.json()["bio"] == "Coffee first."


@pytest.mark.parametrize(
    "changes, code",
    [
        ({"display_name": "   "}, "bad_name"),
        ({"display_name": "x" * 41}, "bad_name"),
        ({"bio": "x" * 141}, "bad_bio"),
        ({"instagram": "https://instagram.com/priya"}, "bad_instagram"),
        ({"instagram": "instagram.com/priya"}, "bad_instagram"),
        ({"instagram": "javascript:alert(1)"}, "bad_instagram"),
        ({"instagram": "priya eats"}, "bad_instagram"),
        ({"instagram": "priya/../x"}, "bad_instagram"),
        ({"instagram": "priya?x=1"}, "bad_instagram"),
        ({"instagram": ".priya"}, "bad_instagram"),
        ({"instagram": "pri..ya"}, "bad_instagram"),
        ({"instagram": "priya."}, "bad_instagram"),
        ({"instagram": "p" * 31}, "bad_instagram"),
    ],
)
def test_bad_profile_edits_change_nothing(client, changes, code):
    token = _page()
    res = client.patch("/api/creator/me", headers=_auth(token), json=changes)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == code
    page = creator_store.get_creator("priya")
    assert (page.display_name, page.bio, page.instagram) == ("Priya", "", "")


def test_there_is_no_way_to_sign_up(client):
    for path in ["/api/creators", "/api/creator", "/api/creators/priya", "/api/creator/me"]:
        assert client.post(path, json={"handle": "priya"}).status_code in (401, 404, 405)
    assert creator_store.list_creators() == []


# ── Guessing keys ──


@pytest.fixture
def limited(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True, rate_limit_per_minute=60, suggest_rate_limit_per_minute=120
        ),
    )
    monkeypatch.setattr(rate_limit, "_limiters", {})
    monkeypatch.setattr(
        rate_limit,
        "_creator_key_failures",
        rate_limit._SlidingWindowLimiter(max_requests=10, window_seconds=600.0),
    )


def test_ten_wrong_keys_turn_a_client_away(client, limited):
    token = _page()
    bad = _auth("priya.nope")
    codes = [client.get("/api/creator/me", headers=bad).status_code for _ in range(11)]
    assert codes == [401] * 10 + [429]
    # Even the right key waits now, and so does every creator route.
    res = client.get("/api/creator/me", headers={**_auth(token), "Origin": origins[0]})
    assert res.status_code == 429
    assert res.json()["detail"]["code"] == "too_many"
    # The page can read the reply, so it can say why.
    assert res.headers["access-control-allow-origin"] == origins[0]
    # The public page and other people are untouched.
    assert client.get("/api/creators/priya").status_code == 200
    other = {**_auth(token), "X-Forwarded-For": "203.0.113.9"}
    assert client.get("/api/creator/me", headers=other).status_code == 200


def test_right_keys_are_never_counted(client, limited):
    token = _page()
    codes = {client.get("/api/creator/me", headers=_auth(token)).status_code for _ in range(30)}
    assert codes == {200}


# ── The team's script ──


def _links(output: str) -> tuple[str, str]:
    public = re.search(r"(\S+/by/\S+)", output).group(1)
    token = re.search(r"/manage#k=(\S+)", output).group(1)
    return public, token


def test_script_creates_a_page_and_shows_the_link_once(capsys, client):
    assert script(["create", "--handle", "priya", "--name", " Priya "]) == 0
    out = capsys.readouterr().out
    public, token = _links(out)
    assert public == "https://www.moodyeat.in/by/priya"
    assert f"https://www.moodyeat.in/manage#k={token}" in out
    assert out.count(token) == 1
    assert "Store: " in out
    assert client.get("/api/creator/me", headers=_auth(token)).json()["display_name"] == "Priya"

    assert script(["list"]) == 0
    listed = capsys.readouterr().out
    assert "priya" in listed and "Priya" in listed
    assert token.split(".")[1] not in listed
    assert creator_store.get_creator("priya").token_hash not in listed


def test_script_can_print_links_for_another_address(capsys):
    script(["--site", "http://localhost:5611/", "create", "--handle", "priya", "--name", "P"])
    out = capsys.readouterr().out
    assert "http://localhost:5611/by/priya" in out
    assert "http://localhost:5611/manage#k=priya." in out


def test_script_refuses_bad_input(capsys):
    assert script(["create", "--handle", "Admin!", "--name", "X"]) == 2
    assert script(["create", "--handle", "admin", "--name", "X"]) == 2
    assert script(["create", "--handle", "priya", "--name", "x" * 41]) == 2
    assert script(["create", "--handle", "priya", "--name", "  "]) == 2
    assert script(["create", "--handle", "priya", "--name", "P"]) == 0
    assert script(["create", "--handle", "priya", "--name", "P"]) == 1
    assert "taken" in capsys.readouterr().err


def test_script_rotates_a_key(capsys, client):
    script(["create", "--handle", "priya", "--name", "P"])
    _, old = _links(capsys.readouterr().out)
    assert script(["rotate", "--handle", "priya"]) == 0
    out = capsys.readouterr().out
    _, new = _links(out)
    assert "old manage link no longer works" in out
    assert client.get("/api/creator/me", headers=_auth(old)).status_code == 401
    assert client.get("/api/creator/me", headers=_auth(new)).status_code == 200
    assert script(["rotate", "--handle", "nobody"]) == 1


def test_script_deletes_a_page_after_asking(monkeypatch, capsys, client):
    _page()
    short_id = _shared()
    creator_store.add_quest("priya", short_id)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert script(["delete", "--handle", "priya"]) == 1
    assert creator_store.get_creator("priya") is not None
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert script(["delete", "--handle", "priya"]) == 0
    assert client.get("/api/creators/priya").status_code == 404
    assert client.get(f"/api/quest/stored/{short_id}").status_code == 200
    assert script(["delete", "--handle", "priya", "--yes"]) == 1


def test_script_lists_nothing_politely(capsys):
    assert script(["list"]) == 0
    assert "No creator pages." in capsys.readouterr().out
