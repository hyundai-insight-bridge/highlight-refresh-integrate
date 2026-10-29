"""
개인정보 마스킹 테스트 (서동안, WBS 4.1.4)
mask_pii()가 질문·답변 속 회원가입 정보(이름·아이디·비밀번호)를 가리고, 일반 질문은 바꾸지 않는지,
save_qa_log()가 가린 값으로 qa_logs에 저장하는지 확인한다 (DB 없이 실행).

가리는 규칙 (qa_service.mask_pii)
	- 라벨('이름'·'성명' / '아이디'·'ID' / '비밀번호'·'비번'·'패스워드'·'암호'·'password'·'pw') 바로 뒤의 값만 찾는다
	- 이름: 첫 글자·끝 글자만 남김 (홍길동 → 홍*동, 2글자는 김철 → 김*)
	- 아이디: 4글자 이상은 앞 3글자, 3글자는 앞 1글자만 남김 (abc123 → abc***, kim → k**)
	- 비밀번호: 길이와 상관없이 ******** 8개 (한글 비밀번호는 ':'·'=' 뒤에 올 때만)
	- 대문자 약어(GDP)는 아이디로 보지 않고, 이미 가린 값(abc***)은 다시 가리지 않는다
"""

import pytest

from hri.domain.schemas import QALog
from hri.service.qa_service import mask_pii


# =====================================================================
# 1. 이름
# =====================================================================

# [확인 1] 라벨 뒤 이름은 첫·끝 글자만 남긴다. 구분자(: = 공백 조사)는 그대로 둔다
@pytest.mark.parametrize("text,expected", [
	("이름: 홍길동", "이름: 홍*동"),
	("이름:홍길동", "이름:홍*동"),
	("이름=이몽룡", "이름=이*룡"),
	("이름 홍길동", "이름 홍*동"),
	("이름은 홍길동입니다", "이름은 홍*동입니다"),
	("성명: 남궁민수", "성명: 남**수"),     # 4글자
	("이름: 김철", "이름: 김*"),           # 2글자
])
def test_name_masked(text, expected):
	assert mask_pii(text) == expected


# [확인 2] 이름에 조사로 보이는 글자가 들어 있어도(이·가) 이름으로 본다
@pytest.mark.parametrize("text,expected", [
	("이름: 이가영", "이름: 이*영"),
	("이름은 김가영이에요", "이름은 김*영이에요"),
])
def test_name_with_particle_like_letters(text, expected):
	assert mask_pii(text) == expected


# [확인 3] 이름을 묻는 말은 가리지 않는다 (뒤에 이름 값이 없음)
@pytest.mark.parametrize("text", ["이름이 뭐야?", "이름은 뭐예요", "물가 이름은?", "이름값 하는 지표는?"])
def test_name_question_unchanged(text):
	assert mask_pii(text) == text


# =====================================================================
# 2. 아이디
# =====================================================================

# [확인 4] 4글자 이상은 앞 3글자, 3글자는 앞 1글자만 남긴다
@pytest.mark.parametrize("text,expected", [
	("아이디: abc123", "아이디: abc***"),
	("아이디는 abc123", "아이디는 abc***"),
	("ID: hong_gd", "ID: hon****"),
	("id=user.name-1", "id=use********"),   # 대소문자 구분 없음, . _ - 포함
	("아이디 kim", "아이디 k**"),
])
def test_id_masked(text, expected):
	assert mask_pii(text) == expected


# [확인 5] 2글자 이하나 한글 값은 아이디로 보지 않는다
@pytest.mark.parametrize("text", ["아이디: ab", "아이디는 무엇인가요"])
def test_id_not_masked(text):
	assert mask_pii(text) == text


# =====================================================================
# 3. 비밀번호
# =====================================================================

# [확인 6] 비밀번호는 길이와 상관없이 ******** 8개로 바꾼다 (길이도 드러나지 않게)
@pytest.mark.parametrize("text,expected", [
	("비밀번호: qwer1234!", "비밀번호: ********"),
	("비번 1234", "비번 ********"),
	("password=abc!@#", "password=********"),
	("PW: 1q2w3e4r", "PW: ********"),
	("패스워드는 Zx9!", "패스워드는 ********"),
])
def test_password_masked(text, expected):
	assert mask_pii(text) == expected


# [확인 7] 비밀번호를 묻는 말은 가리지 않는다
@pytest.mark.parametrize("text", ["비밀번호를 잊어버렸어요", "비밀번호는 무엇인가요?"])
def test_password_question_unchanged(text):
	assert mask_pii(text) == text


# =====================================================================
# 4. 함께 나올 때 · 공통
# =====================================================================

# [확인 8] 이름·아이디·비밀번호가 한 문장에 함께 있어도 모두 가린다
def test_all_three_together():
	text = "이름: 홍길동, 아이디: hong123, 비밀번호: pw1234!"
	assert mask_pii(text) == "이름: 홍*동, 아이디: hon****, 비밀번호: ********"


def test_name_and_id_in_sentence():
	text = "제 이름은 김민수이고 아이디는 minsu99입니다"
	assert mask_pii(text) == "제 이름은 김*수이고 아이디는 min****입니다"


