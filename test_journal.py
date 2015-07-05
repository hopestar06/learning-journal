# -*_ coding: utf-8 _*-
from __future__ import unicode_literals
import os
import pytest
from pyramid import testing
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from cryptacular.bcrypt import BCRYPTPasswordManager

TEST_DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://muoily@localhost:5432/learning-journal'
    )

os.environ['DATABASE_URL'] = TEST_DATABASE_URL
os.environ['TESTING'] = "True"

import journal


@pytest.fixture(scope='session')
def connection(request):
    engine = create_engine(TEST_DATABASE_URL)
    journal.Base.metadata.create_all(engine)
    connection = engine.connect()
    journal.DBSession.registry.clear()
    journal.DBSession.configure(bind=connection)
    journal.Base.metadata.bind = engine
    request.addfinalizer(journal.Base.metadata.drop_all)
    return connection


@pytest.fixture()
def db_session(request, connection):
    from transaction import abort
    trans = connection.begin()
    request.addfinalizer(trans.rollback)
    request.addfinalizer(abort)

    from journal import DBSession
    return DBSession


@pytest.fixture()
def app():
    from journal import main
    from webtest import TestApp
    app = main()
    return TestApp(app)


@pytest.fixture()
def entry(db_session):
    entry = journal.Entry.write(
        title='This is a Test Title',
        text='This is a Test Entry for the Text',
        session=db_session
    )
    db_session.flush()
    return entry


@pytest.fixture(scope='function')
def auth_req(request):
    manager = BCRYPTPasswordManager()
    settings = {
        'auth.username': 'admin',
        'auth.password': manager.encode('secret'),
    }

    testing.setUp(settings=settings)
    req = testing.DummyRequest()

    def cleanup():
        testing.tearDown()

    request.addfinalizer(cleanup)

    return req



def test_write_entry(db_session):
    kwargs = {'title': "Test Title", 'text': "Test entry text"}
    kwargs['session'] = db_session
    # assert that there are no entries in the database:
    assert db_session.query(journal.Entry).count() == 0
    # create an entry using the 'write' class method
    entry = journal.Entry.write(**kwargs)
    # the entry we get back should be an instance of Entry
    assert isinstance(entry, journal.Entry)
    # id and created are generated automatically, but only on writing to
    # the database
    auto_fields = ['id', 'created']
    for field in auto_fields:
        assert getattr(entry, field, None) is None

    # flush the session to "write" the data to the database
    db_session.flush()
    # now, we should have one entry
    assert db_session.query(journal.Entry).count() == 1
    for field in kwargs:
        if field != 'session':
            assert getattr(entry, field, '') == kwargs[field]

    # id and created should be set automatically upon writing to db:
    for auto in ['id', 'created']:
        assert getattr(entry, auto, None) is not None


def test_entry_no_title_fails(db_session):
    bad_data = {'text': 'test text'}
    journal.Entry.write(session=db_session, **bad_data)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_entry_no_text_fails(db_session):
    bad_data = {'title': 'test title'}
    journal.Entry.write(session=db_session, *bad_data)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_read_entries_empty(db_session):
    entries = journal.Entry.all()
    assert len(entries) == 0


def test_read_entries_one(db_session):
    title_template = "Title {}"
    text_template = "Entry Text {}"
    # write three entries, with order clear in the title and text
    for x in range(3):
        journal.Entry.write(
            title=title_template.format(x),
            text=text_template.format(x),
            session=db_session)
        db_session.flush()
    entries = journal.Entry.all()
    assert len(entries) == 3
    assert entries[0].title > entries[1].title > entries[2].title
    for entry in entries:
        assert isinstance(entry, journal.Entry)


def test_empty_listing(app):
    response = app.get('/')
    assert response.status_code == 200
    actual = response.body
    expected = 'No entries here so far'
    assert expected in actual


def test_listing(app, entry):
    response = app.get('/')
    assert response.status_code == 200
    actual = response.body
    for field in ['title', 'text']:
        expected = getattr(entry, field, 'absent')
        assert expected in actual


def test_post_to_add_view(app):
    entry_data = {
        'title': 'Hello there',
        'text': 'This is a post',
    }
    response = app.post('/add', params=entry_data, status='3*')
    redirected = response.follow()
    actual = redirected.body
    for expected in entry_data.values():
        assert expected in actual


def test_add_no_params(app):
    response = app.post('/add', status=500)
    assert 'IntegrityError' in response.body


def test_do_login_success(auth_req):
    from journal import do_login
    auth_req.params = {'username': 'admin', 'password': 'secret'}
    assert do_login(auth_req)


def test_do_login_bad_pass(auth_req):
    from journal import do_login
    auth_req.params = {'username': 'admin', 'password': 'wrong'}
    assert not do_login(auth_req)


def test_do_login_bad_user(auth_req):
    from journal import do_login
    auth_req.params = {'username': 'bad', 'password': 'secret'}
    assert not do_login(auth_req)


def test_do_login_missing_params(auth_req):
    from journal import do_login
    for params in ({'username': 'admin'}, {'password': 'secret'}):
        auth_req.params = params
        with pytest.raises(ValueError):
            do_login(auth_req)

