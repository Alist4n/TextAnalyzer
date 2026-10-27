from pathlib import Path

import pytest

# свой маленький словарь эмоций: тесты логики не зависят от NRC EmoLex, который скачивается отдельно
TEST_LEXICON = Path(__file__).parent / "data" / "lexicon_test.json"


@pytest.fixture(scope="session")
def test_lexicon() -> Path:
    return TEST_LEXICON
