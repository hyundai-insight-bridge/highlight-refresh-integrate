# 프로젝트 구조 (초안)

> 상태: **초안 v0.2** · 팀 리뷰 후 확정
> 기준 문서: `01. 프로젝트기획서_Insight Bridge.docx`, `기능명세서_경제분석보고서_AI요약서비스.xlsx`, `경제분석보고서_AI요약서비스_WBS` (Google Drive · 현대 1차 4팀_내부자료)
> v0.2 변경: `app/` 바로 아래 폴더 20여 개 → **역할별 상위 그룹 6개**로 묶고, 명세서 패키지는 그 아래로 이동

## 0. 확정된 원칙

| 항목 | 결정 |
|---|---|
| 최상위 배치 | `app/` 단일 패키지. 레포 루트에서 `poetry run python -m app.main`으로 실행 |
| 1단계 (그룹) | 역할별 6개: `presentation` · `application` · `rag` · `ai` · `infrastructure` · `core` |
| 2단계 (패키지) | 기능명세서의 **패키지명 그대로** (`view`, `service`, `loader` …) |
| 3단계 (모듈) | 기능명세서의 **클래스명 = 파일명** (`qa_service.py`, `search.py` …) |
| 스키마 · 예외 | 명세서의 `domain/schemas`, `exception/errors`는 **영역별 파일로 분리**하고 `__init__.py`에서 다시 내보낸다 |
| import 규칙 | 항상 절대 경로 `from app.<그룹>.<패키지>.<모듈> import <이름>` |
| 코드 스타일 | `.github/CONTRIBUTING.md` 그대로 (PEP 8, 탭 들여쓰기, docstring 필수) |

## 1. 상위 그룹 한눈에 보기

```text
app/
├─ main.py
├─ presentation/     화면       view
├─ application/      업무 흐름   service
├─ rag/              문서 처리·검색   ingestion(loader, splitter) · vector_store · retriever
├─ ai/               LLM 활용    llm · prompt · parser · router · memory · source · suggest
├─ infrastructure/   외부 연결   dao · api · config
└─ core/             공통 기반   domain · exception · util
```

| 그룹 | 역할 | 명세서 패키지 |
|---|---|---|
| `presentation` | Gradio 탭과 이벤트 핸들러 | `view` |
| `application` | 화면 요청 하나를 처리하는 업무 흐름 (여러 모듈을 순서대로 호출) | `service` |
| `rag` | PDF → 청크 → 임베딩 저장 → 검색 | `loader`, `splitter` (→ `ingestion/`로 묶음), `vector_store`, `retriever` |
| `ai` | 프롬프트 · LLM 호출 · 구조화 출력 · Tool Calling · 대화 기록 | `llm`, `prompt`, `parser`, `router`, `memory`, `source`, `suggest` |
| `infrastructure` | MySQL · 외부 API · 환경 설정 | `dao`, `api`, `config` |
| `core` | 어디서나 쓰는 스키마 · 예외 · 유틸 | `domain`, `exception`, `util` |

## 2. 전체 트리

