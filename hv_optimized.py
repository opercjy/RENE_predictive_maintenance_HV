import sys
import time
import logging
import os
import json
from typing import Dict, Optional, Any

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QScrollArea, QGraphicsScene, QGraphicsView, QGraphicsProxyWidget, QGraphicsPathItem
# 스레딩 및 시그널 관련 임포트
from PyQt5.QtCore import Qt, QTimer, QRectF, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPixmap, QPainterPath, QBrush

# CAEN 라이브러리 임포트
try:
    from caen_libs import caenhvwrapper as hv
except ImportError:
    logging.error("Failed to import caenhvwrapper. Ensure caen_libs is installed.")
    hv = None

# MariaDB 임포트
try:
    import mariadb
except ImportError:
    logging.warning("mariadb module not found. Database logging will be disabled.")
    mariadb = None

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

# ==============================================================================
# 설정 및 상수 로드 (Configuration and Constants)
# ==============================================================================

def load_config(config_file="config.json"):
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from the configuration file: {config_file}")
        sys.exit(1)

CONFIG = load_config()

# Crate Map 정보
CRATE_MAP = {
    1: {'model': 'A7030P', 'channels': 48},
    4: {'model': 'A7435SN', 'channels': 24},
    8: {'model': 'A7435SN', 'channels': 24},
}

# 수집할 파라미터 목록
PARAMETERS_TO_FETCH = ['Pw', 'POn', 'PDwn', 'VMon', 'IMon', 'V0Set', 'I0Set']

# Display Map 정보 (운영 환경에서는 고정 값 사용 권장)
# import random
# DISPLAY_MAP_4 = sorted(random.sample(range(24), 18)) # 기존 랜덤 방식
DISPLAY_MAP_4 = sorted(list(range(18))) # 예시: 0~17번 채널 사용

DISPLAY_MAP = {
    1: [0, 1],
    4: DISPLAY_MAP_4,
    8: list(range(8, 24)),
}

# Label Positions 정보 (실제 좌표로 설정 필요)
# 참고: hv_push_v2.py의 좌표 데이터를 기반으로 하되, DISPLAY_MAP_4 설정에 맞춰야 합니다.
LABEL_POSITIONS = {
    (1, 0): (613, 610), (1, 1): (1130, 610),
    # Slot 4 (DISPLAY_MAP_4의 인덱스에 따라 좌표 할당)
    (4, DISPLAY_MAP_4[0]): (410, 546), (4, DISPLAY_MAP_4[1]): (1324, 538),
    (4, DISPLAY_MAP_4[2]): (406, 454), (4, DISPLAY_MAP_4[3]): (1324, 450),
    (4, DISPLAY_MAP_4[4]): (410, 358), (4, DISPLAY_MAP_4[5]): (1329, 356),
    (4, DISPLAY_MAP_4[6]): (320, 120), (4, DISPLAY_MAP_4[7]): (1400, 116),
    (4, DISPLAY_MAP_4[8]): (312, 175), (4, DISPLAY_MAP_4[9]): (1412, 170),
    (4, DISPLAY_MAP_4[10]): (302, 230), (4, DISPLAY_MAP_4[11]): (1444, 224),
    (4, DISPLAY_MAP_4[12]): (305, 687), (4, DISPLAY_MAP_4[13]): (1420, 676),
    (4, DISPLAY_MAP_4[14]): (310, 814), (4, DISPLAY_MAP_4[15]): (1410, 804),
    (4, DISPLAY_MAP_4[16]): (320, 926), (4, DISPLAY_MAP_4[17]): (1400, 920),
    # Slot 8
    (8, 8): (200, 320), (8, 9): (60, 380), (8, 10): (90, 522), (8, 11): (36, 580),
    (8, 12): (90, 640), (8, 13): (36, 700), (8, 14): (90, 760), (8, 15): (36, 820),
    (8, 16): (1510, 320), (8, 17): (1660, 380), (8, 18): (1622, 520), (8, 19): (1688, 580),
    (8, 20): (1622, 640), (8, 21): (1688, 700), (8, 22): (1622, 760), (8, 23): (1688, 820),
}

