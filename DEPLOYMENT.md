# YuE Studio 배포

## 연주곡 LoRA 배포 (2026-09-24)

- 출처: [Mothersuperior/YuE2-instrumental-cot-full-loras](https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras). 가중치 라이선스는 **CC BY-NC 4.0**이며 상업적 사용은 허용되지 않는다. 서비스 이용 조건에 맞는지 운영자가 확인한다.
- GPU PC의 `ComfyUI/models/loras/`에 `ar_lora_inst_v3abc_comfyui.safetensors`를 설치한다. 공식 저장소의 **ComfyUI용** 파일을 사용하며 일반 `ar_lora_inst_v3abc.safetensors`와 혼동하지 않는다. 로컬 설치 파일 크기는 212,891,736바이트다. ComfyUI를 재시작하여 LoRA 목록에 나타나는지 확인한다.
- 스튜디오가 `instrumental=true`를 받으면 서버가 가사 입력을 `[instrumental]` 또는 허용된 구간 태그로 정규화하고, 작업 페이로드에 연주곡 플래그를 보낸다. 워커는 ComfyUI `LoraLoader`를 CLIP 경로에 `strength_clip=1.0`, `strength_model=0.0`으로 연결한다. 원곡은 ABC 계획을 항상 생성하고 `mode=full`을 사용한다. 커버 연주곡도 SheetSage ABC와 음악 생성에 `mode=full`을 사용한다. 일반 곡의 그래프는 기존대로다.
- 구간 태그는 `intro`, `verse`, `pre-chorus`, `chorus`, `bridge`, `outro`만 허용한다. 한 줄에 하나씩 쓰거나 `[intro 0:00-0:15]`처럼 순서대로 시간을 지정한다. 가창 가사와 제작 지시문은 연주곡 가사 필드에 넣지 않는다. 시간은 곡 길이의 보장이 아니라 구조 가이드다.
- 배포 순서: 저장소 테스트 → `main` 커밋과 푸시 → Oracle의 `yue2_app/` 변경 파일과 `DEPLOYMENT.md`를 `scp`로 복사 → `yue-studio.service` 재시작 → GPU PC에서 최신 워커 코드와 LoRA 파일 확인 후 ComfyUI 및 워커 재시작. 웹앱과 워커를 함께 갱신해 새 작업 플래그가 끝까지 전달되게 한다.
- 확인: `python -m unittest tests.test_workflow_builder tests.test_distributed_flow -q`, `node --check yue2_app/static/app.js`, `curl -fsS https://yue.codingbot.kr/api/auth/setup-status`. 실제 연주곡 한 건을 제출해 ComfyUI 프롬프트에 `LoraLoader`, `[instrumental]`, `YuE2GenerateABC`, `mode=full`이 들어가는지 확인한다. 가창 곡에는 LoRA가 없어야 한다.

## 현재 구성

- `https://yue.codingbot.kr` → Oracle의 Apache2 vhost → `127.0.0.1:7860`의 `aiohttp` 앱
- Oracle 전용 PostgreSQL 컨테이너 `yue-studio-pg` (`127.0.0.1:5433`)에 계정, 라이브러리, 작업 큐 저장
- 생성 음원·업로드 원본·커버는 Oracle의 `yue2_app/data/`에 저장
- GPU 컴퓨터는 중앙 HTTPS API에 **밖으로 접속**해 작업을 받고, 자기 컴퓨터의 `127.0.0.1:8188` ComfyUI를 사용
- ComfyUI, PostgreSQL, GPU 워커 포트는 인터넷에 공개하지 않음

웹 앱과 워커는 이 저장소에서 함께 관리하지만 각각 실행한다. GPU 컴퓨터에는 PostgreSQL 접속 정보가 필요 없다.

## Oracle 운영 위치

Windows에서 Oracle 서버에 접속할 때는 SSH 별칭을 사용한다.

```powershell
ssh oracle
```

이 별칭은 `C:\Users\admin\.ssh\config`에 설정되어 있으며 `ubuntu@arcade.codingbot.kr`로 접속한다. 배포 파일 복사에도 `oracle:/home/ubuntu/services/yue-studio/` 경로를 사용한다.

## 코드 동기화

