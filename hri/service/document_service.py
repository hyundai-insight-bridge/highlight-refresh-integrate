"""보고서 업로드 처리 · upload_report (김희진) / validate_pdf (엄정현)"""

# 엄정현 validate_pdf() 추가.

import os

import pymupdf

from hri.config.settings import load_settings
from hri.domain.schemas import ValidationResult

def validate_pdf(file_path: str) -> ValidationResult:
	"""업로드된 파일이 PDF로 처리할 수 있는지 확인한다.

	확인 순서: 확장자(.pdf) → 용량(MAX_MB) → pymupdf로 열리는지 → 진짜 PDF인지 → 암호화 여부 → 쪽 수(MAX_PAGES)
	예외를 던지지 않고 ValidationResult(ok, reason)만 돌려준다.
	실패하면 validate 노드가 reason을 state['error']에 기록하고, on_upload()가 화면에 보여 준다.
	글자가 없는 스캔본은 여기서 막지 않는다 (load_pdf()가 Page.is_scanned로 표시).

	예) validate_pdf("data/raw/report.pdf") → ValidationResult(ok=True, reason=None)
	"""
	# MAX_MB·MAX_PAGES는 .env 값 (load_settings()가 Settings.max_mb·max_pages로 읽어 둠)
	settings = load_settings()
	max_mb = settings.max_mb
	max_pages = settings.max_pages

	# 1) 확장자 확인 (.PDF처럼 대문자로 올라와도 통과시키려고 소문자로 바꿔서 비교)
	ext = os.path.splitext(file_path)[1].lower()
	if ext != ".pdf":
		return ValidationResult(ok=False, reason="PDF 파일만 업로드할 수 있습니다")

	# 파일이 없으면 os.path.getsize()가 예외를 내므로 먼저 확인
	if not os.path.isfile(file_path):
		return ValidationResult(ok=False, reason="파일을 찾을 수 없습니다. 다시 업로드해 주세요")

	# 2) 용량 확인 (바이트 → MB: 1MB = 1024 * 1024 바이트)
	size_mb = os.path.getsize(file_path) / (1024 * 1024)
	if size_mb > max_mb:
		return ValidationResult(ok=False, reason=f"파일 용량이 {max_mb}MB를 넘습니다 (현재 {size_mb:.1f}MB)")

	# 3) pymupdf로 열기 (깨진 파일·빈 파일·PDF가 아닌 내용은 여기서 오류가 난다)
	try:
		doc = pymupdf.open(file_path)
	except Exception:
		return ValidationResult(ok=False, reason="PDF 파일을 열 수 없습니다. 파일이 손상되지 않았는지 확인해 주세요")

	# with: 확인이 끝나면 파일을 꼭 닫는다 (안 닫으면 Windows에서 파일이 잠긴 채로 남음)
	with doc:
		# 이름만 .pdf인 이미지(png 등)도 pymupdf는 열어 버리므로 진짜 PDF인지 한 번 더 확인
		if not doc.is_pdf:
			return ValidationResult(ok=False, reason="PDF 파일만 업로드할 수 있습니다")

		# 4) 암호화 여부 확인 (needs_pass: 열 때 암호를 입력해야 하는 파일이면 True)
		if doc.needs_pass:
			return ValidationResult(ok=False, reason="암호가 걸린 PDF는 업로드할 수 없습니다. 암호를 해제한 뒤 다시 올려 주세요")

		# 5) 쪽 수 확인
		page_count = doc.page_count
		if page_count < 1:
			return ValidationResult(ok=False, reason="쪽이 하나도 없는 PDF입니다. 내용이 있는 파일을 올려 주세요")
		if page_count > max_pages:
			return ValidationResult(ok=False, reason=f"쪽 수가 {max_pages}쪽을 넘습니다 (현재 {page_count}쪽)")

	# 6) 모두 통과
	return ValidationResult(ok=True)

# (김희진)
import logging
from collections.abc import Iterator
from langchain_core.callbacks import UsageMetadataCallbackHandler
from hri.graph.registry import get_ingest_graph
from hri.llm.llm_client import cost_korean_won
from hri.dao.usage_dao import insert_usage

logger = logging.getLogger(__name__)

def upload_report(file_path: str, user_id: str) -> Iterator[dict]:
    """PDF를 업로드 그래프로 처리하며 진행 상황을 하나씩 내보낸다.

    내보내는 dict 모양
      진행: {"type": "progress", "step": 노드이름}
      성공: {"type": "result", "report_id": int, "counts": dict, "warnings": list}
      실패: {"type": "error", "reason": str}
    """
    graph = get_ingest_graph()
    usage = UsageMetadataCallbackHandler()
    report_id: int | None = None
    result: dict | None = None
    try:
        for update in graph.stream({
            "file_path": file_path, "user_id": user_id},
            stream_mode = "updates",
            config = {"callbacks": [usage]},
        ):
            for node, state in update.items():
                yield {"type": "progress", "step": node}
                state = state or {}
                if node == "validate" and state.get("error"):
                    result = {"type": "error", "reason": state.get("error")}
                
                if node == "persist":
                    report_id = state.get("report_id")
                    result = {"type": "result", "report_id": report_id,
                             "counts": state.get("counts", {}),
                             "warnings": state.get("warnings", [])}
        yield result or {"type": "error", "reason": "저장 단계까지 진행되지 않았습니다."}
    
    except Exception:
        logger.exception("upload_report 실패: %s", file_path)
        yield {"type": "error", "reason": "업로드 처리 중 오류가 발생했습니다."}

    finally:
        if usage.usage_metadata:
            insert_usage(flow="ingest", ref_id=report_id, usage=usage.usage_metadata, cost_krw=cost_korean_won(usage.usage_metadata))
