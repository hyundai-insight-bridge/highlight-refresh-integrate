# Contributing Guide

이 문서는 우리 팀의 GitHub 협업 규칙입니다. 작업을 시작하기 전에 꼭 읽어주세요.
규칙이 바뀌면 이 문서를 먼저 수정하고 공지합니다.

## 핵심 요약

- `main`에 직접 push할 수 없습니다.
- 모든 작업은 **이슈 → 브랜치 → PR → 승인 → merge** 순서로 진행합니다.
- merge하려면 **@HyeonsuRyu의 승인**이 필요합니다.
- 패키지 관리는 **Poetry**만 사용합니다.

---

## 1. 개발 환경

| 항목 | 기준 |
|---|---|
| Python | 3.11.x |
| 패키지 관리 | Poetry 2.x |
| 가상환경 | 프로젝트 내부 `.venv/` |

설치 방법은 [README](../README.md)를 참고해주세요.

## 2. 작업 순서

```bash
# 1) 최신 main 받기
git switch main
git pull

# 2) 의존성 동기화 (다른 사람이 패키지를 추가했을 수 있음)
poetry install

# 3) 작업 브랜치 만들기
git switch -c feat/#12-login

# 4) 작업 후 커밋
git add 파일명
git commit -m "feat: 로그인 화면 추가"

# 5) 원격에 push
git push -u origin feat/#12-login
```

6. GitHub에서 `main`을 대상으로 **Pull Request**를 생성합니다. (템플릿을 채워주세요)
7. 리뷰 코멘트를 반영하고 승인을 받으면 merge합니다.
8. merge되면 원격 브랜치와 로컬 브랜치는 **직접 정리**해주세요.
   ```bash
   git switch main
   git pull --prune
   git branch -d feat/#12-login
   ```

> 작업 중 `main`이 업데이트되었다면 PR의 **Update branch** 버튼을 누르거나 `git pull origin main`으로 반영합니다.
> Update branch는 반드시 **Update with merge commit**을 선택하세요. (rebase 사용 금지)

## 3. 이슈

- 작업을 시작하기 전에 **이슈를 먼저 생성**하고 본인을 **Assignee**로 지정합니다.
- 템플릿을 선택해 작성합니다.

| 템플릿 | 용도 | 라벨 |
|---|---|---|
| 기능 개발 | 새 기능 | `enhancement` (자동) |
| 버그 제보 | 버그 | `bug` (자동) |
| 작업 | 문서, 리팩터링, 테스트, 설정, 환경 등 | `documentation` 또는 `chore` (직접 선택) |

- 제목은 **할 일이 드러나게** 작성합니다. 예) `PDF 업로드 기능 추가`
- 말머리(`[feat]` 등)는 제목에 쓰지 않고 **라벨**로 구분합니다.
- 이슈 하나에는 작업 하나만 담습니다.
- 질문이나 아이디어는 이슈 대신 **Discussions**에 남깁니다.

## 4. 브랜치 이름

```
<타입>/#<이슈번호>-<짧은-설명>
```

| 타입 | 용도 | 예시 |
|---|---|---|
| `feat` | 새 기능 | `feat/#12-login` |
| `fix` | 버그 수정 | `fix/#15-pdf-encoding` |
| `refactor` | 동작 변경 없는 코드 개선 | `refactor/#20-split-utils` |
| `docs` | 문서 | `docs/#3-readme` |
| `chore` | 설정, 환경, 의존성 | `chore/#8-add-ruff` |
| `test` | 테스트 | `test/#25-retriever` |
| `style` | UI | `sttyle/#44-update-ui` |

> 이슈 번호는 GitHub가 자동으로 붙입니다. 이슈를 만든 뒤 **실제 번호를 확인**해서 사용하세요.

## 5. 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/ko/) 형식을 따릅니다.

```
<타입>: <요약>
```