INSERT_QUERY = """
    INSERT IGNORE INTO HV_DATA (datetime, slot, channel, power, poweron, powerdown, vmon, imon, v0set, i0set)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# ==============================================================================
# 데이터베이스 초기화 및 연결 풀 (Database Initialization)
# ==============================================================================

def initialize_database_pool(db_config) -> Optional[Any]:
    if mariadb is None:
        return None
    try:
        pool = mariadb.ConnectionPool(
            user=db_config["User"],
            password=db_config["Password"],
            host=db_config["Host"],
            port=db_config["Port"],
            database=db_config["Database"],
            pool_name=db_config["PoolName"],
            unix_socket=db_config.get("UnixSocket"),
            pool_size=db_config["PoolSize"]
        )
        logging.info(f"MariaDB Connection Pool '{db_config['PoolName']}' initialized.")
        
        # 테이블 생성 확인
        conn = pool.get_connection()
        with conn.cursor() as cur:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS HV_DATA (
               datetime DATETIME, slot INT, channel INT, power INT, poweron INT, powerdown INT,
               vmon FLOAT, imon FLOAT, v0set FLOAT, i0set FLOAT,
               PRIMARY KEY (datetime, slot, channel)
            )
            """
            cur.execute(create_table_query)
            conn.commit()
        conn.close()
        return pool
    except Exception as e:
        logging.error(f"Error initializing MariaDB Pool: {e}")
        return None

# ==============================================================================
# 데이터 처리 워커 스레드 (DataWorker Thread)
# ==============================================================================