```text
highlight-refresh-integrate/
├─ app/
│  ├─ __init__.py
│  ├─ main.py                              # 진입점: from app.presentation.view.app import main → main()
│  │
│  ├─ presentation/
│  │  └─ view/
│  │     ├─ app.py                         # build_app(), main(), init_state()
│  │     ├─ report_view.py                 # build_upload_tab(), on_upload()
│  │     ├─ summary_view.py                # build_summary_tab(), on_summarize(), on_request()
│  │     ├─ chat_view.py                   # build_chat_tab(), respond_stream(), on_suggest_click()
│  │     ├─ indicator_view.py              # build_indicator_panel(), on_compare()
│  │     ├─ term_view.py                   # term_search_panel()
│  │     ├─ user_view.py                   # build_login_tab(), on_login(), on_register()
│  │     ├─ history_view.py                # build_history_tab(), on_restore()
│  │     └─ admin_view.py                  # build_admin_tab(), on_refresh(), on_feedback()
│  │
│  ├─ application/
│  │  └─ service/
│  │     ├─ document_service.py            # upload_report(), validate_pdf()
│  │     ├─ qa_service.py                  # ask_stream(), validate_question(), mask_pii()
│  │     ├─ summary_service.py             # summarize_report()
│  │     ├─ report_service.py              # list_reports(), get_report_text(), search_reports()
│  │     ├─ ecos_finder.py                 # find_usable_data(), explain_term()
│  │     ├─ indicator_service.py           # extract_indicators(), build_compare_table(), plot_indicators()
│  │     ├─ user_service.py                # register(), login(), logout()
│  │     ├─ history_service.py             # save_qa_log(), get_history(), restore_session()
│  │     └─ dashboard_service.py           # get_dashboard_data(), get_dashboard_data_v2(), plot_daily_counts()
│  │
│  ├─ rag/
│  │  ├─ ingestion/
│  │  │  ├─ loader/
│  │  │  │  ├─ pdf_loader.py               # load_pdf(), clean_text(), find_body_start()
│  │  │  │  └─ table_loader.py             # extract_tables(), validate_table(), table_to_markdown(), split_big_table()
│  │  │  └─ splitter/
│  │  │     └─ text_splitter.py            # split_sections(), split_text()
│  │  ├─ vector_store/
│  │  │  ├─ embedding.py                   # embed_texts(), similarity()
│  │  │  └─ chroma_store.py                # get_collection(), add_chunks(), add_table_summaries(), delete_report_vectors()
│  │  └─ retriever/
│  │     └─ search.py                      # extract_keywords(), keyword_find(), vector_search(), safe_search(),
│  │                                       # mmr_select(), expand_queries(), hybrid_search()
│  │
│  ├─ ai/
│  │  ├─ llm/
│  │  │  └─ llm_client.py                  # ask_llm(), stream_llm(), cost_korean_won(), chat_bot()
│  │  ├─ prompt/
│  │  │  ├─ rag_prompt.py                  # format_docs(), has_context(), build_messages()
│  │  │  ├─ summary_prompt.py              # summarize_sections(), summarize_three_lines(), verify_and_expand(), merge_reports()
│  │  │  └─ persona_prompt.py              # PERSONAS, FEW_SHOT_EXAMPLES, get_persona_prompt()
│  │  ├─ parser/
│  │  │  └─ json_parser.py                 # format_instructions(), parse_json_output()
│  │  ├─ router/
│  │  │  └─ tool_router.py                 # TOOLS, TOOL_MAP, run_agent_with_tools()
│  │  ├─ memory/
│  │  │  └─ history_store.py               # get_session_history(), append_history(), trim_history(), rewrite_question()
│  │  ├─ source/
│  │  │  └─ source_formatter.py            # format_sources()
│  │  └─ suggest/
│  │     └─ suggest_service.py             # suggest_questions()
│  │
│  ├─ infrastructure/
│  │  ├─ dao/
│  │  │  ├─ db.py                          # get_connection()
│  │  │  ├─ report_dao.py                  # insert_report(), insert_sections(), insert_chunks(), insert_tables(), select_reports()
│  │  │  ├─ user_dao.py                    # insert_user(), select_user()
│  │  │  ├─ qa_log_dao.py                  # insert_qa_log(), select_logs(), update_feedback()
│  │  │  └─ dashboard_dao.py               # select_top_questions() … select_no_source_questions()
│  │  ├─ api/
│  │  │  ├─ ecos_client.py                 # call_ecos(), get_ecos_exchange_rate(), get_ecos_statistic_*()
│  │  │  ├─ exchange_client.py             # get_exchange_rate()
│  │  │  └─ stdict_client.py               # get_stdict()
│  │  └─ config/
│  │     └─ settings.py                    # load_settings()
│  │
│  └─ core/
│     ├─ domain/                           # Pydantic 스키마 (영역별 분리)
│     │  ├─ __init__.py                    # 전부 re-export → from app.core.domain import Chunk
│     │  ├─ report.py                      # Page, Section, Chunk, Table, Report
│     │  ├─ answer.py                      # AnswerResult, SuggestedQuestions, SearchHit
│     │  ├─ summary.py                     # ReportSummary, ThreeLineSummary, SectionSummary, VerifyResult, MergedReport
│     │  ├─ external.py                    # TermCard, Indicator, EcosQuery, ExchangeRate
│     │  ├─ user.py                        # User, QALog
│     │  ├─ dashboard.py                   # DashboardData
│     │  └─ settings.py                    # Settings, State
│     ├─ exception/                        # 예외 (영역별 분리)
│     │  ├─ __init__.py                    # 전부 re-export → from app.core.exception import InvalidFileError
│     │  ├─ base.py                        # HriError (공통 부모, 제안)
│     │  ├─ document.py                    # InvalidFileError
│     │  ├─ qa.py                          # InvalidInputError
│     │  ├─ summary.py                     # OutputFormatError
│     │  ├─ external.py                    # ExternalApiError
│     │  └─ user.py                        # LoginFailedError, DuplicateUserError
│     └─ util/
│        ├─ metrics.py                     # measure_time()
│        └─ logger.py                      # log_error(), safe_call()
│
├─ tests/                                  # app/ 구조를 그대로 따라감 (test_<모듈>.py)
│  ├─ conftest.py
│  ├─ fixtures/
│  │  └─ sample_pdf.py                     # make_sample_pdf()
│  ├─ application/  rag/  ai/  infrastructure/  core/
│  └─ scenarios/                           # 4.1.x 테스트 시나리오 (정답 질문 30문항 등)
│
├─ sql/
│  └─ schema.sql                           # users / reports / sections / chunks / report_tables / qa_logs / terms + VIEW v_daily_usage
├─ infra/
│  └─ docker/README.md                     # 로컬 MySQL docker run 명령 (배포용 아님)
├─ assets/
│  └─ fonts/                               # matplotlib 한글 폰트 (커밋 대상)
├─ data/                                   # ↓ 전부 .gitignore
│  ├─ raw/                                 # 원본 PDF (업로드 · 수집 보고서)
│  ├─ cache/                               # ECOS 통계표 목록 캐시 (날짜별)
│  └─ charts/                              # plot_*() 결과 PNG (uuid 파일명)
├─ chroma_db/                              # Chroma PersistentClient 경로 (.gitignore)
├─ logs/                                   # app.log (.gitignore)
├─ docs/
├─ .env.example
├─ pyproject.toml / poetry.lock
└─ README.md
```

