# 檔案名稱: person_sentry.py
import sys, time, os, threading
import cv2, numpy as np, requests
import board, busio, digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
from gpiozero import RotaryEncoder, Button, PWMOutputDevice

# 1. 硬體初始化
SPI_PORT = busio.SPI(clock=board.SCK, MOSI=board.MOSI)
CS_PIN = digitalio.DigitalInOut(board.D5)
DC_PIN = digitalio.DigitalInOut(board.D24)
RST_PIN = digitalio.DigitalInOut(board.D25)
SCREEN_W, SCREEN_H = 320, 240
disp = st7789.ST7789(SPI_PORT, cs=CS_PIN, dc=DC_PIN, rst=RST_PIN, width=240, height=320, baudrate=64000000)

encoder = RotaryEncoder(23, 6, wrap=False)
btn_enter = Button(17, pull_up=True, bounce_time=0.03) 
btn_ko = Button(22, pull_up=True, bounce_time=0.03)    

buzzer = PWMOutputDevice(26)       
led_filament = PWMOutputDevice(13) 
screen_pwm = PWMOutputDevice(12)
screen_pwm.value = 1.0 # 開啟背光

sys.path.insert(0, '/usr/lib/python3/dist-packages')
from picamera2 import Picamera2

try:
    f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    f_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except: f_title = f_small = ImageFont.load_default()

def push_to_screen(img_pil):
    """影像推播與 BGR 校正"""
    arr = np.array(img_pil)
    if arr.shape[2] == 4: arr = arr[:, :, :3]
    disp.image(Image.fromarray(255 - arr[:, :, ::-1]), rotation=270)

# ==========================================
# 🧠 中斷事件處理 (零延遲退出)
# ==========================================
app_exit_flag = False

def handle_exit():
    global app_exit_flag
    app_exit_flag = True

btn_ko.when_pressed = handle_exit # 綁定硬體中斷

