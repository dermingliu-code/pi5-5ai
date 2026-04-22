# 檔案名稱: tft_inmp441_fft.py
import sys
import time
import queue
import numpy as np
import sounddevice as sd
import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# ==========================================
# ⚙️ 1. 硬體腳位與螢幕初始化
# ==========================================
SPI_PORT = busio.SPI(clock=board.SCK, MOSI=board.MOSI)
CS_PIN = digitalio.DigitalInOut(board.D5)
DC_PIN = digitalio.DigitalInOut(board.D24)
RST_PIN = digitalio.DigitalInOut(board.D25)
BLK_PIN = digitalio.DigitalInOut(board.D12)
BLK_PIN.direction = digitalio.Direction.OUTPUT
BLK_PIN.value = True

SCREEN_W, SCREEN_H = 320, 240
disp = st7789.ST7789(
    SPI_PORT, cs=CS_PIN, dc=DC_PIN, rst=RST_PIN,
    width=240, height=320, baudrate=64000000,
    x_offset=0, y_offset=0
)

# 【精算字型大小】：確保不會出框
try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    font_freq  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except IOError:
    font_title = font_freq = font_label = ImageFont.load_default()

# ==========================================
# 🎤 2. 音訊與 FFT 參數設定
# ==========================================
SAMPLE_RATE = 44100
CHUNK_SIZE = 2048
NUM_BARS = 64

audio_queue = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    if status: pass
    # 雙聲道讀取，取左聲道 (L/R 接地)
    raw_left = indata[:, 0].astype(np.float32)
    audio_queue.put(raw_left / 2147483648.0)

# ==========================================
# 📊 3. 專業級 UI 渲染模組
# ==========================================
def get_bar_color(index, total):
    """根據頻段給予動態漸層色 (低頻藍綠 -> 中頻黃 -> 高頻紅)"""
    if index < total * 0.25: return (0, 200, 255)    # Cyan
    elif index < total * 0.5: return (0, 255, 100)   # Green
    elif index < total * 0.75: return (255, 200, 0)  # Yellow
    else: return (255, 60, 60)                       # Red

def draw_dashboard(fft_binned, top_3_freqs):
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15)) # 極深藍黑背景
    draw = ImageDraw.Draw(img)

    # --- A. 頂部狀態列 (高度 24px) ---
    draw.rectangle((0, 0, SCREEN_W, 24), fill=(0, 90, 180))
    draw.text((10, 4), "INMP441 AUDIO SPECTRUM", font=font_title, fill=(255, 255, 255))

    # --- B. 示波器網格 (Grid) ---
    base_y = 170
    max_height = 140
    # 畫 3 條微弱的水平參考線
    for y_line in [base_y - 100, base_y - 60, base_y - 20]:
        draw.line((0, y_line, SCREEN_W, y_line), fill=(30, 40, 50), width=1)

    # --- C. 動態頻譜長條圖 (完美匹配 320px) ---
    # 64 根柱子 * (寬度 4 + 間距 1) = 恰好 320px
    bar_w = 4
    for i in range(NUM_BARS):
        h = min(int(fft_binned[i] * max_height), max_height)
        x1 = i * 5
        y1 = base_y - h
        x2 = x1 + bar_w
        y2 = base_y
        color = get_bar_color(i, NUM_BARS)
        draw.rectangle([x1, y1, x2, y2], fill=color)

    # --- D. 底部專業資訊區 (高度 175 ~ 240) ---
    draw.line((5, 175, SCREEN_W - 5, 175), fill=(70, 70, 90), width=2)
    draw.text((8, 180), "DOMINANT FREQUENCIES:", font=font_label, fill=(180, 180, 200))
    
    # 精算 3 等分的膠囊寬度 (320 / 3 = 106px)
    block_w = SCREEN_W // 3
    colors = [(255, 80, 80), (80, 255, 80), (80, 200, 255)] # Top1紅, Top2綠, Top3藍
    
    for idx in range(3):
        if idx < len(top_3_freqs):
            x_start = idx * block_w
            
            # 畫出帶有科技感的圓角底框
            draw.rounded_rectangle(
                [x_start + 6, 198, x_start + block_w - 4, 230], 
                radius=4, outline=(50, 50, 70), fill=(20, 20, 30)
            )
            
            # 文字排版：確保萬位數也能置中 (x_start + 12 留白)
            freq_val = int(top_3_freqs[idx])
            text = f"{freq_val} Hz"
            draw.text((x_start + 14, 206), text, font=font_freq, fill=colors[idx])

    # 負片反轉與 BGR 校正 (核心神技)
    img_array = 255 - np.array(img)[:, :, ::-1]
    disp.image(Image.fromarray(img_array), rotation=270)

# ==========================================
# 🚀 4. 主程式迴圈
# ==========================================
def main():
    print("\n啟動 INMP441 即時頻譜分析儀 (專業活潑版)...")
    freqs = np.fft.rfftfreq(CHUNK_SIZE, 1 / SAMPLE_RATE)
    
    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=2, dtype='int32',
            blocksize=CHUNK_SIZE, callback=audio_callback
        )
        stream.start()
        print("音訊串流已成功建立！")
        print("="*65)
    except Exception as e:
        print(f"❌ 錯誤：無法啟動麥克風 ({e})。請檢查 ALSA 驅動設定。")
        sys.exit(1)

    try:
        while True:
            try:
                audio_data = audio_queue.get_nowait()
            except queue.Empty:
                time.sleep(0.01)
                continue

            # --- 音量與 FFT 運算 ---
            audio_data = audio_data - np.mean(audio_data) # 去除直流偏移
            rms = np.sqrt(np.mean(audio_data**2))
            
            windowed_data = audio_data * np.hanning(CHUNK_SIZE)
            fft_mags = np.abs(np.fft.rfft(windowed_data))
            fft_mags[:5] = 0 # 忽略超低頻底噪
            
            valid_mags = fft_mags[:len(fft_mags)//2] 
            binned_mags = np.array_split(valid_mags, NUM_BARS)
            fft_binned = [np.max(bin_arr) * 10 for bin_arr in binned_mags] 
            
            top_indices = np.argsort(fft_mags)[-3:][::-1]
            top_3_freqs = freqs[top_indices]

            # ================================================
            # 🖥️ 【終端機】綜合資料儀表板
            # ================================================
            vol_bar_len = int(min(rms * 1000, 30)) # 縮短音量條給頻率留空間
            bar_str = "█" * vol_bar_len + "-" * (30 - vol_bar_len)
            
            # 格式化 Top 3 頻率字串
            freq_str = " | ".join([f"#{i+1}: {int(f):>5}Hz" for i, f in enumerate(top_3_freqs)])
            
            # \r 歸位，列印滿載資訊，並在尾端補空格清空舊字元
            print(f"\r🎤 音量 [{bar_str}] RMS:{rms:.4f} ║ {freq_str}    ", end="", flush=True)

            # --- 推播至 TFT ---
            draw_dashboard(fft_binned, top_3_freqs)

    except KeyboardInterrupt:
        print("\n\n🛑 收到中斷訊號，關閉音訊串流...")
    finally:
        stream.stop()
        stream.close()
        
        img_black = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        disp.image(Image.fromarray(255 - np.array(img_black)[:, :, ::-1]), rotation=270)
        BLK_PIN.value = False
        print("系統已成功關閉。")

if __name__ == "__main__":
    main()
