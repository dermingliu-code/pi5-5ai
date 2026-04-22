# 檔案名稱: tft_camera.py
import sys
import time
import cv2
import board
import busio
import digitalio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# ==========================================
# 🔑 關鍵引入：掛載系統級別的 Picamera2
# ==========================================
sys.path.insert(0, '/usr/lib/python3/dist-packages')
try:
    from picamera2 import Picamera2
except ImportError:
    print("❌ 錯誤：找不到 Picamera2 模組，請確認樹莓派系統是否已安裝。")
    sys.exit(1)

# ==========================================
# ⚙️ 硬體腳位與螢幕初始化
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

# ==========================================
# 🛠️ 螢幕狀態顯示工具
# ==========================================
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except IOError:
    font_large = ImageFont.load_default()

def draw_status(text, bg_color=(0, 0, 100)):
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), bg_color)
    draw = ImageDraw.Draw(img)
    draw.text((20, 100), text, font=font_large, fill=(255, 255, 255))
    
    # 【差異修正】：同步為狀態文字加入 RGB反轉 與 負片反轉 (255 - array)
    img_array = 255 - np.array(img)[:, :, ::-1]
    disp.image(Image.fromarray(img_array), rotation=270)

# ==========================================
# 🚀 主程式：Picamera2 記憶體直讀管線
# ==========================================
def main():
    print("啟動 TFT 終極效能相機管線 (色彩反轉修正版)...")
    draw_status("BOOTING AI CAMERA...")
    
    try:
        picam2 = Picamera2()
        config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
        picam2.configure(config)
        picam2.start()
    except Exception as e:
        print(f"相機初始化失敗: {e}")
        draw_status("CAMERA INIT FAILED", bg_color=(150, 0, 0))
        sys.exit(1)

    print("影像串流開始！")
    
    frames = 0
    start_time = time.time()

    try:
        while True:
            # 1. 核心極速擷取
            request = picam2.capture_request()
            raw_frame = request.make_array("main")
            request.release() 
            
            if raw_frame is None:
                continue

            # 2. 視角校正 (180度翻轉)
            frame = cv2.flip(raw_frame, -1)

            # 3. 縮放至螢幕尺寸
            frame_lcd = cv2.resize(frame, (SCREEN_W, SCREEN_H))

            # ==========================================================
            # 4. 【核心差異修正】：色彩空間轉換 與 負片校正 (SOFTWARE_INVERT)
            # ==========================================================
            # frame_lcd[:, :, ::-1] -> 執行 RGB 到 BGR 的對調
            # 255 - (...)           -> 執行硬體需要的負片反轉 (White -> Black 修正)
            # 這完美復刻了您在 alarm 腳本中的精準邏輯，並使用 Numpy 榨出極限效能！
            frame_corrected = 255 - frame_lcd[:, :, ::-1]

            # 5. 推播至螢幕
            img_pil = Image.fromarray(frame_corrected)
            disp.image(img_pil, rotation=270)
            
            # 幀率計算
            frames += 1
            if frames % 30 == 0:
                elapsed = time.time() - start_time
                print(f"目前效能: {30/elapsed:.1f} FPS")
                start_time = time.time()

    except KeyboardInterrupt:
        print("\n收到中斷訊號，執行安全關閉程序...")
    finally:
        picam2.stop()
        draw_status("SYSTEM HALTED", bg_color=(0, 0, 0))
        BLK_PIN.value = False
        print("系統已成功關閉。")

if __name__ == "__main__":
    main()
