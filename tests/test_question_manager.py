from pathlib import Path

import pytest

from question_manager import QuestionManager


@pytest.fixture()
def temp_question_manager(tmp_path):
    """构造使用临时数据库的QuestionManager实例。"""
    db_path = tmp_path / "questions.db"
    manager = QuestionManager(db_path=str(db_path))

    # Redirect embedding缓存到临时目录，避免污染真实数据
    manager.embedding_cache_path = str(tmp_path / "embeddings.db")
    manager._ensure_embedding_store()
    manager.embedding_cache = {}

    return manager


def test_add_question_defaults_to_solution_type(temp_question_manager):
    """默认情况下新增题目应当归类为解答题。"""
    manager = temp_question_manager
    question_id = manager.add_question(
        latex_content=r"1+1=2",
        tags=["基础代数"],
        reference_answer="2",
        source="单元测试",
        image=[],
    )

    result = manager.get_question_by_id(question_id, None)
    assert result is not None
    assert result["question_type"] == "解答题"


def test_add_question_respects_explicit_type(temp_question_manager):
    """显式指定题型时应保留用户提供的类型。"""
    manager = temp_question_manager
    question_id = manager.add_question(
        latex_content=r"\\frac{1}{2} + \\frac{1}{3} = ?",
        tags=["分数"],
        reference_answer="\\frac{5}{6}",
        source="单元测试",
        image=[],
        question_type="选择题",
    )

    result = manager.get_question_by_id(question_id, None)
    assert result is not None
    assert result["question_type"] == "选择题"


def test_embedding_cache_round_trip(temp_question_manager, tmp_path):
    """验证embedding缓存的保存与重新加载流程。"""
    manager = temp_question_manager
    embed_path = Path(manager.embedding_cache_path)
    assert embed_path.exists()

    manager._save_embedding_to_cache(42, [0.1, 0.2, 0.3])
    cache = manager._load_embedding_cache()

    assert 42 in cache
    assert cache[42] == [0.1, 0.2, 0.3]
