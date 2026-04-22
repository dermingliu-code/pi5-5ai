import sys, time, os, queue, datetime, threading, math
import cv2, numpy as np, psutil, requests
import sounddevice as sd
import board, busio, digitalio
from PIL import Image, ImageDraw, ImageFont, ImageOps
import adafruit_rgb_display.st7789 as st7789
from gpiozero import RotaryEncoder, Button, PWMOutputDevice

# ==========================================
# ⚙️ 1. 硬體全域設定與腳位定義 (劉老師配置)
# ==========================================
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

sys.path.insert(0, '/usr/lib/python3/dist-packages')
from picamera2 import Picamera2

i2c = board.I2C()
try:
    import adafruit_ahtx0
    sensor_aht = adafruit_ahtx0.AHTx0(i2c)
except: sensor_aht = None

try:
    f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    f_item  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    f_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    f_tiny  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
except:
    f_title = f_item = f_small = f_tiny = ImageFont.load_default()

# ==========================================
# 🧠 2. 中斷事件與狀態旗標 (極致流暢的秘密)
# ==========================================
app_exit_flag = False   # 退出 App 的旗標
screen_on = True        # 螢幕開關狀態

def handle_ko_press():
    """KO鍵硬體中斷處理"""
    global app_exit_flag, screen_on
    # 如果正在 App 中，則發送退出訊號
    app_exit_flag = True
    
# 綁定硬體中斷，按鍵零延遲
btn_ko.when_pressed = handle_ko_press

# ==========================================
# 💡 3. LED 動態引擎與音效引擎
# ==========================================
led_mode = "BREATHE"  # BREATHE, SOLID, OFF, AUDIO
audio_rms_val = 0.0

def led_daemon():
    """獨立背景執行緒：控制 LED 燈絲的動態酷炫效果"""
    global led_mode, audio_rms_val
    step = 0.0
    while True:
        if not screen_on:
            led_filament.value = 0
            time.sleep(0.1)
            continue
            
        if led_mode == "BREATHE":
            # 完美的正弦波呼吸燈
            val = (math.sin(step) + 1) / 2 * 0.8 + 0.1
            led_filament.value = val
            step += 0.1
            time.sleep(0.04)
        elif led_mode == "AUDIO":
            # 音量跟隨爆閃
            val = min(1.0, audio_rms_val * 8)
            led_filament.value = val
            time.sleep(0.02)
        elif led_mode == "SOLID":
            led_filament.value = 1.0
            time.sleep(0.1)

# 啟動 LED 引擎
threading.Thread(target=led_daemon, daemon=True).start()

def push_to_screen(img_pil):
    arr = np.array(img_pil)
    if arr.shape[2] == 4: arr = arr[:, :, :3]
    disp.image(Image.fromarray(255 - arr[:, :, ::-1]), rotation=270)

def play_tone(freq, duration, vol=0.3):
    buzzer.frequency = freq; buzzer.value = vol
    time.sleep(duration); buzzer.value = 0

# ==========================================
# 🎨 4. 戰術 UI 渲染工具
# ==========================================
def draw_top_bar(draw):
    """繪製專業的系統狀態列"""
    draw.rectangle((0, 0, SCREEN_W, 18), fill=(20, 30, 40))
    t_str = datetime.datetime.now().strftime("%H:%M:%S")
    cpu_t = "0"
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_t = str(int(float(f.read()) / 1000.0))
    except: pass
    
    draw.text((5, 2), f"TACTICAL-OS", font=f_tiny, fill=(0, 255, 255))
    draw.text((130, 2), f"CPU:{cpu_t}C", font=f_tiny, fill=(255, 150, 0))
    draw.text((255, 2), f"[{t_str}]", font=f_tiny, fill=(200, 200, 200))
    draw.line((0, 18, SCREEN_W, 18), fill=(0, 150, 255), width=1)