| 타입 | 용도 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 리팩터링 |
| `docs` | 문서 수정 |
| `test` | 테스트 추가·수정 |
| `style` | 포맷 변경 (동작 변경 없음) |
| `chore` | 설정, 환경, 의존성 등 |

```
feat: PDF 업로드 기능 추가
fix: 한글 PDF 인코딩 오류 수정
docs: README 실행 방법 추가
```

- 요약은 50자 이내로, 마침표 없이 씁니다.
- 커밋 하나에는 변경 하나만 담습니다.
- **merge commit 방식을 사용하므로 모든 커밋이 `main`에 그대로 남습니다.** `수정`, `ㅇㅇ`, `asdf` 같은 메시지는 쓰지 마세요.

## 6. Pull Request

### 작성 규칙
- PR 템플릿을 채워서 작성합니다.
- 제목은 커밋 메시지와 같은 형식으로 씁니다. 예) `feat: PDF 업로드 기능 추가`
- 본문에 **`Closes #이슈번호`** 를 꼭 적습니다. merge될 때 이슈가 자동으로 닫힙니다.
  - ⚠️ merge 후에 추가하면 이슈가 자동으로 닫히지 않습니다.
- PR은 **작게** 유지합니다. 변경이 300줄을 넘으면 나눌 수 있는지 먼저 고민해주세요.
- 작업이 덜 끝났다면 **Draft PR**로 올리고, 완료되면 **Ready for review**를 누릅니다.

### merge 조건
- [ ] Code Owner(@HyeonsuRyu) 승인 **1개**
- [ ] 모든 리뷰 대화(conversation) **Resolve** 완료
- [ ] 승인 이후 새 커밋이 없을 것. 새 커밋을 올리면 **승인이 취소**되어 다시 받아야 합니다.

> 승인 후에는 **Update branch를 누르지 말고** 바로 merge해주세요. 새 커밋이 생겨 재승인이 필요해집니다.

### merge 방식
- **Merge commit** 방식만 사용합니다.
- 브랜치의 커밋이 모두 `main`에 남으므로 커밋 메시지 규칙을 꼭 지켜주세요.

## 7. 코드 리뷰

### 리뷰어
- 리뷰와 merge 승인은 **@HyeonsuRyu**가 담당합니다.
- 팀원 간 리뷰와 Approve도 환영합니다. 다만 merge 조건은 Code Owner 승인입니다.

### 대화 Resolve 규칙
- 대화는 **코멘트를 단 사람이 Resolve**합니다.
- PR 작성자는 수정한 뒤 직접 Resolve하지 말고 답글만 남겨주세요.
  ```
  반영했습니다! (a1b2c3d)
  ```
- 반영하지 않기로 했다면 이유를 답글로 남기고 리뷰어와 합의합니다.

### 코멘트 말머리
| 말머리 | 의미 |
|---|---|
| `[필수]` | 반드시 수정해야 merge 가능 |
| `[제안]` | 개선 의견, 반영 여부는 작성자 판단 |
| `[질문]` | 이해를 위한 질문 |

## 8. 브랜치 보호 규칙 (`main`)

| 규칙 | 내용 |
|---|---|
| 삭제 금지 | `main` 브랜치를 삭제할 수 없습니다 |
| Force push 금지 | `git push --force`를 할 수 없습니다 |
| PR 필수 | 직접 push할 수 없고 PR로만 merge할 수 있습니다 |
| 승인 필요 | Code Owner 승인 1개가 필요합니다 |
| 재승인 | 승인 후 새 커밋을 올리면 다시 승인을 받아야 합니다 |
| 대화 해결 | 모든 리뷰 대화가 Resolve되어야 합니다 |

### Code Owners

```
* @HyeonsuRyu
```

- 모든 파일의 Code Owner는 @HyeonsuRyu입니다.
- @HyeonsuRyu의 PR은 본인이 승인할 수 없으므로 **관리자 bypass 권한으로 merge**합니다. 팀원 리뷰는 언제든 환영합니다.