- 모든 폴더에 빈 `__init__.py`를 둔다. (트리에서는 `domain`, `exception` 외 생략)
- `app/` 바로 아래에는 `main.py`와 그룹 폴더 6개만 둔다. 새 패키지는 반드시 6개 그룹 중 하나에 넣는다.

## 3. 그룹 간 의존 규칙

```text
presentation  →  application  →  rag · ai · infrastructure  →  core
```

- 화살표 방향으로만 import한다. 아래 그룹이 위 그룹을 import하지 않는다.
- `presentation`은 `application`만 호출한다. (예외: `admin_view.on_feedback()` → `infrastructure.dao.qa_log_dao.update_feedback()`은 명세서대로 허용할지 결정 필요)
- 같은 층의 `rag` · `ai` · `infrastructure` 사이 허용 범위:
  - `rag` → `ai.llm` (표 요약 · 질문 확장), `infrastructure.dao` (`keyword_find`의 MySQL LIKE 검색)
  - `ai` → `infrastructure.api` (`cost_korean_won`의 환율 조회)
  - `infrastructure` → 다른 그룹 import 금지 (`core`만 사용)
- `core`는 다른 그룹을 import하지 않는다. (순환 import 방지)
- SQL 문자열은 `infrastructure/dao/`에만, OpenAI 호출은 `ai/llm/`과 `rag/vector_store/embedding.py`에만, 외부 HTTP 호출은 `infrastructure/api/`에만 둔다.
- `load_settings()`는 `main()`에서 한 번만 호출하고 필요한 값만 인자로 넘긴다.

