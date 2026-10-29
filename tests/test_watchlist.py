"""Tests for the watchlist service."""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import Film, User, WatchlistEntry
from services.collection_service import FilmNotFoundError
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)


@pytest.fixture
def app():
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    with app.app_context():
        entry = add_to_watchlist(sample_user, sample_film, public=False)

        assert entry.user_id == sample_user
        assert entry.film_id == sample_film
        assert entry.public is False
        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count() == 1


def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    with app.app_context():
        add_to_watchlist(sample_user, sample_film, public=True)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(sample_user, sample_film, public=False)

        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count() == 1


def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(sample_user, fake_film_id, public=True)


def test_add_route_requires_explicit_boolean_visibility(app, sample_user, sample_film):
    client = app.test_client()
    endpoint = f"/watchlist/{sample_user}/add"

    missing_visibility = client.post(endpoint, json={"film_id": sample_film})
    assert missing_visibility.status_code == 400

    invalid_visibility = client.post(
        endpoint,
        json={"film_id": sample_film, "public": "false"},
    )
    assert invalid_visibility.status_code == 400

    private_response = client.post(
        endpoint,
        json={"film_id": sample_film, "public": False},
    )
    assert private_response.status_code == 201
    assert private_response.get_json()["public"] is False

    with app.app_context():
        public_film = Film(title="Public Film")
        db.session.add(public_film)
        db.session.commit()
        public_film_id = public_film.id

    public_response = client.post(
        endpoint,
        json={"film_id": public_film_id, "public": True},
    )
    assert public_response.status_code == 201
    assert public_response.get_json()["public"] is True


def test_remove_from_watchlist_removes_entry(app, sample_user, sample_film):
    with app.app_context():
        add_to_watchlist(sample_user, sample_film, public=True)

        assert remove_from_watchlist(sample_user, sample_film) is True
        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first() is None


def test_remove_from_watchlist_missing_entry_raises(app, sample_user, sample_film):
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(sample_user, sample_film)


def test_get_watchlist_returns_newest_first(app, sample_user):
    with app.app_context():
        older_film = Film(title="Older Film")
        newer_film = Film(title="Newer Film")
        db.session.add_all([older_film, newer_film])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=1)
        later = datetime.now(timezone.utc)
        db.session.add_all([
            WatchlistEntry(
                user_id=sample_user,
                film_id=older_film.id,
                date_added=earlier,
                public=True,
            ),
            WatchlistEntry(
                user_id=sample_user,
                film_id=newer_film.id,
                date_added=later,
                public=True,
            ),
        ])
        db.session.commit()

        watchlist = get_watchlist(sample_user)

        assert [film["title"] for film in watchlist] == [
            "Newer Film",
            "Older Film",
        ]