## 9. 브랜치 전략

- 브랜치는 `main`, `develop`, `feat`, `fix` 4가지를 사용합니다.
- `main`
  - 안정된 코드를 유지하는 브랜치입니다.
  - 직접 기능 개발을 하지 않습니다.
- `develop`
  - 개발 통합 브랜치입니다. 기능 개발 및 수정이 완료된 브랜치를 병합하여 통합 테스트를 진행합니다.
  - `main`에 merge한 후에도 삭제하지 않고, 계속하여 사용합니다.
- `feat`
  - `develop` 브랜치에서 분기하며, 새로운 기능을 개발할 때 사용합니다.
  - 개발 완료 후 `develop`으로 병합합니다.
- `fix`
  - 버그를 수정하기 위한 브랜치입니다. `develop`에서 분기하여 사용합니다.
  - 단, `main`에 긴급 수정이 필요한 경우 `main`에서 분기하고 수정 결과를 `main`과 `develop`에 모두 반영합니다.

## 10. 의존성 관리

- 패키지 관리는 **Poetry 2.x**만 사용합니다. (`pip install`, `uv add`, `uv sync` 금지)
- 패키지 추가: `poetry add 패키지명`
- 개발용 패키지 추가: `poetry add --group dev 패키지명`
- `pyproject.toml`과 `poetry.lock`은 **반드시 같은 커밋**에 포함합니다.
- pull 후 다른 사람이 패키지를 추가했다면 `poetry install`을 실행합니다.
- `poetry.lock` 충돌 시 직접 수정하지 말고, `pyproject.toml` 충돌을 해결한 뒤 재생성합니다.
  ```bash
  poetry lock
  ```
- 패키지 추가·삭제는 가능하면 **별도 PR**로 올려주세요.

## 11. 코드 스타일

[PEP 8](https://peps.python.org/pep-0008/)을 기준으로 작성합니다.

### 네이밍 규칙

| 대상 | 규칙 | 예시 |
|---|---|---|
| 클래스 | `PascalCase` | `PdfLoader`, `ChatService` |
| 함수 · 메서드 | `snake_case` | `load_pdf()`, `get_answer()` |
| 변수 · 인자 | `snake_case` | `user_query`, `chunk_size` |
| 상수 | `UPPER_SNAKE_CASE` | `MAX_TOKENS`, `DEFAULT_MODEL` |
| 모듈(파일) · 패키지 | 짧은 `snake_case` | `pdf_loader.py`, `retriever/` |
| 내부용(private) | 앞에 `_` | `_parse_page()` |

### 기타
- 들여쓰기는 **탭을**을 사용합니다. (스페이스 4번 금지)
- 기능별로 파일을 나누고, 실행 파일은 모듈을 불러와 실행하는 구조로 작성합니다.
- 본인이 작성한 함수·클래스에는 **docstring 또는 주석**을 꼭 남깁니다.
  
## 12. 하지 말아야 할 것

- ❌ API 키, 비밀번호, 토큰 등 **비밀 정보 커밋** (`.env`는 커밋하지 않고 `.env.example`만 커밋)
- ❌ 노트북(`.ipynb`)을 **실행 결과가 남은 채로** 커밋
- ❌ 벡터DB, 원본 PDF 등 **대용량 파일** 커밋 (`vectorstore/`, `data/raw/` 사용)
- ❌ 다른 사람의 브랜치에 허락 없이 push
- ❌ 리뷰 코멘트를 반영하지 않고 Resolve
- ❌ 하나의 PR에 관련 없는 변경 여러 개 섞기

> 실수로 비밀 정보를 커밋했다면 **즉시 팀장, 강사님에게 알려주세요.**
> 커밋을 지워도 기록이 남기 때문에 해당 키를 폐기하고 새로 발급해야 합니다.

---

궁금한 점은 Discussions에 남겨주세요.