# ==========================================
# 🚀 主程式
# ==========================================
def main():
    print("啟動獨立 AI 守衛雷達 (Camera Mod 3 軟體推論版)...")
    
    # AI 模型檢查與下載 (使用穩定的 djmv 鏡像)
    model_dir = "models"
    prototxt = f"{model_dir}/MobileNetSSD_deploy.prototxt"
    caffemodel = f"{model_dir}/MobileNetSSD_deploy.caffemodel"
    
    if not os.path.exists(model_dir): os.makedirs(model_dir)
    if not os.path.exists(prototxt) or not os.path.exists(caffemodel):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 50))
        draw = ImageDraw.Draw(img)
        draw.text((20, 100), "DOWNLOADING AI MODEL...", font=f_title, fill=(0, 255, 255))
        draw.text((20, 130), "Please wait (~22MB)", font=f_small, fill=(200, 200, 200))
        push_to_screen(img)
        
        print("正在下載 AI 模型 (只需下載一次，約 22MB)...")
        try:
            url_p = "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.prototxt"
            url_c = "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.caffemodel"
            with open(prototxt, "wb") as f: f.write(requests.get(url_p, timeout=10).content)
            with open(caffemodel, "wb") as f: f.write(requests.get(url_c, timeout=30).content)
            print("✅ 下載完成！")
        except Exception as e: 
            print("❌ 下載失敗:", e); return

    net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
    
    MODE_X, MODE_Y, MODE_SIZE, MODE_ARMED = 0, 1, 2, 3
    current_mode = MODE_X
    zone_x, zone_y, zone_radius = SCREEN_W // 2, SCREEN_H // 2, 50
    last_enc = encoder.steps
    strobe_count = 0
    
    # 異步 AI 推論引擎
    latest_frame = None
    ai_boxes = [] 
    
    def ai_worker():
        nonlocal latest_frame, ai_boxes
        while not app_exit_flag:
            if latest_frame is not None:
                blob = cv2.dnn.blobFromImage(cv2.resize(latest_frame, (300, 300)), 0.007843, (300, 300), (127.5, 127.5, 127.5), False)
                net.setInput(blob)
                detections = net.forward()
                boxes = []
                for i in range(detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    if confidence > 0.55 and int(detections[0, 0, i, 1]) == 15:
                        box = detections[0, 0, i, 3:7] * np.array([SCREEN_W, SCREEN_H, SCREEN_W, SCREEN_H])
                        x1, y1, x2, y2 = box.astype("int")
                        boxes.append({"box": (x1, y1, x2, y2), "score": confidence})
                ai_boxes = boxes
            time.sleep(0.02)
    threading.Thread(target=ai_worker, daemon=True).start()

    # 啟動相機
    try:
        picam2 = Picamera2()
        picam2.configure(picam2.create_video_configuration(main={"size": (640, 360), "format": "RGB888"}))
        picam2.start()
    except Exception as e: print("相機啟動失敗:", e); return

    # 主迴圈 (依賴 app_exit_flag)
    while not app_exit_flag:
        if btn_enter.is_pressed:
            current_mode = (current_mode + 1) % 4
            buzzer.value = 0.2; time.sleep(0.1); buzzer.value = 0
            time.sleep(0.3)
            
        if encoder.steps != last_enc:
            diff = encoder.steps - last_enc
            last_enc = encoder.steps
            if current_mode == MODE_X: zone_x = max(0, min(SCREEN_W, zone_x + diff*10))
            elif current_mode == MODE_Y: zone_y = max(0, min(SCREEN_H, zone_y + diff*10))
            elif current_mode == MODE_SIZE: zone_radius = max(5, min(320, zone_radius + diff*5))

        req = picam2.capture_request()
        raw = req.make_array("main"); req.release()
        if raw is None: continue
        
        latest_frame = cv2.flip(raw, -1)
        canvas = np.zeros((240, 320, 3), dtype=np.uint8)
        canvas[30:210, 0:320] = cv2.resize(latest_frame, (320, 180)) 
        
        intruder_detected = False
        zx1, zy1 = max(0, zone_x-zone_radius), max(0, zone_y-zone_radius)
        zx2, zy2 = min(SCREEN_W, zone_x+zone_radius), min(SCREEN_H, zone_y+zone_radius)

        for person in ai_boxes:
            x1, y1, x2, y2 = person["box"]
            px, py = (x1 + x2)//2, (y1 + y2)//2
            if (zx1 < px < zx2) and (zy1 < py < zy2):
                intruder_detected = True; break

        is_armed = (current_mode == MODE_ARMED)
        
        if is_armed and intruder_detected:
            strobe_count += 1
            led_filament.value = 1.0 if strobe_count % 2 == 0 else 0.0
            buzzer.frequency = 2000 + ((time.time()*30)%1)*1500; buzzer.value = 0.5
        else:
            strobe_count = 0
            led_filament.value = 0.5 if is_armed else 0.0
            buzzer.value = 0

        img_pil = Image.fromarray(canvas)
        draw = ImageDraw.Draw(img_pil)

        if is_armed and intruder_detected and (strobe_count % 2 == 0):
            overlay = Image.new('RGB', (SCREEN_W, SCREEN_H), (150, 0, 0))
            img_pil = Image.blend(img_pil, overlay, 0.5)
            draw = ImageDraw.Draw(img_pil) 

        draw.rectangle((0, 0, SCREEN_W, 18), fill=(20, 30, 40))
        draw.text((5, 2), "AI SENTRY STANDALONE", font=f_small, fill=(0, 255, 255))

        for person in ai_boxes:
            x1, y1, x2, y2 = person["box"]
            draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=2)
            draw.text((x1+2, max(18, y1-15)), f"HUMAN {int(person['score']*100)}%", font=f_small, fill=(0, 255, 0))

        zone_color = (255, 0, 0) if is_armed else (0, 255, 255)
        mode_text = ["MOVE X", "MOVE Y", "ADJUST SIZE", "SYSTEM ARMED"][current_mode]
        draw.rectangle([zx1, zy1, zx2, zy2], outline=zone_color, width=2)
        draw.text((zx1+5, max(18, zy1+5)), f"ZONE [{mode_text}]", font=f_small, fill=zone_color)

        push_to_screen(img_pil)
        
    # ==========================================
    # 🛑 安全退出與螢幕黑屏清洗
    # ==========================================
    print("\n收到退出指令，關閉相機與硬體資源...")
    picam2.stop()
    buzzer.value = 0
    led_filament.value = 0
    
    # 終極黑屏：送入一張全黑畫面清洗 VRAM
    push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
    time.sleep(0.1) # 給 SPI 傳輸留點時間
    screen_pwm.value = 0 # 徹底切斷背光

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        # 處理 Ctrl+C
        push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
        time.sleep(0.1)
        screen_pwm.value = 0; led_filament.value = 0; buzzer.value = 0
    finally: sys.exit(0)