# [확인 9] 회원가입 정보가 없는 보고서 질문·답변은 한 글자도 바꾸지 않는다
@pytest.mark.parametrize("text", [
	"2026년 하반기 소비자물가 상승률은 어느 범위로 전망되나요?",
	"GDP 성장률 1.7%",
	"원/달러 환율은 1,440원에서 1,530원으로 올랐습니다. (출처: 물가, 환율 상승의 누적 효과에 주의해야 한다! p.8)",
])
def test_plain_text_unchanged(text):
	assert mask_pii(text) == text


# [확인 10] 두 번 가려도 결과가 같다 (validate 노드에서 가린 질문을 save_qa_log가 다시 가려도 안전)
@pytest.mark.parametrize("text", ["이름: 홍길동", "아이디: abc123", "비밀번호: qwer1234!", "암호: 아무거나"])
def test_idempotent(text):
	assert mask_pii(mask_pii(text)) == mask_pii(text)


# =====================================================================
# 5. 보완한 경우 (예전 코드에서 틀리던 것)
# =====================================================================

# [확인 11] 한글 비밀번호는 ':'·'=' 뒤에 올 때 가린다 (예전: ':'를 비밀번호로 잡아 '암호******** 아무거나')
@pytest.mark.parametrize("text,expected", [
	("암호: 아무거나", "암호: ********"),
	("비밀번호=한글비번123", "비밀번호=********"),
	("비번:1234", "비번:********"),
])
def test_password_after_colon(text, expected):
	assert mask_pii(text) == expected


# [확인 12] 대문자 약어(GDP·CPI)는 지표 이름이라 아이디로 보지 않는다 (예전: 'ID는 G** 같은 지표')
@pytest.mark.parametrize("text", ["ID는 GDP 같은 지표 아닌가요", "ID=CPI"])
def test_uppercase_acronym_not_id(text):
	assert mask_pii(text) == text


# [확인 13] 이름 뒤 호칭(님·씨)은 이름에 넣지 않는다 (예전: '홍**님')
@pytest.mark.parametrize("text,expected", [
	("이름: 홍길동님", "이름: 홍*동님"),
	("이름은 홍길동씨", "이름은 홍*동씨"),
])
def test_name_with_title(text, expected):
	assert mask_pii(text) == expected


# [확인 14] 아이디도 두 번 가려 결과가 같다 (예전: 'abc***'를 다시 가려 'a*****')
def test_id_idempotent():
	assert mask_pii(mask_pii("아이디: abc123")) == "아이디: abc***"


# =====================================================================
# 6. 알려진 한계
#    strict=True: 고치면 이 테스트가 실패로 바뀌므로, 그때 xfail 표시를 지우고 일반 테스트로 옮긴다
# =====================================================================

@pytest.mark.xfail(strict=True, reason="공백이 들어간 비밀번호는 다음 단어와 구별할 수 없어 첫 단어만 가림 ('pass word' → '******** word')")
def test_known_password_with_space():
	assert mask_pii("비밀번호는 pass word") == "비밀번호는 ********"


# [확인 15] 대문자로만 된 아이디(ABC)는 약어와 구별할 수 없어 가리지 않는다 (확인 12의 대가로 정한 동작)
def test_uppercase_only_id_kept():
	assert mask_pii("아이디: ABC") == "아이디: ABC"


# =====================================================================
# 7. qa_logs 저장값 (save_qa_log → insert_qa_log, DB 없이)
# =====================================================================

def _log(question: str, answer: str) -> QALog:
	return QALog(user_id="tester", session_id="s-1", question=question, answer=answer, persona="실무자",
		route="chat", has_source=False, response_ms=100, tokens=10, cost_krw=0.1)


# [확인 16] save_qa_log는 질문·답변의 이름·아이디·비밀번호를 가린 값으로 insert_qa_log에 넘긴다
def test_save_qa_log_masks_before_insert(monkeypatch):
	import hri.service.history_service as history_service

	saved = []
	monkeypatch.setattr(history_service, "insert_qa_log", lambda log: saved.append(log) or 7)

	original = _log("제 아이디는 hong123이고 비밀번호는 pw1234!인데 로그인이 안 돼요",
		"이름: 홍길동 님, 아이디 hong123으로 다시 시도해 보세요")
	log_id = history_service.save_qa_log(original)

	assert log_id == 7
	assert saved[0].question == "제 아이디는 hon****이고 비밀번호는 ********인데 로그인이 안 돼요"
	assert "hong123" not in saved[0].answer and "홍길동" not in saved[0].answer
	assert original.question.startswith("제 아이디는 hong123")  # 넘긴 원본은 바뀌지 않는다


# [확인 17] 가리는 것 말고 나머지 값(route·토큰·비용 등)은 그대로 저장한다
def test_save_qa_log_keeps_other_fields(monkeypatch):
	import hri.service.history_service as history_service

	saved = []
	monkeypatch.setattr(history_service, "insert_qa_log", lambda log: saved.append(log) or 1)
	history_service.save_qa_log(_log("물가 전망은?", "2.7%입니다"))

	log = saved[0]
	assert (log.question, log.answer) == ("물가 전망은?", "2.7%입니다")
	assert (log.user_id, log.session_id, log.persona, log.route, log.has_source, log.tokens, log.cost_krw) == \
		("tester", "s-1", "실무자", "chat", False, 10, 0.1)
