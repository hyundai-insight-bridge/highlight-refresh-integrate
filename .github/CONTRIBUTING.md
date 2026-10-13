# Contributing Guide

이 문서는 우리 팀의 GitHub 협업 규칙입니다. 작업을 시작하기 전에 꼭 읽어주세요.
규칙이 바뀌면 이 문서를 먼저 수정하고 공지합니다.

## TL;DR(핵심 요약)

- `main`에 직접 push할 수 없습니다.
- 모든 작업은 **이슈 → 브랜치 → PR → 승인 → merge** 순서로 진행합니다.
- merge하려면 **@HyeonsuRyu의 승인**이 필요합니다.

---

## 1. 작업 순서

```bash
# 1) 최신 main 받기
git switch main
git pull

# 2) 작업 브랜치 만들기
git switch -c feat/#12-login

# 3) 작업 후 커밋
git add .
git commit -m "feat: 로그인 화면 추가"

# 4) 원격에 push
git push -u origin feat/#12-login
```

5. GitHub에서 `main`을 대상으로 **Pull Request**를 생성합니다.
6. 리뷰 코멘트를 반영하고 승인을 받으면 merge합니다.
7. merge된 브랜치는 삭제합니다.

> 작업 중에 `main`이 업데이트되었다면 `git pull origin main`으로 내 브랜치에 반영한 뒤 충돌을 해결해주세요.

## 2. 이슈

- 작업을 시작하기 전에 **이슈를 먼저 생성**하고 본인을 Assignee로 지정합니다.
- 이슈 하나에는 작업 하나만 담습니다.

## 3. 브랜치 이름

```
<타입>/#<이슈번호>-<짧은-설명>
```

| 타입 | 용도 | 예시 |
|---|---|---|
| `feat` | 새 기능 | `feat/#12-login` |
| `fix` | 버그 수정 | `fix/#15-null-error` |
| `refactor` | 동작 변경 없는 코드 개선 | `refactor/#20-split-utils` |
| `docs` | 문서 | `docs/#3-readme` |
| `chore` | 설정, 빌드, 기타 | `chore/#8-gitignore` |

## 4. 커밋 메시지

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
| `chore` | 설정, 빌드, 패키지 등 |

```
feat: 로그인 화면 추가
fix: 비밀번호 검증 시 null 오류 수정
docs: README 실행 방법 추가
```

- 요약은 50자 이내로, 마침표 없이 씁니다.
- 커밋 하나에는 변경 하나만 담습니다.

## 5. Pull Request

### 작성 규칙
- 제목은 커밋 메시지와 같은 형식으로 씁니다. 예: `feat: 로그인 화면 추가`
- 본문에 **무엇을, 왜** 바꿨는지 적습니다.
- 관련 이슈를 연결합니다. 본문에 `Closes #12`라고 쓰면 merge될 때 이슈가 자동으로 닫힙니다.
- PR은 **작게** 유지합니다. 변경이 300줄을 넘으면 나눌 수 있는지 먼저 고민해주세요.
- 작업이 덜 끝났다면 **Draft PR**로 올립니다.
  - Draft PR은 중간 점검이 필요하거나, 진행 상황을 공유할 때 사용할 수 있습니다.

### merge 조건
아래 조건을 모두 만족해야 merge할 수 있습니다.

- [ ] Code Owner(@HyeonsuRyu) 승인 **1개**
- [ ] 모든 리뷰 대화(conversation) **Resolve** 완료
- [ ] 승인 이후 새 커밋이 없을 것. 새 커밋을 올리면 **승인이 취소**되어 다시 받아야 합니다.

## 6. 코드 리뷰

### 리뷰어
- 리뷰와 merge 승인은 **@HyeonsuRyu**가 담당합니다.
- 팀원 간 리뷰도 적극적으로 해주세요. 다만 merge 조건은 Code Owner 승인입니다.

### 대화 Resolve 규칙
- 대화는 **코멘트를 단 사람이 Resolve**합니다.
- PR 작성자는 수정한 뒤 직접 Resolve하지 말고 답글만 남겨주세요.
  ```
  반영했습니다! (a1b2c3d)
  ```
- 반영하지 않기로 했다면 이유를 답글로 남기고 리뷰어와 합의합니다.

### 코멘트 말머리 (권장)
| 말머리 | 의미 |
|---|---|
| `[필수]` | 반드시 수정해야 merge 가능 |
| `[제안]` | 개선 의견, 반영 여부는 작성자 판단 |
| `[질문]` | 이해를 위한 질문 |

## 7. 브랜치 보호 규칙 (`main`)

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
- @HyeonsuRyu의 PR은 본인이 승인할 수 없으므로, **관리자 bypass 권한으로 merge**합니다.
  팀원 리뷰는 언제든 환영합니다.

## 8. 하지 말아야 할 것

- ❌ API 키, 비밀번호, 토큰 등 **비밀 정보 커밋** (`.env`는 `.gitignore`에 포함)
- ❌ 다른 사람의 브랜치에 허락 없이 push
- ❌ 리뷰 코멘트를 반영하지 않고 Resolve
- ❌ 하나의 PR에 관련 없는 변경 여러 개 섞기

> 실수로 비밀 정보를 커밋했다면 **즉시 팀장, 강사님에게 알려주세요.**
> 커밋을 지워도 기록이 남기 때문에 해당 키를 폐기하고 새로 발급해야 합니다.

---

궁금한 점은 Discussions에 남겨주세요.