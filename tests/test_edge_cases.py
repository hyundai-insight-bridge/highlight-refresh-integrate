import pytest

from hri.exception.errors import InvalidInputError
from hri.service.qa_service import mask_pii, validate_question

INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"]


@pytest.mark.parametrize("ch", INVISIBLE)
def test_invisible_only_is_empty_question(ch):
	for text in (ch, ch * 5, f" {ch} \n{ch}", "\u3000" + ch):
		with pytest.raises(InvalidInputError, match="질문을 입력해 주세요"):
			validate_question(text)


def test_many_invisible_chars_is_empty_not_too_long():
	with pytest.raises(InvalidInputError, match="질문을 입력해 주세요"):
		validate_question("\u200b" * 2000)


@pytest.mark.parametrize("ch", INVISIBLE)
def test_invisible_chars_removed_from_question(ch):
	assert validate_question(f"{ch}기준금리{ch} 전망은?{ch}") == "기준금리 전망은?"


def test_normal_question_unchanged():
	assert validate_question("  2026년 물가 상승률은 2.5~3.0%인가요?  ") == "2026년 물가 상승률은 2.5~3.0%인가요?"


def test_length_limit_ignores_invisible_chars():
	assert len(validate_question("가" * 1000 + "\u200b" * 50)) == 1000
	with pytest.raises(InvalidInputError, match="1,000자"):
		validate_question("가" * 1001)


def test_masking_not_bypassed_after_validate():
	question = validate_question("이름: 홍\u200b길동 비밀번호: abc\u200b123")
	assert mask_pii(question) == "이름: 홍*동 비밀번호: ********"

def test_mask_pii_alone_not_bypassed():
	assert mask_pii("이름: 홍\u200b길동") == "이름: 홍*동"
	assert mask_pii("비밀번호: abc\u200b123") == "비밀번호: ********"