## 4. 모듈별 담당 (기획서 · WBS 역할 분담 기준)

| 경로 (`app/` 생략) | 담당 | 비고 |
|---|---|---|
| `presentation/view/app.py`, `user_view`, `history_view`, `admin_view` | 임세준 | 메인 앱 구조 · 로그인 · 내 기록 · 대시보드 |
| `presentation/view/report_view`, `summary_view` | 김희진 | 업로드 화면 · 요약 화면 |
| `presentation/view/chat_view` | 장유빈 | 채팅 화면 |
| `presentation/view/indicator_view` | 류현수 · 장유빈 | 환율 패널(류현수) / `on_compare` 비교표(장유빈) |
| `presentation/view/term_view` | 류현수 | 용어 카드 |
| `application/service/document_service` | 김희진 · 엄정현 | 업로드 통합(김희진) / `validate_pdf`(엄정현) |
| `application/service/qa_service` | 장유빈 · 서동안 | `ask_stream`(장유빈) / 입력 검증 · 마스킹(서동안) |
| `application/service/summary_service` | 김희진 | |
| `application/service/report_service`, `indicator_service` | 장유빈 | 보고서 목록 · 지표 비교표 |
| `application/service/ecos_finder` | 엄정현 | |
| `application/service/user_service`, `history_service`, `dashboard_service` | 임세준 | |
| `rag/ingestion/loader/` | 엄정현 | PDF · 표 추출 |
| `rag/ingestion/splitter/`, `rag/vector_store/` | 김희진 | 임베딩 · Chroma (splitter는 확인 필요) |
| `rag/retriever/search.py` | 장유빈 · 김희진 | RAG 검색(장유빈) / `keyword_find`(김희진) |
| `ai/llm/`, `ai/prompt/rag_prompt`, `ai/prompt/persona_prompt` | 서동안 | 공통 LLM 모듈 · 질의응답 프롬프트 · 페르소나 |
| `ai/prompt/summary_prompt`, `ai/router/`, `ai/parser/` | 김희진 | 요약 · Tool Calling · 구조화 출력 (parser는 확인 필요) |
| `ai/memory/` | 임세준 · 장유빈 | 대화 기록(임세준) / `rewrite_question`(장유빈) |
| `ai/source/` | 장유빈 | 출처 정리 |
| `ai/suggest/` | 류현수 | 추천 질문 |
| `infrastructure/dao/db.py`, `sql/schema.sql` | 장유빈 | DB 설계 · 연결 |
| `infrastructure/dao/report_dao` | 김희진 · 장유빈 | INSERT(김희진) / `select_reports`(장유빈) |
| `infrastructure/dao/user_dao`, `qa_log_dao`, `dashboard_dao`, `infrastructure/config/`, `core/util/` | 임세준 | 설정 모듈 · 예외 처리 |
| `infrastructure/api/ecos_client` | 엄정현 | ECOS |
| `infrastructure/api/exchange_client`, `stdict_client` | 류현수 | 환율 · 국어원 |
| `core/domain/`, `core/exception/` | 각 영역 담당 | 자기 영역 파일만 수정 |
| `infra/`, 폴더 구조 · 환경 세팅 | 류현수 | |
| `tests/` | 서동안 (전반) · 각자 단위 테스트 | |

