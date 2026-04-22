import time
import sys
import os
import subprocess
import board
import busio
import digitalio
import psutil
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# ==========================================
# 1. 硬體腳位定義 (與接線相符)
# ==========================================
SPI_PORT = busio.SPI(clock=board.SCK, MOSI=board.MOSI)

CS_PIN = digitalio.DigitalInOut(board.D5) # 避開系統 GPIO 8 佔用
DC_PIN = digitalio.DigitalInOut(board.D24)
RST_PIN = digitalio.DigitalInOut(board.D25)

BLK_PIN = digitalio.DigitalInOut(board.D12)
BLK_PIN.direction = digitalio.Direction.OUTPUT
BLK_PIN.value = True

# ==========================================
# 2. 初始化螢幕與尺寸設定
# ==========================================
BAUDRATE = 24000000
display = st7789.ST7789(
    SPI_PORT,
    cs=CS_PIN,
    dc=DC_PIN,
    rst=RST_PIN,
    width=240, 
    height=320, 
    baudrate=BAUDRATE,
    x_offset=0,
    y_offset=0
)

WIDTH = 320
HEIGHT = 240

# ==========================================
# 3. 系統資訊讀取函式 (讀取 RPi 5 真實狀態)
# ==========================================
def get_ip_address():
    """取得本機 IP 位址"""
    try:
        ip = subprocess.check_output(['hostname', '-I']).decode('utf-8').split()[0]
        return ip
    except Exception:
        return "DISCONNECTED"

def get_cpu_temp():
    """讀取樹莓派核心溫度"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except Exception:
        return 0.0

# ==========================================
# 4. UI 設計與精確字型載入
# ==========================================
try:
    # 根據雙欄佈局調整字型大小
    font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font_title  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    font_env    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32) # 左欄大字
    font_sys    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16) # 右欄數值
    font_label  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except IOError:
    font_header = font_title = font_env = font_sys = font_label = ImageFont.load_default()

def draw_professional_dashboard(env_temp, env_hum):
    """繪製專業雙欄系統看版 (RGB 顏色設計，推播前會轉 BGR)"""
    # 讀取真實系統數據
    cpu_usage = psutil.cpu_percent(interval=None)
    cpu_temp = get_cpu_temp()
    ram = psutil.virtual_memory()
    ram_usage = ram.percent
    ip_addr = get_ip_address()

    # 建立暗黑科技背景
    image = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 15))
    draw = ImageDraw.Draw(image)

    # ----------------------------------------
    # 頂部狀態列 (高度 24)
    # ----------------------------------------
    draw.rectangle((0, 0, WIDTH, 24), fill=(0, 90, 180))
    draw.text((10, 4), "PI-5 CORE SYSTEM | ONLINE", font=font_header, fill=(255, 255, 255))
    
    # 畫出雙欄外框與中線
    # 左欄框 (環境數據)
    draw.rectangle((5, 30, 155, 235), outline=(50, 50, 80), width=2)
    # 右欄框 (系統資訊)
    draw.rectangle((165, 30, 315, 235), outline=(50, 50, 80), width=2)

    # ----------------------------------------
    # 左欄：環境感測 (Environment)
    # ----------------------------------------
    draw.text((15, 38), "ENVIRONMENT", font=font_title, fill=(150, 150, 150))
    draw.line((15, 55, 145, 55), fill=(50, 50, 80), width=1)
    
    # 溫度
    draw.text((15, 65), "TEMPERATURE", font=font_label, fill=(180, 180, 180))
    draw.text((15, 80), f"{env_temp:.1f} °C", font=font_env, fill=(255, 100, 50)) # 橘紅
    
    # 濕度
    draw.text((15, 145), "HUMIDITY", font=font_label, fill=(180, 180, 180))
    draw.text((15, 160), f"{env_hum:.1f} %", font=font_env, fill=(50, 200, 255)) # 冰藍

    # ----------------------------------------
    # 右欄：系統核心 (System Core)
    # ----------------------------------------
    draw.text((175, 38), "SYSTEM CORE", font=font_title, fill=(150, 150, 150))
    draw.line((175, 55, 305, 55), fill=(50, 50, 80), width=1)

    # CPU 狀態 (使用率與溫度)
    draw.text((175, 65), "CPU USAGE & TEMP", font=font_label, fill=(180, 180, 180))
    # 根據溫度改變顏色警示 (超過 65度變紅色)
    cpu_color = (255, 50, 50) if cpu_temp > 65.0 else (100, 255, 100)
    draw.text((175, 80), f"{cpu_usage}% | {cpu_temp:.1f}°C", font=font_sys, fill=cpu_color)

    # RAM 狀態
    draw.text((175, 120), "RAM USAGE", font=font_label, fill=(180, 180, 180))
    draw.text((175, 135), f"{ram_usage}% ({ram.used//1048576}MB)", font=font_sys, fill=(200, 200, 255))

    # 網路狀態
    draw.text((175, 175), "NETWORK IP", font=font_label, fill=(180, 180, 180))
    draw.text((175, 190), f"{ip_addr}", font=font_sys, fill=(255, 200, 50)) # 鵝黃色

    return image

# ==========================================
# 5. 主迴圈與安全退出機制
# ==========================================
def main():
    print("啟動 TFT 系統看版測試... (按下 Ctrl+C 結束程式並關閉螢幕)")
    # 首次呼叫 psutil CPU 計算，以利取得準確數值
    psutil.cpu_percent(interval=0.1) 
    
    # 環境模擬數據 (尚未接上 AHT10 時使用)
    mock_temp = 26.5
    mock_hum = 45.2

    try:
        while True:
            # 微調模擬環境數據，產生動態感
            mock_temp += 0.1 if mock_temp < 28.0 else -1.5
            mock_hum += 0.2 if mock_hum < 50.0 else -5.0

            # 繪製 UI
            img = draw_professional_dashboard(mock_temp, mock_hum)
            
            # 處理硬體的紅藍色彩反轉 (RGB 轉 BGR)
            r, g, b = img.split()
            img_bgr = Image.merge("RGB", (b, g, r))
            
            # 推播至螢幕 (旋轉 270 度為橫式正向)
            display.image(img_bgr, rotation=270)
            
            # 每秒更新一次系統狀態
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n收到中斷訊號，執行螢幕關閉程序...")
    finally:
        # 黑屏切斷背光
        black_image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        display.image(black_image, rotation=270)
        BLK_PIN.value = False
        print("螢幕已成功關閉。")
        sys.exit(0)

if __name__ == "__main__":
    main()