def draw_grid_bg(draw):
    """繪製賽博龐克背景格線"""
    for i in range(0, SCREEN_W, 40): draw.line((i, 18, i, SCREEN_H), fill=(15, 15, 20))
    for i in range(18, SCREEN_H, 40): draw.line((0, i, SCREEN_W, i), fill=(15, 15, 20))

# ==========================================
# 🎬 5. 動畫 (開機/關機對稱呼應)
# ==========================================
def animation_boot():
    screen_pwm.value = 1.0
    # 橫向掃描展開
    for h in range(1, SCREEN_H, 15):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, SCREEN_H//2 - h//2, SCREEN_W, SCREEN_H//2 + h//2), fill=(0, 50, 80))
        push_to_screen(img)
        if h < 50: play_tone(500 + h*20, 0.01, 0.1)
    
    # 標題閃現
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 15, 20))
    draw = ImageDraw.Draw(img)
    draw_grid_bg(draw)
    draw.text((60, 100), "SYSTEM INITIATED", font=f_title, fill=(0, 255, 255))
    push_to_screen(img)
    play_tone(2500, 0.1); time.sleep(0.1); play_tone(3500, 0.2)
    time.sleep(0.5)

def animation_shutdown(last_img):
    """CRT 螢幕關閉動畫 (完美關閉背光)"""
    global led_mode
    led_mode = "OFF"
    play_tone(1500, 0.1); play_tone(800, 0.3)
    
    # 1. 垂直壓縮成一條線
    for scale in range(100, 0, -15):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        h = int(SCREEN_H * scale / 100)
        if h > 0:
            resized = last_img.resize((SCREEN_W, h), Image.Resampling.LANCZOS)
            img.paste(resized, (0, (SCREEN_H - h)//2))
        push_to_screen(img)
    
    # 2. 水平壓縮成一個點
    for w in range(SCREEN_W, 0, -40):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.line((SCREEN_W//2 - w//2, SCREEN_H//2, SCREEN_W//2 + w//2, SCREEN_H//2), fill=(255, 255, 255), width=2)
        push_to_screen(img)
        
    # 3. 徹底黑屏與斷電
    img_black = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    push_to_screen(img_black) # 送出最後一個黑幀洗掉 VRAM
    screen_pwm.value = 0      # 切斷背光 PWM
    led_filament.value = 0

# ==========================================
# 🗂️ 6. 應用程式模組 (Apps)
# ==========================================
def app_system_info():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "SOLID"
    
    while not app_exit_flag:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
        draw = ImageDraw.Draw(img)
        draw_grid_bg(draw); draw_top_bar(draw)
        
        draw.text((10, 30), ">> CORE TELEMETRY", font=f_title, fill=(0, 200, 255))
        
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        # 繪製精緻的資料長條圖
        metrics = [("CPU LOAD", cpu, (0, 255, 100)), ("MEM LOAD", ram, (0, 150, 255)), ("DISK USE", disk, (200, 200, 200))]
        y = 70
        for name, val, color in metrics:
            draw.text((15, y), f"{name}: {val}%", font=f_item, fill=(255, 255, 255))
            draw.rectangle((15, y+20, 300, y+28), outline=(50, 50, 50))
            draw.rectangle((17, y+22, 17 + int(280*(val/100)), y+26), fill=color)
            y += 45
            
        push_to_screen(img)
        time.sleep(0.5)

def app_environment():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "BREATHE"
    
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=25.08&longitude=121.59&current_weather=true&hourly=relativehumidity_2m"
        req = requests.get(url, timeout=2).json()
        web_t, web_h = req['current_weather']['temperature'], req['hourly']['relativehumidity_2m'][0]
    except: web_t, web_h = "--", "--"

    while not app_exit_flag:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 15, 10))
        draw = ImageDraw.Draw(img)
        draw_grid_bg(draw); draw_top_bar(draw)
        
        draw.text((10, 30), ">> ENV RADAR", font=f_title, fill=(0, 255, 100))
        
        loc_t = f"{sensor_aht.temperature:.1f}" if sensor_aht else "--"
        loc_h = f"{sensor_aht.relative_humidity:.1f}" if sensor_aht else "--"
        
        # 本地與雲端雙面板對比設計
        draw.rounded_rectangle((10, 60, 155, 150), radius=5, outline=(0, 255, 100), fill=(10, 30, 10))
        draw.text((20, 65), "[ AHT11 LOCAL ]", font=f_small, fill=(0, 255, 100))
        draw.text((20, 90), f"{loc_t}°C", font=f_title, fill=(255, 255, 255))
        draw.text((20, 120), f"{loc_h}% RH", font=f_item, fill=(200, 200, 200))
        
        draw.rounded_rectangle((165, 60, 310, 150), radius=5, outline=(0, 150, 255), fill=(10, 10, 30))
        draw.text((175, 65), "[ WEB: NEIHU ]", font=f_small, fill=(0, 150, 255))
        draw.text((175, 90), f"{web_t}°C", font=f_title, fill=(255, 255, 255))
        draw.text((175, 120), f"{web_h}% RH", font=f_item, fill=(200, 200, 200))

        push_to_screen(img)
        time.sleep(1)

def app_camera():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "SOLID"
    
    try:
        picam2 = Picamera2()
        config = picam2.create_video_configuration(main={"size": (640, 360), "format": "RGB888"})
        picam2.configure(config); picam2.start()
    except: return

    while not app_exit_flag:
        req = picam2.capture_request()
        raw = req.make_array("main"); req.release()
        if raw is None: continue

        frame = cv2.flip(raw, -1)
        canvas = np.zeros((240, 320, 3), dtype=np.uint8)
        canvas[30:210, 0:320] = cv2.resize(frame, (320, 180))

        img = Image.fromarray(canvas)
        draw = ImageDraw.Draw(img)
        draw_top_bar(draw) # 覆蓋頂部狀態列
        
        # 底部戰術標線與資料
        draw.line((10, 215, 310, 215), fill=(255, 0, 0), width=1)
        draw.text((10, 220), f"CAM: MODULE 3 (FOV 16:9)", font=f_tiny, fill=(255, 150, 50))
        
        push_to_screen(img)
        
    picam2.stop()

def app_audio_fft():
    global app_exit_flag, led_mode, audio_rms_val
    app_exit_flag = False; led_mode = "AUDIO" # 啟動音浪燈絲
    
    CHUNK = 2048; RATE = 44100; BARS = 64
    audio_queue = queue.Queue()
    freqs = np.fft.rfftfreq(CHUNK, 1 / RATE)

    def cb(indata, frames, time_info, status):
        audio_queue.put(indata[:, 0].astype(np.float32) / 2147483648.0)

    try:
        stream = sd.InputStream(samplerate=RATE, channels=2, dtype='int32', blocksize=CHUNK, callback=cb)
        stream.start()
    except: return

    while not app_exit_flag:
        try: data = audio_queue.get_nowait()
        except: time.sleep(0.01); continue
        
        data = data - np.mean(data)
        audio_rms_val = np.sqrt(np.mean(data**2)) # 傳遞給 LED 背景執行緒
        
        mags = np.abs(np.fft.rfft(data * np.hanning(CHUNK)))
        mags[:5] = 0
        binned = [np.max(b)*10 for b in np.array_split(mags[:len(mags)//2], BARS)]
        
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
        draw = ImageDraw.Draw(img)
        draw_grid_bg(draw); draw_top_bar(draw)

        base_y = 180
        for i in range(BARS):
            h = min(int(binned[i] * 120), 140)
            c = (0, 255, 255) if i < 20 else (0, 255, 100) if i < 45 else (255, 50, 50)
            draw.rectangle([i*5, base_y-h, i*5+4, base_y], fill=c)

        top_f = freqs[np.argsort(mags)[-3:][::-1]]
        for idx in range(3):
            if idx < len(top_f):
                x = idx * 106
                draw.rounded_rectangle((x+5, 200, x+101, 230), radius=3, outline=(50, 50, 50), fill=(20, 20, 25))
                draw.text((x+12, 206), f"{int(top_f[idx])}Hz", font=f_item, fill=(255, 255, 255))

        push_to_screen(img)
        
    stream.stop(); stream.close()

# ==========================================
# 🎮 7. 戰術主選單與排程
# ==========================================
MENU_ITEMS = [
    ("[ SYS ] CORE INFO", app_system_info),
    ("[ ENV ] RADAR", app_environment),
    ("[ CAM ] LIVE VIEW", app_camera),
    ("[ FFT ] AUDIO ANLZ", app_audio_fft),
    ("[ PWR ] SYSTEM HALT", "EXIT")
]

def draw_main_menu(selected_idx):
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
    draw = ImageDraw.Draw(img)
    draw_grid_bg(draw); draw_top_bar(draw)
    
    start_y = 40
    for i, (name, _) in enumerate(MENU_ITEMS):
        y = start_y + i * 38
        if i == selected_idx:
            # 專業的括號聚焦特效
            draw.rectangle((10, y, SCREEN_W-10, y+30), fill=(0, 50, 100))
            draw.text((15, y+5), f">> {name} <<", font=f_item, fill=(0, 255, 255))
            draw.line((10, y, 10, y+30), fill=(0, 255, 255), width=3) # 左側高光條
        else:
            draw.text((25, y+5), name, font=f_item, fill=(100, 150, 150))
            
    push_to_screen(img)
    return img

def main():
    global app_exit_flag, screen_on, led_mode
    animation_boot()
    
    current_idx = 0
    last_encoder = encoder.steps
    last_img = None

    while True:
        # 1. 主選單下的 KO 鍵行為 (螢幕開關)
        if app_exit_flag:
            app_exit_flag = False
            screen_on = not screen_on
            if screen_on:
                screen_pwm.value = 1.0; led_mode = "BREATHE"
            else:
                screen_pwm.value = 0.0; led_mode = "OFF"
                push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
            time.sleep(0.3)
            
        if not screen_on:
            time.sleep(0.1); continue

        # 2. 編碼器選單切換
        if encoder.steps != last_encoder:
            diff = encoder.steps - last_encoder
            last_encoder = encoder.steps
            current_idx = (current_idx + diff) % len(MENU_ITEMS)
            play_tone(1500, 0.01, 0.1)
            last_img = draw_main_menu(current_idx)

        # 3. 按下確定鍵
        if btn_enter.is_pressed:
            play_tone(3000, 0.05, 0.5)
            action = MENU_ITEMS[current_idx][1]
            
            if action == "EXIT":
                if last_img is None: last_img = draw_main_menu(current_idx)
                animation_shutdown(last_img)
                break
            else:
                # 進入 App，清除中斷旗標
                app_exit_flag = False 
                action() 
                
                # 從 App 退出後，重整狀態
                led_mode = "BREATHE"
                app_exit_flag = False # 清除離開 App 時按下的 KO 旗標
                play_tone(800, 0.1); time.sleep(0.2)
                last_encoder = encoder.steps
                last_img = draw_main_menu(current_idx)

        last_img = draw_main_menu(current_idx)
        time.sleep(0.05) # 提高更新頻率，讓頂部時鐘秒數平滑

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # 【完美退出處理】：按下 Ctrl+C 也能完整執行關機動畫並徹底黑屏
        print("\n收到中斷指令，執行安全關閉程序...")
        try:
            # 隨便抓一張最後畫面來執行壓縮動畫
            temp_img = Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 20))
            animation_shutdown(temp_img)
        except:
            screen_pwm.value = 0
            led_filament.value = 0
    finally:
        sys.exit(0)