로컬 작업본에서 테스트를 통과시킨 뒤 변경 사항을 `main`에 커밋하고 `origin/main`에 푸시한다. Oracle의 애플리케이션 디렉터리는 Git 저장소가 아닌 배포본이므로, 변경된 서버 실행 파일과 정적 파일을 `scp`로 복사하고 해시를 비교한다. 배포본에 커밋 SHA를 `DEPLOYED_COMMIT`으로 기록해 저장소 버전과 대조한다. `venv/`, `secrets/`, `yue2_app/data/`는 코드 동기화 대상에서 제외한다.

정적 CSS를 바꾸면 `index.html`의 CSS 버전 값도 갱신해 기존 브라우저 캐시가 새 스타일을 가리지 않게 한다. 배포 후 `https://yue.codingbot.kr/`의 HTML·CSS 응답과 API 상태를 확인한다.

| 항목 | 경로 또는 이름 |
| --- | --- |
| 애플리케이션 | `/home/ubuntu/services/yue-studio/` |
| Python 환경 | `/home/ubuntu/services/yue-studio/venv/` |
| 서비스 | `yue-studio.service` |
| YuE Apache vhost | `/etc/apache2/sites-available/yue.codingbot.kr.conf` |
| 서비스 환경 변수 | `/home/ubuntu/services/yue-studio/secrets/studio.env` |
| PostgreSQL 컨테이너·볼륨 | `yue-studio-pg`, `yue-studio-pgdata` |

환경 변수 파일에는 `YUE2_DATABASE_URL`, `YUE2_DISPATCH_DSN`, `YUE2_WORKER_TOKENS`, `YUE2_PUBLIC_ORIGIN`, `YUE2_SECURE_COOKIES`가 있다. 토큰과 DB 비밀번호를 Git에 넣지 않는다. 현재 웹 앱이 한 프로세스이므로 여러 프로세스로 늘리기 전에는 WebSocket 이벤트 전달 구조도 확장해야 한다.

설정이나 코드 변경 후에는 YuE만 점검하고 재시작한다.

```bash
sudo apache2ctl -t
sudo systemctl status yue-studio.service
sudo systemctl restart yue-studio.service
curl -fsS https://yue.codingbot.kr/api/auth/setup-status
```

Apache 설정을 바꿀 때는 `sudo apache2ctl -t`가 성공한 뒤에만 `sudo systemctl reload apache2`를 실행한다. Apache에는 다른 사이트가 함께 있으므로 전체 설정 파일을 일괄 수정하지 않는다.

## Windows GPU 워커

1. 이 저장소의 `venv`, `ComfyUI`, YuE2·SheetSage 모델을 준비한다. 모델 파일 이름은 `yue2_3b_bf16.safetensors`, `sheetsage2_bf16.safetensors`이다.
2. 서버 관리자에게 워커 ID와 전용 토큰을 발급받아 서버의 `YUE2_WORKER_TOKENS`에 등록한다.
3. 저장소 루트에 Git에서 제외되는 `.yue2-worker.local.bat`을 만들고 `set "YUE2_WORKER_ID=..."`, `set "YUE2_WORKER_TOKEN=..."`을 적는다.
4. `run_yue2_worker.bat`을 실행한다. ComfyUI가 꺼져 있으면 로컬에서 띄운 뒤 작업을 기다린다. 종료하면 새 작업을 받지 않는다.

GPU 컴퓨터의 ComfyUI는 `127.0.0.1:8188`에만 바인딩한다. 작업 중에는 컴퓨터 절전과 ComfyUI 종료를 피한다. 워커가 연결이 끊겨도 중앙 작업은 보존되며, 임대 시간이 지난 작업은 다시 배정될 수 있다. 같은 작업의 늦게 도착한 결과는 수락하지 않는다.

## 보관과 백업

PostgreSQL DB만 백업하면 음악 파일은 복구되지 않는다. `pg_dump`로 YuE 전용 DB를 백업하고 `yue2_app/data/`의 `covers/`, `outputs/`, `sources/`도 함께 보관한다. 기존 SQLite DB는 이전 시점의 백업으로 남겨 두었으며 운영 중인 원본은 PostgreSQL이다. Oracle의 디스크 사용량을 확인하고 오래된 업로드 원본의 보존 기간을 정해야 한다.
