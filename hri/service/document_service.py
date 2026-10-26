"""보고서 업로드 처리 · upload_report (김희진) / validate_pdf (엄정현)"""
import logging
from collections.abc import Iterator
from langchain_core.callbacks import UsageMetadataCallbackHandler
from hri.graph.registry import get_ingest_graph
from hri.util.metrics import cost_korean_won
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
                if node == "validate" and not state.get("ok", True):
                    result = {"type": "error", "reason": state.get("reason", "PDF 검증 실패")}
                
                if node == "persist":
                    report_id = state["report_id"]
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