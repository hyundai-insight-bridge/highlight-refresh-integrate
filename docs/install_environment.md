# 1. 저장소 받기
git clone <저장소 URL>
cd <저장소 폴더>

# 2. 환경 생성 및 설치
poetry env use 3.11
poetry install

# 3. 환경 변수
Copy-Item .env.example .env   # 이후 .env에 키 입력

# 4. 확인
poetry run python --version