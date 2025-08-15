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

```svg
<svg width="700" height="450" viewBox="0 0 700 450" xmlns="http://www.w3.org/2000/svg">
  <style>
    .boundary { fill: none; stroke: #333; stroke-width: 2; stroke-dasharray: 5,5; }
    .box { fill: #E3F2FD; stroke: #2196F3; stroke-width: 2; }
    .db { fill: #E8F5E9; stroke: #4CAF50; stroke-width: 2; }
    .hw { fill: #FFF3E0; stroke: #FF9800; stroke-width: 2; }
    .text { font-family: Arial, sans-serif; font-size: 14px; }
    .title { font-size: 16px; font-weight: bold; }
    .arrow { stroke: #333; stroke-width: 2; marker-end: url(#arrowhead); }
  </style>

  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#333" />
    </marker>
  </defs>

  <!-- Boundaries -->
  <rect x="10" y="10" width="330" height="430" class="boundary" />
  <text x="20" y="30" class="title">Main Thread (GUI)</text>

  <rect x="360" y="10" width="330" height="430" class="boundary" />
  <text x="370" y="30" class="title">Worker Thread (I/O)</text>

  <!-- Main Thread Components -->
  <rect x="30" y="50" width="290" height="60" class="box" />
  <text x="175" y="85" class="text" text-anchor="middle">HVMonitor (QMainWindow)</text>

  <rect x="30" y="180" width="290" height="60" class="box" />
  <text x="175" y="215" class="text" text-anchor="middle">update_gui_from_data() Slot</text>

  <rect x="30" y="320" width="290" height="60" class="box" />
  <text x="175" y="355" class="text" text-anchor="middle">PyQt5 GUI Rendering</text>

  <!-- Worker Thread Components -->
  <rect x="380" y="50" width="290" height="60" class="box" />
  <text x="525" y="85" class="text" text-anchor="middle">DataWorker (QObject)</text>

  <rect x="380" y="130" width="290" height="60" class="box" />
  <text x="525" y="165" class="text" text-anchor="middle">poll_data() - 1s Timer</text>

  <rect x="380" y="210" width="290" height="60" class="box" />
  <text x="525" y="245" class="text" text-anchor="middle">fetch_data_bulk_optimized()</text>
  
  <rect x="380" y="290" width="290" height="60" class="box" />
  <text x="525" y="325" class="text" text-anchor="middle">commit_to_db() - 60s Timer</text>

  <!-- External Components -->
  <rect x="500" y="370" width="170" height="50" class="db" />
  <text x="585" y="400" class="text" text-anchor="middle">MariaDB</text>

  <rect x="380" y="370" width="100" height="50" class="hw" />
  <text x="430" y="400" class="text" text-anchor="middle">CAEN HV</text>

  <!-- Arrows and Interactions -->
  <path d="M 340 85 L 360 85" class="arrow" />
  <text x="350" y="70" class="text" text-anchor="middle">Starts</text>

  <!-- Signal/Slot Connection (Simplified representation) -->
  <path d="M 360 160 L 340 200" class="arrow" stroke-dasharray="5,3" />
  <text x="300" y="170" class="text" text-anchor="end">data_fetched Signal</text>

  <path d="M 175 240 L 175 320" class="arrow" />
  <text x="180" y="280" class="text">Updates UI</text>

  <path d="M 525 190 L 525 210" class="arrow" />

  <path d="M 430 370 L 430 270" class="arrow" />
  <text x="435" y="320" class="text">Bulk Read</text>

  <path d="M 525 350 L 585 370" class="arrow" />
  <text x="560" y="360" class="text" text-anchor="start">Batch Insert</text>

</svg>
