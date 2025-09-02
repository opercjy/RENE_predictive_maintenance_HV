import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# --- 설정 부분 ---
file_path = 'HV_DATA_250902_selected_with_slot.csv'
start_date_str = '2025-08-01'

CRATE_MAP = {
    1: {'model': 'A7030P', 'channels': 48},
    4: {'model': 'A7435SN', 'channels': 24},
    8: {'model': 'A7435SN', 'channels': 24},
}
# --- 설정 끝 ---

def plot_channels_by_slot(df: pd.DataFrame, plot_type: str, cr_map: dict):
    """
    각 슬롯별로 모든 채널의 Vmon 또는 Imon 시계열 데이터를 고해상도 파일로 저장합니다.
    """
    for slot, info in cr_map.items():
        channels_in_slot = info['channels']
        
        # << MODIFIED: 서브플롯 레이아웃 조정 (이 값을 변경하여 가로/세로 비율 조정)
        num_cols = 6 # 한 행에 표시할 서브플롯 수를 4개에서 6개로 늘려 더 넓게 표시

        num_rows = (channels_in_slot + num_cols - 1) // num_cols

        # << MODIFIED: Figure 크기를 대폭 증가시킴 (가로 30인치, 세로 동적 계산)
        fig, axes = plt.subplots(num_rows, num_cols, figsize=(num_cols * 5, num_rows * 4), 
                                 sharex=True, sharey=False) 
        
        if num_rows == 1 and num_cols > 1:
            axes = np.array([axes])
        elif num_rows == 1 and num_cols == 1:
            axes = np.array([[axes]])
        elif num_rows > 1 and num_cols == 1:
            axes = np.array([[ax] for ax in axes])
        
        axes = axes.flatten()

        fig.suptitle(f'Slot {slot} - All Channels {plot_type} Monitoring (From {start_date_str})', fontsize=24) # << MODIFIED: 제목 폰트 크기 증가

        for i, channel in enumerate(range(channels_in_slot)):
            ax = axes[i]
            channel_data = df[(df['slot'] == slot) & (df['channel'] == channel)]
            
            if not channel_data.empty:
                ax.plot(channel_data.index, channel_data[plot_type.lower()], label=f'Ch {channel} {plot_type}')
                ax.set_title(f'Ch {channel}', fontsize=12) # << MODIFIED: 서브플롯 제목 폰트 크기 증가
                ax.grid(True, linestyle=':', alpha=0.7)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                
                if plot_type == 'Vmon':
                    ax.set_ylabel('V (V)')
                else:
                    ax.set_ylabel('I (uA)')
            else:
                ax.set_title(f'Ch {channel} (No Data)')
                ax.text(0.5, 0.5, 'No Data', transform=ax.transAxes, 
                        horizontalalignment='center', verticalalignment='center', fontsize=12, color='gray')

        for j in range(i + 1, len(axes)):
            fig.delaxes(axes[j])
            
        fig.tight_layout(rect=[0, 0.03, 1, 0.96]) # << MODIFIED: 타이틀 공간 확보
        plt.gcf().autofmt_xdate()
        
        # << MODIFIED: `plt.show()` 대신 고해상도 파일로 바로 저장
        output_filename = f'slot_{slot}_all_channels_{plot_type.lower()}_high_res.png'
        plt.savefig(output_filename, dpi=200) # dpi (dots per inch)로 해상도 설정
        print(f" Slot {slot} {plot_type} 그래프가 '{output_filename}' 파일로 저장되었습니다.")
        plt.close(fig) # 메모리 해제를 위해 Figure 객체를 닫아줍니다.

# --- 메인 실행 로직 ---
try:
    print(f"'{file_path}' 파일을 불러오는 중입니다...")
    column_names = ['datetime', 'slot', 'channel', 'vmon', 'imon']
    df = pd.read_csv(
        file_path, 
        header=None, 
        names=column_names,
        parse_dates=['datetime']
    )
    print("파일 로딩 완료!")

    start_date = pd.to_datetime(start_date_str)
    df_filtered = df[df['datetime'] >= start_date].copy()
    df_filtered.set_index('datetime', inplace=True)
    df_filtered.sort_index(inplace=True)

    if df_filtered.empty:
        print(f"'{start_date_str}' 이후에 해당하는 데이터가 없습니다.")
    else:
        print(f"'{start_date_str}' 이후 총 {len(df_filtered)}개의 데이터 포인트를 찾았습니다.")
        
        print("\n--- Vmon 데이터 시각화 및 저장 시작 ---")
        plot_channels_by_slot(df_filtered, 'Vmon', CRATE_MAP)
        
        print("\n--- Imon 데이터 시각화 및 저장 시작 ---")
        plot_channels_by_slot(df_filtered, 'Imon', CRATE_MAP)
        
        print("\n 모든 그래프 파일 생성이 완료되었습니다.")

except FileNotFoundError:
    print(f"오류: '{file_path}' 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
except Exception as e:
    print(f"오류가 발생했습니다: {e}")
