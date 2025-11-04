import json
from types import SimpleNamespace

import numpy as np
import pytest

from question_manager import QuestionManager


@pytest.fixture()
def qm_context(tmp_path, monkeypatch):
    responses = []

    class DummyOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(self, **kwargs):
            if not responses:
                raise AssertionError("No queued LLM response for test")
            content = responses.pop(0)
            message = SimpleNamespace(content=content)
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

    monkeypatch.setattr("question_manager.OpenAI", DummyOpenAI)

    class DummyOCRClient:
        def __init__(self, *args, **kwargs):
            self.embeddings_to_return = [[0.0, 0.0, 0.0]]

        def set_embeddings(self, embeddings):
            self.embeddings_to_return = embeddings

        def get_embeddings(self, texts):
            if not texts:
                return []
            if len(self.embeddings_to_return) == len(texts):
                return self.embeddings_to_return
            if len(self.embeddings_to_return) == 1:
                return self.embeddings_to_return * len(texts)
            raise AssertionError("Mismatch between requested embeddings and queued embeddings")

        def ocr_image(self, image_path):
            return {"request_id": "dummy", "markdown": "", "images": []}

    dummy_ocr = DummyOCRClient()
    monkeypatch.setattr("question_manager.DeepSeekOCRClient", lambda *args, **kwargs: dummy_ocr)

    class DummyFaissIndex:
        def __init__(self, dimension):
            self.vectors = np.zeros((0, dimension), dtype="float32")

        def add(self, array):
            self.vectors = array

        def search(self, query_array, k):
            if self.vectors.size == 0:
                raise AssertionError("No vectors added to FAISS index stub")
            distances = np.sum((self.vectors - query_array) ** 2, axis=1)
            order = np.argsort(distances)[:k]
            return distances[order][None, :], order.astype("int64")[None, :]

    monkeypatch.setattr("question_manager.faiss.IndexFlatL2", DummyFaissIndex)

    class FakeSystemManager:
        def __init__(self):
            self.tags = {}

        def get_all_tags(self, limit=50):
            return [{'name': name} for name in sorted(self.tags.keys())]

        def add_tag(self, tag_name):
            self.tags[tag_name] = self.tags.get(tag_name, 0) + 1

    fake_system_manager = FakeSystemManager()

    manager = QuestionManager(db_path=str(tmp_path / "questions.db"), system_manager=fake_system_manager)
    manager.embedding_cache_path = str(tmp_path / "embeddings.db")
    manager._ensure_embedding_store()
    manager.embedding_cache = {}

    # Prevent background threads during tests
    manager._compute_missing_embeddings_async = lambda *args, **kwargs: None

    return SimpleNamespace(
        manager=manager,
        llm_responses=responses,
        ocr_client=dummy_ocr,
        system_manager=fake_system_manager,
    )


def test_add_question_defaults_to_solution_type(qm_context):
    manager = qm_context.manager
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


def test_add_question_respects_explicit_type(qm_context):
    manager = qm_context.manager
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


def test_add_question_validation_on_empty_content(qm_context):
    manager = qm_context.manager

    with pytest.raises(ValueError):
        manager.add_question(
            latex_content="",
            tags=[],
            reference_answer="",
            source="",
            image=[],
        )


def test_update_question_permission(qm_context):
    manager = qm_context.manager
    question_id = manager.add_question(
        latex_content="原始题目",
        tags=["标签"],
        reference_answer="答案",
        source="单元测试",
        image=[],
        user_id=1
    )

    # 非题目所有者无法更新
    with pytest.raises(PermissionError):
        manager.update_question(
            question_id=question_id,
            latex_content="更新后的题目",
            reference_answer="新答案",
            current_user_id=2,
        )

    updated = manager.update_question(
        question_id=question_id,
        latex_content="更新后的题目",
        reference_answer="新答案",
        current_user_id=1,
        question_type="填空题"
    )

    assert updated["latex_content"] == "更新后的题目"
    assert updated["reference_answer"] == "新答案"
    assert updated["question_type"] == "填空题"


def test_embedding_cache_round_trip(qm_context):
    manager = qm_context.manager

    manager._save_embedding_to_cache(42, [0.1, 0.2, 0.3])
    cache = manager._load_embedding_cache()

    assert 42 in cache
    assert cache[42] == [0.1, 0.2, 0.3]


def test_auto_tag_and_answer_parses_llm_payload(qm_context):
    manager = qm_context.manager
    payload = {
        "latex_content": "x^2+1",
        "tags": ["分数"],
        "answer": "示例解答",
        "question_type": "选择题",
    }
    qm_context.llm_responses.append(f"以下是结果：{json.dumps(payload, ensure_ascii=False)}")

    tags, answer, latex_content, question_type = manager.auto_tag_and_answer("示例题目")

    assert latex_content == "x^2+1"
    assert tags == ["分数"]
    assert answer == "示例解答"
    assert question_type == "选择题"
    assert qm_context.system_manager.tags["分数"] == 1


def test_parse_exam_paper_maps_images(qm_context):
    manager = qm_context.manager
    qm_context.llm_responses.append(
        """
        {"questions": [{"question": "题目1", "image": ["0.jpg"], "tags": ["解析几何"], "answer": "解析", "question_type": "填空题"}]}
        """
    )

    mapping = {"0.jpg": "/uploads/ocr_images/ocr_0.jpg"}
    parsed = manager.parse_exam_paper("markdown 内容", mapping)

    assert len(parsed) == 1
    question = parsed[0]
    assert question["question"] == "题目1"
    assert question["image"] == ["/uploads/ocr_images/ocr_0.jpg"]
    assert question["tags"] == ["解析几何"]
    assert question["question_type"] == "填空题"


def test_search_questions_merges_keyword_and_embeddings(qm_context):
    manager = qm_context.manager

    qid_keyword = manager.add_question(
        latex_content="这是一道geometry相关的题目",
        tags=["几何"],
        reference_answer="答案1",
        source="测试",
        image=[],
        user_id=1
    )

    qid_embedding = manager.add_question(
        latex_content="向量空间问题",
        tags=["线性代数"],
        reference_answer="答案2",
        source="测试",
        image=[],
        user_id=1
    )

    manager._save_embedding_to_cache(qid_keyword, [1.0, 0.0])
    manager._save_embedding_to_cache(qid_embedding, [0.0, 1.0])

    qm_context.ocr_client.set_embeddings([[0.0, 1.0]])

    results = manager.search_questions("geometry", current_user_id=1, k=2)

    assert results[0]["id"] == qid_keyword  # 关键词匹配优先
    assert any(item["id"] == qid_embedding for item in results)
