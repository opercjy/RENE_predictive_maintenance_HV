# RENE HV Monitor - Optimized Version

이 프로젝트는 CAEN SY4527LC 고전압 시스템을 모니터링하고, 데이터를 MariaDB에 로깅하며, PyQt5 GUI로 실시간 시각화하는 애플리케이션입니다. 기존 `hv_push_v2.py`의 심각한 성능 문제와 아키텍처 결함을 해결하기 위해 전면적으로 리팩토링되었습니다.

## 주요 개선 사항 및 최적화 내역

### 1. 성능 최적화: 일괄 읽기(Bulk Read) 구현 (97% 통신량 감소)

*   **문제점 (v2):** 매 주기마다 약 672번의 네트워크 요청(96채널 × 7파라미터)이 발생하여 심각한 지연이 발생했습니다.
*   **개선 (Optimized):** `caenhvwrapper`의 일괄 읽기 기능을 사용하여 통신 횟수를 주기당 21회(3슬롯 × 7파라미터)로 줄였습니다.

### 2. 아키텍처 개선: 멀티스레딩 도입 (GUI 응답성 확보)

*   **문제점 (v2):** 네트워크 통신(I/O)이 메인 GUI 스레드에서 실행되어, 통신 지연 시 GUI 전체가 멈추는 현상(Freezing)이 발생했습니다.
*   **개선 (Optimized):** 데이터 수집 및 DB 작업을 별도의 워커 스레드(`QThread`)로 분리했습니다. GUI는 통신 상태와 관계없이 항상 반응성을 유지합니다. 데이터는 시그널/슬롯(Signal/Slot) 메커니즘을 통해 스레드 간 안전하게 전달됩니다.

### 3. 데이터베이스 로직 수정 (치명적 버그 해결)

*   **문제점 (v2):** 배치 삽입(`executemany`)과 `commit`이 반복문 내부에 잘못 위치하여 비정상적인 DB 부하가 발생했습니다.
*   **개선 (Optimized):** 모든 데이터를 수집한 후, 단 한 번의 배치 삽입 및 커밋을 수행하도록 수정했습니다.

### 4. 유지보수성 향상

*   **설정 관리:** 접속 정보와 환경 설정을 외부 `config.json` 파일로 분리했습니다.
*   **로깅 도입:** 표준 `logging` 모듈을 도입하여 시스템 상태 추적 및 디버깅을 용이하게 했습니다.

## 최적화된 아키텍처 다이어그램

데이터 수집 및 DB 작업은 워커 스레드에서 처리되며, GUI는 메인 스레드에서 안전하게 업데이트됩니다.

<img width="699" height="449" alt="image" src="https://github.com/user-attachments/assets/b1138ba4-b6e6-43ad-8630-f44842cc60bc" />


## 요구 사항

*   Python 3.8+
*   PyQt5
*   CAEN HV Wrapper Library (`C/C++`)
*   CAEN HV Wrapper Python Binding Library (`https://github.com/caenspa/py-caen-libs`)
*   MariaDB Connector/Python (`mariadb`)

## 설치 및 실행

1.  **의존성 설치:**
    ```bash
    pip install PyQt5 mariadb
    ```
    (`caen_libs`는 CAEN에서 제공하는 설치 절차를 따르십시오.)

2.  **구성:**
    `config.json` 파일을 생성하고 실제 환경에 맞게 CAEN 및 MariaDB 접속 정보를 수정합니다.

3.  **좌표 설정:**
    `RENE_HV.py` 파일 내부의 `LABEL_POSITIONS` 딕셔너리가 사용자의 `DISPLAY_MAP` 설정 및 배경 이미지(`RENE_VETO_FOR_HV4.png`)와 일치하는지 확인합니다.

4.  **실행:**
    ```bash
    python RENE_HV.py
    ```
```
