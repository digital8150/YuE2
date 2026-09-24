# YuE2 Studio GPU 워커 설치 요청서

이 문서를 GPU PC의 코딩 에이전트(Codex 등)에 전달하고 다음처럼 요청하세요.

> 이 문서대로 이 PC에 YuE2 Studio GPU 워커를 설치하고 연결까지 확인해 줘. 필요한 모델 다운로드 위치와 용량을 먼저 알려 줘. 내가 스튜디오에서 발급받은 연결 설정은 요청할 때 전달할게.

## 사용자 준비

1. Studio에 로그인하고 **대기열 → 내 GPU 기여하기 → 연결 키 발급**에서 이 PC의 이름을 입력합니다.
2. 발급 직후 표시되는 세 줄의 설정을 복사해 에이전트에 전달합니다. 토큰은 이 화면에서 한 번만 보입니다. 분실하면 워커를 연결 해제하고 새 키를 발급하세요.
3. GPU와 드라이버, 여유 디스크 공간, 모델 라이선스를 확인합니다. 모델은 여러 GB입니다. 설치 전 에이전트가 다운로드 크기와 출처를 보여주게 하세요.
4. 음악 생성 중에는 PC의 절전과 ComfyUI/워커 종료를 피합니다.

## 에이전트 작업 지침

대상은 **사용자 자신의 GPU PC**입니다. Studio 서버나 PostgreSQL을 설치하거나 수정하지 마세요. 워커는 Studio HTTPS API에 바깥으로 접속하고, ComfyUI는 이 PC의 `127.0.0.1:8188`에서만 실행합니다. 8188 포트를 외부에 개방하지 마세요.

### 1. 환경 확인

- OS, GPU, VRAM, 드라이버, Python, Git, 디스크 여유 공간을 확인하고 설치 경로를 사용자와 정하세요. 저장소: `https://github.com/digital8150/YuE2.git`.
- Windows를 기본 대상으로 합니다. 다른 OS에서는 `run_yue2_worker.bat` 대신 같은 환경 변수로 `python -m yue2_app.worker`를 실행할 수 있습니다.
- 이 저장소의 `ComfyUI/`와 `venv/`는 Git에서 제외되어 있습니다. 클론만으로 실행할 수 없으므로 별도로 준비해야 합니다.

### 2. ComfyUI와 모델 준비

- [공식 ComfyUI](https://github.com/Comfy-Org/ComfyUI)를 저장소 루트의 `ComfyUI/`에 설치하세요. 사용하는 ComfyUI 버전에 `YuE2GenerateABC`, `YuE2GenerateMusic`, `SheetSage2AudioToABC`, `EmptyYuE2LatentAudio` 노드가 있는지 `/object_info`에서 확인하세요. 누락되면 YuE2 지원 버전을 확인해 설치하고 재검증하세요.
- 저장소 루트에 Python 가상환경 `venv/`를 만들고 ComfyUI의 GPU에 맞는 PyTorch 및 의존성과 루트의 `requirements-server.txt`를 설치하세요. PyTorch 설치 명령은 이 PC의 OS, GPU, 드라이버에 맞춰 공식 안내로 결정하세요.
- [Comfy-Org/YuE2 모델 저장소](https://huggingface.co/Comfy-Org/YuE2/tree/main)에서 `yue2_3b_bf16.safetensors`를 받아 `ComfyUI/models/checkpoints/yue2/`에, `sheetsage2_bf16.safetensors`를 받아 `ComfyUI/models/audio_encoders/yue2/`에 둡니다. 모델 라이선스를 사용자에게 보여주고 확인한 뒤 다운로드하세요. 파일 이름이 정확해야 합니다.
- 연주곡 작업도 받으려면 [ComfyUI용 연주곡 LoRA](https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras/tree/main)의 `ar_lora_inst_v3abc_comfyui.safetensors`를 `ComfyUI/models/loras/`에 설치하세요. 일반 `ar_lora_inst_v3abc.safetensors`와 다릅니다. 이 모델은 CC BY-NC 4.0입니다. 이 파일이 없으면 연주곡 작업이 실패할 수 있습니다.
- ComfyUI를 `127.0.0.1:8188`에 실행하고 `/system_stats`와 `/object_info`가 응답하는지 확인하세요. GPU 인식과 위 노드·모델 선택 가능 여부도 확인하세요.

### 3. 워커 연결

- 사용자가 제공한 세 줄의 `set "..."` 설정을 저장소 루트의 `.yue2-worker.local.bat`에 저장하세요. 이 파일은 Git에서 제외됩니다. 토큰을 채팅 로그, 스크린샷, 커밋, 이슈, 원격 서버에 다시 노출하지 마세요.
- `YUE2_SERVER_URL`은 로그인한 Studio의 HTTPS 주소여야 합니다. `YUE2_WORKER_ID`와 `YUE2_WORKER_TOKEN`은 발급받은 값을 그대로 사용하세요.
- Windows에서는 저장소 루트의 `run_yue2_worker.bat`을 실행하세요. ComfyUI가 꺼져 있으면 배치 파일이 로컬에서 실행합니다. 워커 창은 연결을 유지하는 동안 열어 둡니다.
- Studio **대기열 → 연결된 GPU 워커**에 이름과 장치가 나타나고 상태가 **유휴**인지 확인하세요. 작업을 받으면 **작업 중**과 진행 속도가 표시됩니다. 첫 진행 샘플 이전에는 속도가 비어 있을 수 있습니다.

### 4. 끝나기 전 확인

- 테스트용 곡 한 건을 실행해 워커가 작업을 받고, ComfyUI가 생성하고, Studio에 결과가 돌아오는지 확인하세요. 테스트 작업은 실제 GPU 시간과 저장 공간을 사용하므로 사용자에게 먼저 알려 주세요.
- 문제를 만나면 워커 콘솔 오류, ComfyUI 로그, 모델 파일 위치, `/object_info`, `/system_stats` 응답을 확인하세요. 비밀 토큰은 로그에 출력하지 마세요.
- 사용자에게 설치 위치, 실행 방법, 자동 시작 여부, 확인 결과, 남은 문제를 요약하세요. 자동 시작 설정은 사용자가 원하는 경우에만 하세요.

## 연결 해제

Studio의 **내 워커 → 연결 해제**를 누르면 키가 즉시 폐기됩니다. 워커 프로세스도 종료하고 `.yue2-worker.local.bat`을 삭제하세요. 새 키로 다시 연결할 수 있습니다.
