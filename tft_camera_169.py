# 檔案名稱: tft_camera_169.py
import sys, time, cv2, board, busio, digitalio, numpy as np
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# 強制掛載系統級別的 Picamera2
sys.path.insert(0, '/usr/lib/python3/dist-packages')
from picamera2 import Picamera2

# 硬體設定
SPI_PORT = busio.SPI(clock=board.SCK, MOSI=board.MOSI)
CS_PIN, DC_PIN, RST_PIN = digitalio.DigitalInOut(board.D5), digitalio.DigitalInOut(board.D24), digitalio.DigitalInOut(board.D25)
BLK_PIN = digitalio.DigitalInOut(board.D12)
BLK_PIN.direction, BLK_PIN.value = digitalio.Direction.OUTPUT, True

SCREEN_W, SCREEN_H = 320, 240
disp = st7789.ST7789(SPI_PORT, cs=CS_PIN, dc=DC_PIN, rst=RST_PIN, width=240, height=320, baudrate=64000000)

def draw_status(text):
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 100))
    ImageDraw.Draw(img).text((20, 100), text, fill=(255, 255, 255))
    disp.image(Image.fromarray(255 - np.array(img)[:, :, ::-1]), rotation=270)

def main():
    draw_status("BOOTING 16:9 WIDE...")
    try:
        picam2 = Picamera2()
        # 優化點：請求 16:9 解析度 (640x360) 獲取最廣視野
        config = picam2.create_video_configuration(main={"size": (640, 360), "format": "RGB888"})
        picam2.configure(config); picam2.start()
    except Exception as e:
        draw_status("INIT FAILED"); sys.exit(1)

    print("16:9 廣角模式啟動..."); start_time = time.time(); frames = 0
    try:
        while True:
            request = picam2.capture_request()
            raw = request.make_array("main"); request.release()
            if raw is None: continue

            # 1. 旋轉 180 度並縮放為 320x180
            frame = cv2.flip(raw, -1)
            frame_resized = cv2.resize(frame, (320, 180))

            # 2. 電影黑邊化：將 320x180 置入 320x240 畫布中央
            canvas = np.zeros((240, 320, 3), dtype=np.uint8)
            canvas[30:210, 0:320] = frame_resized # 上下各留 30 像素黑邊

            # 3. 負片校正與 BGR 轉換 (255 - array)
            disp.image(Image.fromarray(255 - canvas[:, :, ::-1]), rotation=270)
            
            frames += 1
            if frames % 30 == 0:
                print(f"FPS: {30/(time.time()-start_time):.1f}"); start_time = time.time()
    except KeyboardInterrupt: pass
    finally: picam2.stop(); BLK_PIN.value = False

if __name__ == "__main__": main()