class DataWorker(QObject):
    """
    백그라운드 스레드에서 CAEN 장비 통신(I/O) 및 데이터베이스 작업을 수행합니다.
    """
    data_fetched = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, device: Any, db_pool: Optional[Any], config: Dict):
        super().__init__()
        self.device = device
        self.db_pool = db_pool
        self.polling_interval = config["Settings"]["PollingInterval_ms"]
        self.db_commit_interval = config["Settings"]["DBCommitInterval_ms"]
        
        # 워커 스레드 내부 타이머 (QObject를 상속받아 스레드 안전하게 동작)
        self.polling_timer = QTimer(self)
        self.db_timer = QTimer(self)
        
        self.polling_timer.timeout.connect(self.poll_data)
        self.db_timer.timeout.connect(self.commit_to_db)
        
        # DB 저장을 위한 데이터 캐시
        self.data_cache_for_db = []

    def start_worker(self):
        """스레드 시작 시 타이머를 활성화합니다."""
        logging.info("DataWorker started.")
        self.polling_timer.start(self.polling_interval)
        self.db_timer.start(self.db_commit_interval)

    def stop_worker(self):
        """스레드 종료 전 타이머를 중지하고 마지막 데이터를 커밋합니다."""
        logging.info("DataWorker stopping.")
        self.polling_timer.stop()
        self.db_timer.stop()
        self.commit_to_db() # 종료 전 마지막 커밋 시도

    def poll_data(self):
        """주기적으로 데이터를 수집하고 GUI로 전송합니다."""
        data = self._fetch_data_bulk_optimized()
        
        if data:
            # GUI 업데이트를 위해 최신 데이터 전송 (Signal 발생)
            self.data_fetched.emit(data)
            
            # DB 저장을 위해 캐시에 스냅샷 추가
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            self.data_cache_for_db.append((timestamp, data))

    def _fetch_data_bulk_optimized(self) -> Optional[Dict[int, Dict[int, Dict[str, Any]]]]:
        """
        [핵심 최적화] 슬롯 단위 일괄 읽기(Bulk Read)를 수행합니다.
        네트워크 통신 횟수를 주기당 672회에서 21회로 줄입니다.
        """
        collected_data = {}
        try:
            for slot, board_info in CRATE_MAP.items():
                channel_list = list(range(board_info['channels']))
                slot_data = {ch: {} for ch in channel_list}

                # 각 파라미터에 대해 슬롯의 모든 채널 값을 한 번에 요청
                for param in PARAMETERS_TO_FETCH:
                    # 최적화된 통신 발생 (슬롯당 1회)
                    values = self.device.get_ch_param(slot, channel_list, param)

                    # 결과를 채널별로 정리 및 타입 안정화
                    for ch, value in zip(channel_list, values):
                        if param in ['VMon', 'IMon', 'V0Set', 'I0Set']:
                             slot_data[ch][param] = float(value)
                        else:
                             slot_data[ch][param] = int(value)

                collected_data[slot] = slot_data
            return collected_data

        except Exception as e:
            # hv.Error 및 기타 통신 오류 처리
            logging.error(f"Error fetching CAEN data: {e}")
            self.error_occurred.emit(f"CAEN Communication Error: {e}")
            return None

    def commit_to_db(self):
        """
        [버그 수정 및 최적화] 주기적으로 캐시된 데이터를 DB에 일괄 삽입합니다.
        """
        if not self.db_pool or not self.data_cache_for_db:
            return

        logging.info(f"Committing {len(self.data_cache_for_db)} snapshots to the database.")
        data_to_insert = []
        
        # 캐시된 모든 스냅샷을 DB 삽입 형식으로 변환
        for timestamp, data_snapshot in self.data_cache_for_db:
            for slot, slot_data in data_snapshot.items():
                for channel, params in slot_data.items():
                    data_to_insert.append((
                        timestamp, slot, channel,
                        params.get('Pw'), params.get('POn'), params.get('PDwn'),
                        params.get('VMon'), params.get('IMon'),
                        params.get('V0Set'), params.get('I0Set')
                    ))

        conn = None
        try:
            conn = self.db_pool.get_connection()
            with conn.cursor() as cur:
                # [버그 수정] 루프 밖에서 단 한 번의 배치 삽입(executemany) 실행
                cur.executemany(INSERT_QUERY, data_to_insert)
                conn.commit() # [버그 수정] 단 한 번의 커밋 실행
            
            self.data_cache_for_db = [] # 커밋 성공 후 캐시 비우기
            logging.info("Database commit successful.")

        except Exception as e:
            logging.error(f"Database commit error: {e}")
            self.error_occurred.emit(f"Database Error: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                conn.close()

# ==============================================================================
# GUI 메인 윈도우 (HVMonitor)
# ==============================================================================

class HVMonitor(QMainWindow):
    def __init__(self, device: Any, db_pool: Optional[Any], config: Dict):
        super().__init__()
        self.setWindowTitle("RENE HV Monitor (Optimized)")
        self.device = device
        self.db_pool = db_pool
        self.config = config
        self.current_status = "OK" if device else "DISCONNECTED"

        self._init_ui()
        
        if self.device:
            self._setup_worker()
        else:
            self.handle_error("Initialization Failed: No CAEN device connected.")

    def _init_ui(self):
        """UI 컴포넌트를 초기화합니다."""
        # 화면 크기 설정 및 레이아웃 구성
        try:
            screen_geometry = QApplication.desktop().screenGeometry()
            self.resize(screen_geometry.width(), screen_geometry.height())
        except Exception:
            self.resize(1920, 1080) # Fallback resolution

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        widget = QWidget()
        grid_layout = QGridLayout()
        widget.setLayout(grid_layout)
        scroll_area.setWidget(widget)

        # 캔버스 설정
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setFixedSize(1920, 1080)
        grid_layout.addWidget(self.view, 0, 0)

        # 배경 이미지 로드
        bg_image = self.config["Settings"]["BackgroundImage"]
        if os.path.exists(bg_image):
             pixmap = QPixmap(bg_image)
             self.scene.addPixmap(pixmap)
        else:
            logging.warning(f"Background image '{bg_image}' not found.")

        self._setup_labels_and_shapes()
        self._setup_legend()
        self._setup_status_label()

    def _setup_labels_and_shapes(self):
        """채널 라벨과 도형을 캔버스에 배치합니다."""
        self.labels = {}
        self.shape_items = {}

        for (slot, channel), (x, y) in LABEL_POSITIONS.items():
            # 라벨 생성 및 설정
            label = QLabel("Loading...")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background-color: transparent; color: gray;")
            self.labels[(slot, channel)] = label

            label_item = QGraphicsProxyWidget()
            label_item.setWidget(label)
            label_item.setPos(x, y)

            # 도형 생성 (Slot 1은 타원, 그 외는 둥근 사각형)
            path = QPainterPath()
            if slot == 1 and channel in [0, 1]:
                path.addEllipse(QRectF(0, 0, 160, 80))
            else:
                path.addRoundedRect(QRectF(0, 0, 160, 50), 10, 10)
            
            shape_item = QGraphicsPathItem(path)
            shape_item.setPos(x, y)
            shape_item.setBrush(QBrush(QColor("lightgray"))) # 초기 색상
            self.shape_items[(slot, channel)] = shape_item

            # 캔버스에 추가 (도형 먼저, 텍스트 나중)
            self.scene.addItem(shape_item)
            self.scene.addItem(label_item)

    def _setup_legend(self):
        """범례를 설정합니다."""
        legend_label = QLabel()
        legend_label.setStyleSheet("background-color: rgba(0, 0, 0, 58); color: white; padding: 5px;")
        legend_label.setFixedSize(260, 230)

        # HTML 기반 범례 텍스트 (가독성 향상)
        legend_text = """
            <p style='font-size: 12pt; text-align: center;'><b>범례 (Legend)</b></p>
            <p style='font-size: 10pt; text-align: center;'><b>전압 Voltage (도형색)</b></p>
            <p style='font-size: 10pt;'><span style='color: green;'>●</span> |Vmon - V0Set| ≤ 10 V</p>
            <p style='font-size: 10pt;'><span style='color: yellow;'>●</span> 10 V &lt; ~ ≤ 30 V</p>
            <p style='font-size: 10pt;'><span style='color: magenta;'>●</span> 30 V &lt; ~ ≤ 50 V</p>
            <p style='font-size: 10pt;'><span style='color: red;'>●</span> 50 V &lt;</p>
            <p style='font-size: 10pt; text-align: center;'><b>전류 Current (글자색)</b></p>
            <p style='font-size: 10pt;'><span style='color: black;'>■</span> IMon ≥ 0 uA (Black Text)</p> 
            <p style='font-size: 10pt;'><span style='color: white;'>■</span> IMon &lt; 0 uA (White Text)</p> 
        """
        legend_label.setText(legend_text)

        legend_item = QGraphicsProxyWidget()
        legend_item.setWidget(legend_label)
        legend_item.setPos(1640, 150)
        self.scene.addItem(legend_item)

    def _setup_status_label(self):
        """현재 시각 및 상태 표시 라벨을 설정합니다."""
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedSize(260, 80)
        self.status_label.setFont(QFont("Noto Sans", 12))

        status_item = QGraphicsProxyWidget()
        status_item.setWidget(self.status_label)
        status_item.setPos(1640, 50)
        self.scene.addItem(status_item)

        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(500) # 0.5초마다 시간 갱신
        self.update_time() # 초기 상태 업데이트

    def update_time(self):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.status_label.setText(f"Monitoring Status\n{current_time}\n{self.current_status}")
        
        if self.current_status == "OK":
             self.status_label.setStyleSheet("background-color: black; color: white;")
        elif self.current_status == "DISCONNECTED":
             self.status_label.setStyleSheet("background-color: gray; color: white;")
        else:
             self.status_label.setStyleSheet("background-color: darkred; color: white;")

    def _setup_worker(self):
        """워커 스레드를 초기화하고 시작합니다."""
        self.thread = QThread()
        self.thread.setObjectName("DataWorkerThread") # 스레드 이름 지정
        self.worker = DataWorker(self.device, self.db_pool, self.config)
        
        # 워커를 별도 스레드로 이동
        self.worker.moveToThread(self.thread)
        
        # 시그널 연결 (워커 -> 메인 스레드)
        self.worker.data_fetched.connect(self.update_gui_from_data)
        self.worker.error_occurred.connect(self.handle_error)
        
        # 스레드 시작 시 워커의 타이머 활성화
        self.thread.started.connect(self.worker.start_worker)
        
        # 스레드 시작
        self.thread.start()

    def handle_error(self, message: str):
        """워커 스레드에서 발생한 오류를 처리합니다."""
        logging.error(f"Worker Error Received: {message}")
        self.current_status = f"ERROR: {message[:20]}..." # 상태 라벨에 표시
        self.update_time()


    def update_gui_from_data(self, data: Dict[int, Dict[int, Dict[str, Any]]]):
        """
        워커로부터 데이터를 받아 GUI를 갱신합니다. (메인 스레드에서 실행)
        """
        # 에러 상태였다가 데이터가 정상 수신되면 상태 복구
        if self.current_status != "OK":
            self.current_status = "OK"
            self.update_time()

        try:
            for slot, slot_data in data.items():
                for channel, params in slot_data.items():
                    if (slot, channel) in self.labels:
                        self._update_single_channel_ui(slot, channel, params)
        except Exception as e:
            logging.error(f"Error updating GUI: {e}")

    def _update_single_channel_ui(self, slot: int, channel: int, params: Dict[str, Any]):
        """단일 채널의 UI 요소를 업데이트합니다."""
        label = self.labels[(slot, channel)]
        shape_item = self.shape_items[(slot, channel)]

        power = params.get('Pw')
        vmon = params.get('VMon')
        imon = params.get('IMon')
        v0set = params.get('V0Set')

        font_size = 12
        font_style = "Noto Sans"

        if power == 0:
            text = f"""<p style='font-size:{font_size}pt;line-height: 0.8; margin: 0px; text-align: center;'>Slot{slot}, Ch{channel}</p>
<p style='font-size:{font_size}pt;line-height: 0.8; margin: 0px; text-align: center;'>Power Off</p>"""
            color_name = "gray"
            text_color = "white"
        else:
            text = f"""<p style="line-height: 0.8; margin: 0px; font-size:{font_size}pt;">Slot{slot}, Ch{channel}</p>
<p style="line-height: 0.8; margin: 0px;"><b><span style="font-size:12pt;">{vmon:.1f} V, {imon:.2f} uA</span></b></p>"""
            color_name = self.vmon_to_color(vmon, v0set)
            text_color = "black" if imon >= 0 else "white"

        # 텍스트 및 스타일 업데이트
        label.setText(text)
        label.setStyleSheet(f"background-color: transparent; color: {text_color};")
        label.setFont(QFont(font_style, font_size))

        # 도형 색상 및 투명도 업데이트
        alpha = 178  # 약 70% 불투명도
        color = QColor(color_name)
        color.setAlpha(alpha)
        shape_item.setBrush(QBrush(color, Qt.SolidPattern))

    def vmon_to_color(self, vmon: float, v0set: float) -> str:
        """Vmon과 V0Set 차이에 따라 색상을 결정합니다."""
        diff = abs(vmon - v0set)
        if diff <= 10: return "green"
        elif diff <= 30: return "yellow"
        elif diff <= 50: return "magenta"
        else: return "red"

    def closeEvent(self, event):
        """프로그램 종료 시 리소스를 안전하게 해제합니다."""
        logging.info("Shutting down application...")
        
        # 워커 스레드 종료 요청 및 대기
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop_worker()

        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(5000): # 최대 5초 대기
                logging.warning("Worker thread did not shut down gracefully. Terminating.")
                self.thread.terminate()

        # CAEN 디바이스 연결 해제
        if self.device:
            try:
                self.device.close()
                logging.info("CAEN device closed.")
            except Exception as e:
                logging.error(f"Error closing CAEN device: {e}")

        super().closeEvent(event)

# ==============================================================================
# 프로그램 실행 (Application Entry Point)
# ==============================================================================

def main():
    app = QApplication(sys.argv)

    # 1. 데이터베이스 연결 풀 초기화
    db_pool = initialize_database_pool(CONFIG["MariaDB"])

    # 2. CAEN HV 장비 연결
    device = None
    if hv:
        try:
            hv_config = CONFIG["CAEN_HV"]
            system_type = getattr(hv.SystemType, hv_config["SystemType"])
            link_type = getattr(hv.LinkType, hv_config["LinkType"])
            
            logging.info(f"Connecting to CAEN HV system at {hv_config['IPAddress']}...")
            device = hv.Device.open(
                system_type, link_type, hv_config["IPAddress"], 
                hv_config["Username"], hv_config["Password"]
            )
            logging.info("Successfully connected to CAEN HV system.")
        except Exception as e:
            logging.error(f"Failed to connect to CAEN HV system: {e}")
            # 장비 연결 실패 시에도 GUI는 실행되나, 데이터 수집은 동작하지 않음.

    # 3. 메인 윈도우 실행
    window = HVMonitor(device, db_pool, CONFIG)
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
