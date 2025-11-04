import pytest

from config import QUESTION_TAGS
from system_manager import SystemManager


@pytest.fixture()
def system_manager(tmp_path):
    return SystemManager(db_path=str(tmp_path / "system.db"))


def test_seed_initial_tags(system_manager):
    tags = system_manager.get_all_tags(limit=len(QUESTION_TAGS))
    names = {tag['name'] for tag in tags}
    for tag_name in QUESTION_TAGS:
        assert tag_name in names


def test_register_and_authenticate_user(system_manager):
    success, message = system_manager.register_user("alice", "secret123", "alice@example.com")
    assert success, message

    user = system_manager.authenticate_user("alice", "secret123")
    assert user is not None
    assert user['username'] == "alice"

    duplicate_success, duplicate_message = system_manager.register_user("alice", "anotherpass")
    assert not duplicate_success
    assert "存在" in duplicate_message


def test_update_password_requires_correct_old_password(system_manager):
    system_manager.register_user("bob", "password1")
    user = system_manager.authenticate_user("bob", "password1")

    ok, msg = system_manager.update_password(user['id'], "wrong", "password2")
    assert not ok

    ok, msg = system_manager.update_password(user['id'], "password1", "password2")
    assert ok

    assert system_manager.authenticate_user("bob", "password2") is not None


def test_add_tag_increments_usage_count(system_manager):
    system_manager.add_tag("函数与方程")
    system_manager.add_tag("函数与方程")

    tag = system_manager.get_tag_by_name("函数与方程")
    assert tag is not None
    assert tag['usage_count'] >= 2


def test_export_history_round_trip(system_manager):
    system_manager.register_user("carol", "strongpass")
    user = system_manager.authenticate_user("carol", "strongpass")

    export_id = system_manager.save_export_history(
        user_id=user['id'],
        title="测试试卷",
        question_ids=[1, 2, 3],
        export_format="latex",
        export_mode="questions"
    )

    history = system_manager.get_export_history(user['id'])
    assert len(history) == 1
    assert history[0]['title'] == "测试试卷"

    export = system_manager.get_export_by_id(export_id)
    assert export is not None
    assert export['question_ids'] == [1, 2, 3]