> ⚠️ 기능명세서 시트 제목의 담당자(예: "문서처리 – 팀원1 류현수", "화면통합 – 팀원6 장유빈")는 기획서 · WBS의 역할 분담과 다릅니다. 위 표는 **기획서 · WBS 기준**이며, 확정 후 명세서 시트 제목을 맞춰 주세요.
> 명세서의 "패키지명" 열은 그대로 두고, 필요하면 "경로" 열(예: `app/rag/retriever`)을 추가하면 됩니다.

## 5. 결정이 필요한 사항 (명세서 검토 중 발견)

| # | 내용 | 제안 |
|---|---|---|
| 1 | `upload_report()`가 호출하는 `make_child_chunks()`, `table_loader`가 호출하는 `ocr_page()`, `ask_stream()`이 호출하는 `route()`, `get_parent_sections()`가 명세서에 정의되어 있지 않음 | 각각 `rag/ingestion/splitter/text_splitter.py`, `rag/ingestion/loader/pdf_loader.py`, `ai/llm/llm_client.py`, `infrastructure/dao/report_dao.py`에 추가 |
| 2 | `on_request()`는 `run_with_tools()`를, `tool_router`는 `run_agent_with_tools()`를 정의 | `run_agent_with_tools()`로 통일 |
| 3 | `ai/router/tool_router.py`의 `TOOL_MAP`이 요약 · 검증 · 병합 · ECOS 판단(= `application/service` 함수)을 실행해야 해서 의존 방향이 거꾸로 됨 | ① `tool_router.py`를 `application/service/`로 옮기거나 ② `TOOL_MAP`을 `application`에서 만들어 `run_agent_with_tools(tool_map=…)`로 주입 |
| 4 | 환율 조회가 `ecos_client.get_ecos_exchange_rate()`와 `exchange_client.get_exchange_rate()` 두 곳에 있음 (기본값 상수도 각각) | 하나를 주 경로로 정하고 다른 하나는 fallback |
| 5 | `report_service.list_reports()`는 `REPORTS` 딕셔너리 + `reports/` 폴더 기준, `search_reports()`는 DB 기준 | DB(`reports` 테이블)로 통일하고 원본 경로는 `data/raw/` |
| 6 | `register()`는 비밀번호를 그대로 저장 · `user_type='admin'`으로 저장, 서비스 기능 정의서는 `SHA2()` 해시 | 해시 저장 + 일반 가입은 `user`, 관리자 코드 일치 시 `admin` |
| 7 | `User.role`과 `register(user_type)` 이름이 다름 | `role`로 통일 |
| 8 | `report_service.py`, `report_dao.py`, `qa_service.py`, `indicator_view.py`를 두 명이 함께 수정 | 함수 단위로 담당을 나누고 PR을 작게 유지 |
| 9 | `ask_llm()`의 반환 타입 `Usage` 정의 위치 없음 | OpenAI SDK의 `CompletionUsage` 사용 또는 `core/domain/answer.py`에 정의 |

## 6. 의존성 (pyproject 추가 예정 목록 · 참고용)

- 런타임: `openai`, `pydantic>=2`, `gradio>=4,<5`, `chromadb`, `pypdf`, `pdfplumber`, `pymysql`, `python-dotenv`, `numpy`, `pandas`, `matplotlib`
- 기획서 명시: `langchain` (현재 명세서 코드는 OpenAI SDK 직접 호출이라 사용 범위 확인 필요)
- 개발용(`--group dev`): `pytest`, `reportlab`(샘플 PDF 생성)

## 7. 실행 · 테스트 (구조 확정 후)

```bash
poetry install
poetry run python -m app.main     # http://localhost:7860
poetry run pytest
```

- 항상 **레포 루트에서** 실행한다. (`app` 패키지를 찾기 위해)
- `.env.example`에 `ECOS_API_KEY`, `STDICT_API_KEY`, `DB_HOST/PORT/USER/PASSWORD/NAME`, 모델명 · 단가 항목을 추가한다.
