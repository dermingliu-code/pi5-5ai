# 檔案名稱: tft_camera_43.py
import sys, time, cv2, board, busio, digitalio, numpy as np
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

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
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 50, 0))
    ImageDraw.Draw(img).text((20, 100), text, fill=(255, 255, 255))
    disp.image(Image.fromarray(255 - np.array(img)[:, :, ::-1]), rotation=270)

def main():
    draw_status("BOOTING 4:3 FULL...")
    try:
        picam2 = Picamera2()
        # 優化點：請求 4:3 解析度 (640x480) 填滿螢幕
        config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
        picam2.configure(config); picam2.start()
    except Exception as e:
        draw_status("INIT FAILED"); sys.exit(1)

    print("4:3 滿版模式啟動..."); start_time = time.time(); frames = 0
    try:
        while True:
            request = picam2.capture_request()
            raw = request.make_array("main"); request.release()
            if raw is None: continue

            # 1. 旋轉 180 度並直接縮放為 320x240
            frame = cv2.flip(raw, -1)
            frame_lcd = cv2.resize(frame, (SCREEN_W, SCREEN_H))

            # 2. 負片校正與 BGR 轉換
            disp.image(Image.fromarray(255 - frame_lcd[:, :, ::-1]), rotation=270)
            
            frames += 1
            if frames % 30 == 0:
                print(f"FPS: {30/(time.time()-start_time):.1f}"); start_time = time.time()
    except KeyboardInterrupt: pass
    finally: picam2.stop(); BLK_PIN.value = False

if __name__ == "__main__": main()
