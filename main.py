# 檔案名稱: main.py
import sys, time, os, queue, datetime, threading, math, subprocess
import cv2, numpy as np, psutil, requests
import sounddevice as sd
import board, busio, digitalio
from PIL import Image, ImageDraw, ImageFont, ImageOps
import adafruit_rgb_display.st7789 as st7789
from gpiozero import RotaryEncoder, Button, PWMOutputDevice

# --- Rich 函式庫 (高密度終端機排版) ---
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Console, Group
from rich.columns import Columns
from rich.align import Align
from rich import box

console = Console()

# ==========================================
# ⚙️ 1. 硬體全域設定與腳位定義
# ==========================================
SPI_PORT = busio.SPI(clock=board.SCK, MOSI=board.MOSI)
CS_PIN, DC_PIN, RST_PIN = digitalio.DigitalInOut(board.D5), digitalio.DigitalInOut(board.D24), digitalio.DigitalInOut(board.D25)
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
try: picam2_global = Picamera2()
except: picam2_global = None

i2c = board.I2C()
try:
    import adafruit_ahtx0
    sensor_aht = adafruit_ahtx0.AHTx0(i2c)
except: sensor_aht = None

# ==========================================
# 🔤 1.5 自動化科技字型部署引擎
# ==========================================
font_dir = "fonts"
if not os.path.exists(font_dir): os.makedirs(font_dir)

font_urls = {
    "ShareTechMono": "https://github.com/google/fonts/raw/main/ofl/sharetechmono/ShareTechMono-Regular.ttf",
    "RobotoMono-Bold": "https://github.com/google/fonts/raw/main/apache/robotomono/RobotoMono-Bold.ttf",
    "RobotoMono-Regular": "https://github.com/google/fonts/raw/main/apache/robotomono/RobotoMono-Regular.ttf"
}

font_paths = {}
for name, url in font_urls.items():
    path = os.path.join(font_dir, f"{name}.ttf")
    font_paths[name] = path
    if not os.path.exists(path):
        print(f"正在為您下載戰術字型: {name} ...")
        try:
            with open(path, "wb") as f: f.write(requests.get(url, timeout=10).content)
        except: pass

try:
    f_title = ImageFont.truetype(font_paths.get("ShareTechMono", ""), 18)
    f_item  = ImageFont.truetype(font_paths.get("RobotoMono-Bold", ""), 15)
    f_small = ImageFont.truetype(font_paths.get("RobotoMono-Regular", ""), 12)
    f_tiny  = ImageFont.truetype(font_paths.get("RobotoMono-Regular", ""), 10)
except Exception as e:
    print(f"⚠️ 使用系統預設字型 ({e})")
    try:
        f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        f_item  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        f_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        f_tiny  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        f_title = f_item = f_small = f_tiny = ImageFont.load_default()

# ==========================================
# 🧠 2. 狀態旗標與軍規終端機引擎
# ==========================================
app_exit_flag = False   
screen_on = True        
system_running = True   

sys_status = {
    "app": "BOOTING",
    "cpu": "0%", "ram": "0%", "disk": "0%", "temp": "0°C",
    "env_web": "Wait...", "env_loc": "Wait...",
    "cam": "[dim]Standby[/dim]",
    "audio_rms": 0.0, "audio_freq": "0Hz",
    "ai_target": "[dim]None[/dim]", "ai_conf": "0%"
}

log_cache = []
MAX_LOG_LINES = 6

def update_term_log(msg, level="INFO"):
    t_str = datetime.datetime.now().strftime("%H:%M:%S")
    color = "cyan" if level == "INFO" else "yellow" if level == "WARN" else "red"
    log_cache.append(f"[[dim]{t_str}[/dim]] [[bold {color}]{level:^4}[/bold {color}]] {msg}")
    if len(log_cache) > MAX_LOG_LINES:
        log_cache.pop(0)

def generate_dashboard():
    t_hw = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    t_hw.add_column("CORE HW", style="cyan")
    t_hw.add_column("VALUE", style="green", justify="right")
    t_hw.add_row("CPU Load", sys_status["cpu"])
    t_hw.add_row("CPU Temp", sys_status["temp"])
    t_hw.add_row("RAM Use", sys_status["ram"])
    t_hw.add_row("Disk Use", sys_status["disk"])
    t_hw.add_row("Cam ISP", sys_status["cam"])
    p_hw = Panel(t_hw, border_style="blue", padding=(0, 0))

    t_sens = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    t_sens.add_column("SENSORS & AI", style="cyan")
    t_sens.add_column("VALUE", style="yellow", justify="right")
    t_sens.add_row("Env (Loc)", sys_status["env_loc"])
    t_sens.add_row("Env (Web)", sys_status["env_web"])
    t_sens.add_row("Audio RMS", f"{sys_status['audio_rms']:.4f}")
    t_sens.add_row("Audio Freq", sys_status["audio_freq"])
    t_sens.add_row("AI Target", sys_status["ai_target"])
    t_sens.add_row("AI Conf.", sys_status["ai_conf"])
    p_sens = Panel(t_sens, border_style="blue", padding=(0, 0))

    log_text = "\n".join(log_cache) if log_cache else "Waiting for system events..."
    p_log = Panel(log_text, title="[bold]System Log[/bold]", title_align="left", border_style="dim", height=MAX_LOG_LINES+2)

    top_bar = f"[bold cyan]TACTICAL EDGE OS[/bold cyan] | APP: [bold yellow on red] {sys_status['app']} [/bold yellow on red]"
    
    content_group = Group(
        top_bar,
        "",
        Columns([p_hw, p_sens], expand=True),
        p_log
    )
    return Align.left(Panel(content_group, border_style="cyan"))

class TacticalDashboard:
    def __rich__(self): return generate_dashboard()

def system_monitor_daemon():
    while system_running:
        sys_status["cpu"] = f"{psutil.cpu_percent():.1f}%"
        sys_status["ram"] = f"{psutil.virtual_memory().percent:.1f}%"
        sys_status["disk"] = f"{psutil.disk_usage('/').percent:.1f}%"
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                sys_status["temp"] = f"{int(float(f.read()) / 1000.0)}°C"
        except: pass
        time.sleep(2)
threading.Thread(target=system_monitor_daemon, daemon=True).start()

def handle_ko_press():
    global app_exit_flag, screen_on
    app_exit_flag = True
    update_term_log("KO Button Pressed", "WARN")
    
btn_ko.when_pressed = handle_ko_press

# ==========================================
# 💡 3. LED 動態引擎與共用工具
# ==========================================
led_mode = "BREATHE"  

def led_daemon():
    global led_mode, system_running
    step = 0.0
    while system_running:
        try:
            if not screen_on:
                led_filament.value = 0; time.sleep(0.1); continue
                
            if led_mode == "BREATHE":
                led_filament.value = (math.sin(step) + 1) / 2 * 0.8 + 0.1
                step += 0.1; time.sleep(0.04)
            elif led_mode == "AUDIO":
                led_filament.value = min(1.0, sys_status["audio_rms"] * 8)
                time.sleep(0.02)
            elif led_mode == "SOLID":
                led_filament.value = 1.0; time.sleep(0.1)
            elif led_mode == "OFF":
                led_filament.value = 0; time.sleep(0.1)
        except: break

threading.Thread(target=led_daemon, daemon=True).start()

def push_to_screen(img_pil):
    arr = np.array(img_pil)
    if arr.shape[2] == 4: arr = arr[:, :, :3]
    disp.image(Image.fromarray(255 - arr[:, :, ::-1]), rotation=270)

def play_tone(freq, duration, vol=0.3):
    try:
        buzzer.frequency = freq; buzzer.value = vol
        time.sleep(duration); buzzer.value = 0
    except: pass

def draw_loading_screen(module_name):
    update_term_log(f"Loading {module_name}...")
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 15, 20))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, SCREEN_W, 18), fill=(20, 30, 40))
    draw.text((5, 2), f"TACTICAL-OS", font=f_tiny, fill=(0, 255, 255))
    draw.text((10, 100), f"INITIALIZING...", font=f_title, fill=(0, 255, 255))
    draw.text((10, 130), module_name, font=f_small, fill=(200, 200, 200))
    push_to_screen(img)

# ==========================================
# 🎨 4. 戰術 UI 與動畫
# ==========================================
def draw_top_bar(draw):
    draw.rectangle((0, 0, SCREEN_W, 18), fill=(20, 30, 40))
    t_str = datetime.datetime.now().strftime("%H:%M:%S")
    draw.text((5, 2), f"TACTICAL-OS", font=f_tiny, fill=(0, 255, 255))
    draw.text((130, 2), f"CPU:{sys_status['temp']}", font=f_tiny, fill=(255, 150, 0))
    draw.text((255, 2), f"[{t_str}]", font=f_tiny, fill=(200, 200, 200))
    draw.line((0, 18, SCREEN_W, 18), fill=(0, 150, 255), width=1)

def draw_grid_bg(draw):
    for i in range(0, SCREEN_W, 40): draw.line((i, 18, i, SCREEN_H), fill=(15, 15, 20))
    for i in range(18, SCREEN_H, 40): draw.line((0, i, SCREEN_W, i), fill=(15, 15, 20))

def animation_boot():
    update_term_log("Visual boot sequence started")
    screen_pwm.value = 1.0
    for h in range(1, SCREEN_H, 15):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, SCREEN_H//2 - h//2, SCREEN_W, SCREEN_H//2 + h//2), fill=(0, 50, 80))
        push_to_screen(img)
        if h < 50: play_tone(500 + h*20, 0.01, 0.1)
    
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 15, 20))
    draw = ImageDraw.Draw(img)
    draw_grid_bg(draw)
    draw.text((60, 100), "SYSTEM INITIATED", font=f_title, fill=(0, 255, 255))
    push_to_screen(img)
    play_tone(2500, 0.1); time.sleep(0.1); play_tone(3500, 0.2); time.sleep(0.5)

def animation_shutdown(last_img):
    global led_mode
    update_term_log("CRT shutdown sequence initiated", "WARN")
    led_mode = "OFF"
    play_tone(1500, 0.1); play_tone(800, 0.3)
    
    for scale in range(100, 0, -15):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        h = int(SCREEN_H * scale / 100)
        if h > 0:
            resized = last_img.resize((SCREEN_W, h), Image.Resampling.LANCZOS)
            img.paste(resized, (0, (SCREEN_H - h)//2))
        push_to_screen(img)
    
    for w in range(SCREEN_W, 0, -40):
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        ImageDraw.Draw(img).line((SCREEN_W//2 - w//2, SCREEN_H//2, SCREEN_W//2 + w//2, SCREEN_H//2), fill=(255, 255, 255), width=2)
        push_to_screen(img)
        
    push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
    time.sleep(0.1)
    screen_pwm.value = 0 

# ==========================================
# 🗂️ 5. 應用程式模組 (Apps)
# ==========================================
def app_system_info():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "SOLID"
    sys_status["app"] = "CORE INFO"
    
    def get_cmd(cmd):
        try: return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        except: return "ERR"

    while not app_exit_flag:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
        draw = ImageDraw.Draw(img)
        draw_grid_bg(draw); draw_top_bar(draw)

        cpu_u = psutil.cpu_percent()
        temp_raw = get_cmd("vcgencmd measure_temp")
        temp_str = temp_raw.replace("temp=", "") if "temp=" in temp_raw else "N/A"
        try: temp_val = float(temp_str.replace("'C", "").replace("C", ""))
        except: temp_val = 0.0

        freq_raw = get_cmd("vcgencmd measure_clock arm")
        try: freq_str = f"{int(freq_raw.split('=')[1]) / 1000000000:.2f} GHz"
        except: freq_str = "N/A"
        volts_raw = get_cmd("vcgencmd measure_volts core")
        volts_str = volts_raw.replace("volt=", "") if "volt=" in volts_raw else "N/A"

        throttle_raw = get_cmd("vcgencmd get_throttled")
        is_throttled = "0x0" not in throttle_raw
        fan_state = get_cmd("cat /sys/class/thermal/cooling_device0/cur_state")

        ram_mem = psutil.virtual_memory()
        ram_u = ram_mem.percent
        ram_tot = f"{ram_mem.total / (1024**3):.1f}G"
        disk_u = psutil.disk_usage('/').percent

        ip_addr = get_cmd("hostname -I | awk '{print $1}'")
        if not ip_addr or ip_addr == "ERR": ip_addr = "OFFLINE"
        uptime_str = get_cmd("uptime -p").replace("up ", "")
        
        eeprom_ver = get_cmd("rpi-eeprom-update | head -n 1 | awk '{print $3}'")
        usb_count = get_cmd("lsusb | wc -l")

        lx, rx, cw = 8, 164, 148 

        draw.rounded_rectangle((lx, 24, lx+cw, 125), radius=4, outline=(0, 150, 255), fill=(10, 20, 30))
        draw.text((lx+5, 28), "[ CPU & SOC PWR ]", font=f_tiny, fill=(0, 150, 255))
        draw.text((lx+5, 43), f"LOAD: {cpu_u}%", font=f_small, fill=(255, 255, 255))
        bar_w = cw - 10
        draw.rectangle((lx+5, 58, lx+5+bar_w, 61), outline=(50, 50, 50))
        draw.rectangle((lx+5, 58, lx+5+int(bar_w*(cpu_u/100)), 61), fill=(0, 255, 100))
        t_color = (255, 50, 50) if temp_val > 75 else (0, 255, 100)
        draw.text((lx+5, 68), f"TEMP: {temp_str}", font=f_small, fill=t_color)
        draw.text((lx+5, 86), f"FREQ: {freq_str}", font=f_small, fill=(200, 200, 200))
        draw.text((lx+5, 104), f"VOLT: {volts_str}", font=f_small, fill=(255, 150, 0))

        draw.rounded_rectangle((lx, 130, lx+cw, 230), radius=4, outline=(150, 100, 255), fill=(20, 10, 30))
        draw.text((lx+5, 134), "[ MEMORY & I/O ]", font=f_tiny, fill=(150, 100, 255))
        draw.text((lx+5, 150), f"RAM : {ram_u}%", font=f_small, fill=(255, 255, 255))
        draw.rectangle((lx+5, 165, lx+5+bar_w, 168), outline=(50, 50, 50))
        draw.rectangle((lx+5, 165, lx+5+int(bar_w*(ram_u/100)), 168), fill=(150, 100, 255))
        draw.text((lx+5, 175), f"DISK: {disk_u}%", font=f_small, fill=(255, 255, 255))
        draw.rectangle((lx+5, 190, lx+5+bar_w, 193), outline=(50, 50, 50))
        draw.rectangle((lx+5, 190, lx+5+int(bar_w*(disk_u/100)), 193), fill=(100, 200, 255))
        draw.text((lx+5, 205), f"PHYSICAL MEM: {ram_tot}", font=f_tiny, fill=(150, 150, 150))

        draw.rounded_rectangle((rx, 24, rx+cw, 125), radius=4, outline=(255, 150, 0), fill=(30, 20, 10))
        draw.text((rx+5, 28), "[ DIAGNOSTICS ]", font=f_tiny, fill=(255, 150, 0))
        thr_color = (255, 50, 50) if is_throttled else (0, 255, 100)
        thr_txt = "THROTTLED!" if is_throttled else "STABLE(0x0)"
        draw.text((rx+5, 45), f"PWR : {thr_txt}", font=f_tiny, fill=thr_color)
        fan_txt = f"LVL {fan_state}" if fan_state != "ERR" else "N/A"
        draw.text((rx+5, 62), f"FAN : {fan_txt}", font=f_tiny, fill=(200, 200, 200))
        draw.text((rx+5, 79), "OS  : Debian 12", font=f_tiny, fill=(200, 200, 200))
        up_str = uptime_str[:18] + "..." if len(uptime_str) > 18 else uptime_str
        draw.text((rx+5, 96), f"UP  : {up_str}", font=f_tiny, fill=(0, 255, 255))

        draw.rounded_rectangle((rx, 130, rx+cw, 230), radius=4, outline=(0, 255, 150), fill=(10, 30, 20))
        draw.text((rx+5, 134), "[ NET & COMMS ]", font=f_tiny, fill=(0, 255, 150))
        draw.text((rx+5, 150), "IP ADDRESS:", font=f_tiny, fill=(200, 200, 200))
        draw.text((rx+5, 163), ip_addr, font=f_small, fill=(0, 255, 150))
        usb_txt = usb_count if usb_count != "ERR" else "0"
        draw.text((rx+5, 185), f"USB DEVS: {usb_txt}", font=f_tiny, fill=(200, 200, 200))
        rom_str = eeprom_ver[:12] if eeprom_ver != "ERR" else "Unknown"
        draw.text((rx+5, 202), f"ROM: {rom_str}", font=f_tiny, fill=(150, 150, 150))

        push_to_screen(img)
        time.sleep(0.5) 

def app_environment():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "BREATHE"
    sys_status["app"] = "ENV RADAR"
    
    draw_loading_screen("Weather & Forecast API")
    update_term_log("Fetching Open-Meteo 5-Day API...")
    
    forecast_data = []
    web_t, web_h = "--", "--"
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=25.08&longitude=121.59&current_weather=true&hourly=relativehumidity_2m&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
        req = requests.get(url, timeout=4).json()
        web_t = req['current_weather']['temperature']
        web_h = req['hourly']['relativehumidity_2m'][0]
        
        daily = req['daily']
        for i in range(5):
            date_str = daily['time'][i] 
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            day_name = dt.strftime("%a").upper() 
            if i == 0: day_name = "TDA"
            
            w_code = daily['weathercode'][i]
            t_max = daily['temperature_2m_max'][i]
            t_min = daily['temperature_2m_min'][i]
            forecast_data.append({"day": day_name, "code": w_code, "max": t_max, "min": t_min})
            
        sys_status["env_web"] = f"{web_t}°C / {web_h}%"
        update_term_log("5-Day Forecast Synced")
    except Exception as e:
        sys_status["env_web"] = "[red]ERROR[/red]"
        update_term_log(f"API Fetch Failed: {e}", "WARN")

    def get_wx_style(code):
        if code <= 1: return "[SUN]", (255, 200, 0)      
        if code <= 3: return "[CLD]", (200, 200, 200)    
        if code <= 49: return "[FOG]", (150, 150, 150)   
        if code <= 69: return "[RAN]", (0, 150, 255)     
        if code <= 79: return "[SNW]", (255, 255, 255)   
        if code <= 99: return "[STM]", (255, 50, 255)    
        return "[UNK]", (100, 100, 100)

    while not app_exit_flag:
        loc_t = f"{sensor_aht.temperature:.1f}" if sensor_aht else "--"
        loc_h = f"{sensor_aht.relative_humidity:.1f}" if sensor_aht else "--"
        sys_status["env_loc"] = f"{loc_t}°C / {loc_h}%"
        
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
        draw = ImageDraw.Draw(img)
        draw_grid_bg(draw); draw_top_bar(draw)
        
        lx, rx, cw, hy = 8, 164, 148, 110
        
        draw.rounded_rectangle((lx, 24, lx+cw, hy), radius=4, outline=(0, 255, 100), fill=(10, 30, 10))
        draw.text((lx+5, 28), "[ LOCAL SENSOR ]", font=f_tiny, fill=(0, 255, 100))
        draw.text((lx+5, 48), f"{loc_t}°C", font=f_title, fill=(255, 255, 255))
        draw.text((lx+5, 80), f"RH: {loc_h}%", font=f_small, fill=(200, 255, 200))
        
        draw.rounded_rectangle((rx, 24, rx+cw, hy), radius=4, outline=(0, 150, 255), fill=(10, 10, 30))
        draw.text((rx+5, 28), "[ WEB: NEIHU ]", font=f_tiny, fill=(0, 150, 255))
        draw.text((rx+5, 48), f"{web_t}°C", font=f_title, fill=(255, 255, 255))
        draw.text((rx+5, 80), f"RH: {web_h}%", font=f_small, fill=(200, 200, 255))

        fy1, fy2 = 118, 230
        draw.rounded_rectangle((lx, fy1, rx+cw, fy2), radius=4, outline=(100, 100, 150), fill=(15, 15, 20))
        draw.text((lx+5, fy1+4), ">> 5-DAY TACTICAL FORECAST", font=f_tiny, fill=(150, 150, 255))
        
        if forecast_data:
            col_w = (rx + cw - lx) / 5
            for i, day_data in enumerate(forecast_data):
                cx = lx + int(i * col_w)
                if i > 0: draw.line((cx, fy1+20, cx, fy2-5), fill=(50, 50, 70), width=1)
                
                sym, c_color = get_wx_style(day_data['code'])
                
                draw.text((cx+12, fy1+22), day_data['day'], font=f_tiny, fill=(200, 200, 200))
                draw.text((cx+10, fy1+42), sym, font=f_small, fill=c_color)
                draw.text((cx+12, fy1+65), f"H:{int(day_data['max'])}", font=f_tiny, fill=(255, 100, 100))
                draw.text((cx+12, fy1+85), f"L:{int(day_data['min'])}", font=f_tiny, fill=(100, 200, 255))
        else:
            draw.text((lx+60, fy1+50), "FORECAST DATA UNAVAILABLE", font=f_small, fill=(255, 50, 50))

        push_to_screen(img)
        time.sleep(1) 

def app_camera():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "SOLID"
    sys_status["app"] = "LIVE CAMERA"
    
    if picam2_global is None: 
        update_term_log("Hardware ISP Not Available", "WARN")
        return
        
    draw_loading_screen("Hardware ISP")
    sys_status["cam"] = "[bold green]ACTIVE 🟢[/bold green]"
    update_term_log("Camera Pipeline Active")
    
    try:
        picam2_global.configure(picam2_global.create_video_configuration(main={"size": (640, 360), "format": "RGB888"}))
        picam2_global.start()
        
        while not app_exit_flag:
            req = picam2_global.capture_request()
            raw = req.make_array("main"); req.release()
            if raw is None: continue

            frame = cv2.flip(raw, -1)
            canvas = np.zeros((240, 320, 3), dtype=np.uint8)
            canvas[30:210, 0:320] = cv2.resize(frame, (320, 180))

            img = Image.fromarray(canvas)
            draw = ImageDraw.Draw(img)
            draw_top_bar(draw) 
            draw.line((10, 215, 310, 215), fill=(255, 0, 0), width=1)
            draw.text((10, 220), f"CAM: MODULE 3 (FOV 16:9)", font=f_tiny, fill=(255, 150, 50))
            push_to_screen(img)
            
    except Exception as e:
        update_term_log(f"Stream Error: {e}", "WARN")
    finally:
        picam2_global.stop()
        sys_status["cam"] = "[dim]Standby 🔴[/dim]"

# ==========================================
# 🎵 戰術三頻獨立鎖定 (Tri-Band Tactical Radar)
# ==========================================
def app_audio_fft():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "AUDIO" 
    sys_status["app"] = "AUDIO RADAR"
    
    CHUNK = 2048; RATE = 44100; BARS = 40 
    audio_queue = queue.Queue()
    freqs = np.fft.rfftfreq(CHUNK, 1 / RATE)

    def cb(indata, frames, time_info, status):
        audio_queue.put(indata[:, 0].astype(np.float32) / 2147483648.0)

    draw_loading_screen("Acoustic Radar")
    update_term_log("Initializing Tri-Band FFT Engine...")
    
    try:
        stream = sd.InputStream(samplerate=RATE, channels=2, dtype='int32', blocksize=CHUNK, callback=cb)
        stream.start()
        
        peak_holds = [0.0] * BARS
        last_log_time = 0
        
        while not app_exit_flag:
            try: data = audio_queue.get_nowait()
            except: time.sleep(0.01); continue
            
            data = data - np.mean(data)
            rms = np.sqrt(np.mean(data**2)) 
            sys_status["audio_rms"] = rms
            
            mags = np.abs(np.fft.rfft(data * np.hanning(CHUNK)))
            mags[:3] = 0 
            
            half_mags = mags[:len(mags)//2]
            bins = np.array_split(half_mags, BARS)
            
            idx_low_end = sum(len(b) for b in bins[:8])
            idx_mid_end = sum(len(b) for b in bins[:25])
            
            idx_low = np.argmax(half_mags[:idx_low_end])
            idx_mid = idx_low_end + np.argmax(half_mags[idx_low_end:idx_mid_end])
            idx_hi  = idx_mid_end + np.argmax(half_mags[idx_mid_end:])

            top_f_bands = [
                (freqs[idx_low], (0, 255, 255), "LOW"),  
                (freqs[idx_mid], (0, 255, 100), "MID"),  
                (freqs[idx_hi],  (255, 50, 200), "HI ")  
            ]
            
            binned = [np.max(b)*10 for b in bins]
            sys_status["audio_freq"] = f"{int(freqs[idx_mid])}Hz"
            
            if time.time() - last_log_time > 2.0:
                update_term_log(f"L:{int(freqs[idx_low])} M:{int(freqs[idx_mid])} H:{int(freqs[idx_hi])} | RMS:{rms:.3f}")
                last_log_time = time.time()
                
            img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
            draw = ImageDraw.Draw(img)
            draw_grid_bg(draw); draw_top_bar(draw)

            cx, cy = 160, 115
            base_r = 25 + min(rms * 120, 20) 
            
            draw.ellipse((cx-base_r, cy-base_r, cx+base_r, cy+base_r), outline=(0, 255, 255), width=2)
            draw.ellipse((cx-base_r+4, cy-base_r+4, cx+base_r-4, cy+base_r-4), outline=(0, 100, 200), width=1)
            draw.text((cx-12, cy-6), "FFT", font=f_small, fill=(0, 255, 255))

            for i in range(BARS):
                val = binned[i]
                if val > peak_holds[i]: peak_holds[i] = val
                else: peak_holds[i] = max(0, peak_holds[i] - 0.05) 

                mag_h = min(int(val * 100), 70)
                peak_h = min(int(peak_holds[i] * 100), 70)

                angle = (i / BARS) * math.pi - (math.pi / 2) 
                c_cos, c_sin = math.cos(angle), math.sin(angle)

                rx1, ry1 = cx + base_r * c_cos, cy + base_r * c_sin
                rx2, ry2 = cx + (base_r + mag_h) * c_cos, cy + (base_r + mag_h) * c_sin
                rpx, rpy = cx + (base_r + peak_h + 3) * c_cos, cy + (base_r + peak_h + 3) * c_sin

                c = (0, 255, 255) if i < 8 else (0, 255, 100) if i < 25 else (255, 50, 200)
                pc = (255, 255, 255) 

                draw.line((rx1, ry1, rx2, ry2), fill=c, width=2)
                draw.rectangle((rpx-1, rpy-1, rpx+1, rpy+1), fill=pc) 

                lx1, lx2, lpx = cx - (rx1 - cx), cx - (rx2 - cx), cx - (rpx - cx)
                draw.line((lx1, ry1, lx2, ry2), fill=c, width=2)
                draw.rectangle((lpx-1, rpy-1, lpx+1, rpy+1), fill=pc)

            # ------------------------------------------
            # 🎯 戰術三頻獨立鎖定框 (三等分對稱滿版佈局)
            # ------------------------------------------
            draw.line((5, 193, 315, 193), fill=(0, 100, 200), width=1)
            for idx, (freq_val, color, label) in enumerate(top_f_bands):
                # 3等分佈局: 起點 5, 110, 215 (每格寬度 100px，間距 5px)
                x = 5 + idx * 105
                draw.rectangle((x, 198, x+100, 236), outline=color, fill=(10, 20, 30))
                
                # 標籤與數值上下分層，完美解決 5 位數頻率超出框線問題
                draw.text((x+5, 201), f"[{label}]", font=f_tiny, fill=color)
                # 加入千位符號，大幅提升視覺專業度
                draw.text((x+5, 216), f"{int(freq_val):,} Hz", font=f_item, fill=(255, 255, 255))

            push_to_screen(img)
            
    except Exception as e:
        update_term_log(f"I2S Error: {e}", "WARN")
    finally:
        try: 
            stream.stop(); stream.close()
            sys_status["audio_rms"] = 0.0
            sys_status["audio_freq"] = "0Hz"
        except: pass

def app_person_sentry():
    global app_exit_flag, led_mode
    app_exit_flag = False; led_mode = "OFF"
    sys_status["app"] = "PERSON SENTRY"
    
    if picam2_global is None: 
        update_term_log("Hardware ISP Not Available", "WARN")
        return
    
    model_dir = "models"
    prototxt = f"{model_dir}/MobileNetSSD_deploy.prototxt"
    caffemodel = f"{model_dir}/MobileNetSSD_deploy.caffemodel"
    
    if not os.path.exists(model_dir): os.makedirs(model_dir)
    if not os.path.exists(prototxt) or not os.path.exists(caffemodel):
        draw_loading_screen("Downloading AI")
        update_term_log("Downloading Caffe Model (~22MB)")
        try:
            url_p = "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.prototxt"
            url_c = "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.caffemodel"
            with open(prototxt, "wb") as f: f.write(requests.get(url_p, timeout=10).content)
            with open(caffemodel, "wb") as f: f.write(requests.get(url_c, timeout=30).content)
            update_term_log("Model Downloaded")
        except Exception as e:
            update_term_log("Download Failed", "WARN"); return

    draw_loading_screen("Neural Network")
    net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
    sys_status["cam"] = "[bold green]AI ACTIVE 🟢[/bold green]"
    
    MODE_X, MODE_Y, MODE_SIZE, MODE_ARMED = 0, 1, 2, 3
    current_mode = MODE_X
    zone_x, zone_y, zone_radius = SCREEN_W // 2, SCREEN_H // 2, 50
    last_enc = encoder.steps
    strobe_count = 0
    
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

    try:
        picam2_global.configure(picam2_global.create_video_configuration(main={"size": (640, 360), "format": "RGB888"}))
        picam2_global.start()
        update_term_log("Surveillance radar active")
        
        last_log_time = 0
        while not app_exit_flag:
            if btn_enter.is_pressed:
                current_mode = (current_mode + 1) % 4
                play_tone(1800, 0.1, 0.2); time.sleep(0.3)
                
            if encoder.steps != last_enc:
                diff = encoder.steps - last_enc
                last_enc = encoder.steps
                if current_mode == MODE_X: zone_x = max(0, min(SCREEN_W, zone_x + diff*10))
                elif current_mode == MODE_Y: zone_y = max(0, min(SCREEN_H, zone_y + diff*10))
                elif current_mode == MODE_SIZE: zone_radius = max(5, min(320, zone_radius + diff*5))

            req = picam2_global.capture_request()
            raw = req.make_array("main"); req.release()
            if raw is None: continue
            
            latest_frame = cv2.flip(raw, -1)
            canvas = np.zeros((240, 320, 3), dtype=np.uint8)
            canvas[30:210, 0:320] = cv2.resize(latest_frame, (320, 180))
            
            intruder_detected = False
            zx1, zy1 = max(0, zone_x-zone_radius), max(0, zone_y-zone_radius)
            zx2, zy2 = min(SCREEN_W, zone_x+zone_radius), min(SCREEN_H, zone_y+zone_radius)
            
            sys_status["ai_target"] = "[dim]None[/dim]"
            sys_status["ai_conf"] = "0%"

            for person in ai_boxes:
                x1, y1, x2, y2 = person["box"]
                px, py = (x1 + x2)//2, (y1 + y2)//2
                
                conf = int(person['score']*100)
                sys_status["ai_target"] = "[bold red]HUMAN[/bold red]"
                sys_status["ai_conf"] = f"[bold red]{conf}%[/bold red]"
                
                if (zx1 < px < zx2) and (zy1 < py < zy2):
                    intruder_detected = True; break

            is_armed = (current_mode == MODE_ARMED)
            
            if is_armed and intruder_detected:
                if time.time() - last_log_time > 2.0:
                    update_term_log(f"Intruder Lock! Confidence: {conf}%", "WARN")
                    last_log_time = time.time()
                strobe_count += 1
                led_mode = "SOLID" 
                play_tone(2000 + ((time.time()*30)%1)*1500, 0.05, 0.5)
            else:
                strobe_count = 0
                led_mode = "BREATHE" if is_armed else "OFF"

            img_pil = Image.fromarray(canvas)
            draw = ImageDraw.Draw(img_pil)

            if is_armed and intruder_detected and (strobe_count % 2 == 0):
                overlay = Image.new('RGB', (SCREEN_W, SCREEN_H), (150, 0, 0))
                img_pil = Image.blend(img_pil, overlay, 0.5)
                draw = ImageDraw.Draw(img_pil) 

            draw_top_bar(draw)

            for person in ai_boxes:
                x1, y1, x2, y2 = person["box"]
                draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=2)
                draw.text((x1+2, max(18, y1-15)), f"TARGET {conf}%", font=f_small, fill=(0, 255, 0))

            zone_color = (255, 0, 0) if is_armed else (0, 255, 255)
            mode_text = ["MOVE X", "MOVE Y", "ADJUST SIZE", "SYSTEM ARMED"][current_mode]
            draw.rectangle([zx1, zy1, zx2, zy2], outline=zone_color, width=2)
            draw.text((zx1+5, max(18, zy1+5)), f"ZONE [{mode_text}]", font=f_small, fill=zone_color)

            push_to_screen(img_pil)
            
    except Exception as e:
        update_term_log(f"Engine Crash: {e}", "WARN")
    finally:
        picam2_global.stop()
        sys_status["cam"] = "[dim]Standby[/dim]"
        sys_status["ai_target"] = "[dim]None[/dim]"
        sys_status["ai_conf"] = "0%"

# ==========================================
# 🎮 6. 戰術主選單與排程
# ==========================================
MENU_ITEMS = [
    ("[ SYS ] CORE INFO", app_system_info),
    ("[ ENV ] RADAR", app_environment),
    ("[ CAM ] LIVE VIEW", app_camera),
    ("[ FFT ] AUDIO ANLZ", app_audio_fft),
    ("[ AI  ] PERSON SENTRY", app_person_sentry),
    ("[ PWR ] SYSTEM HALT", "EXIT")
]

def draw_main_menu(selected_idx):
    sys_status["app"] = "MAIN MENU"
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (5, 5, 10))
    draw = ImageDraw.Draw(img)
    draw_grid_bg(draw); draw_top_bar(draw)
    
    start_y = 40
    for i, (name, _) in enumerate(MENU_ITEMS):
        y = start_y + i * 33
        if i == selected_idx:
            draw.rectangle((10, y, SCREEN_W-10, y+28), fill=(0, 50, 100))
            draw.text((15, y+4), f">> {name} <<", font=f_item, fill=(0, 255, 255))
            draw.line((10, y, 10, y+28), fill=(0, 255, 255), width=3) 
        else:
            draw.text((25, y+4), name, font=f_item, fill=(100, 150, 150))
            
    push_to_screen(img)
    return img

def main():
    global app_exit_flag, screen_on, led_mode, system_running
    
    os.system('cls' if os.name == 'nt' else 'clear')
    animation_boot()
    current_idx, last_encoder, last_img = 0, encoder.steps, None

    with Live(TacticalDashboard(), refresh_per_second=4, screen=False) as live:
        while system_running:
            if app_exit_flag:
                app_exit_flag = False
                screen_on = not screen_on
                if screen_on:
                    update_term_log("Screen Woke Up")
                    screen_pwm.value = 1.0; led_mode = "BREATHE"
                else:
                    update_term_log("Screen Entered Sleep Mode")
                    screen_pwm.value = 0.0; led_mode = "OFF"
                    push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
                time.sleep(0.3)
                
            if not screen_on: time.sleep(0.1); continue

            if encoder.steps != last_encoder:
                diff = encoder.steps - last_encoder
                last_encoder = encoder.steps
                current_idx = (current_idx + diff) % len(MENU_ITEMS)
                play_tone(1500, 0.01, 0.1)
                last_img = draw_main_menu(current_idx)

            if btn_enter.is_pressed:
                play_tone(3000, 0.05, 0.5)
                action = MENU_ITEMS[current_idx][1]
                if action == "EXIT":
                    if last_img is None: last_img = draw_main_menu(current_idx)
                    system_running = False 
                    animation_shutdown(last_img)
                    break
                else:
                    app_exit_flag = False 
                    action() 
                    led_mode = "BREATHE"; app_exit_flag = False 
                    play_tone(800, 0.1); time.sleep(0.2)
                    last_encoder = encoder.steps
                    last_img = draw_main_menu(current_idx)

            if sys_status["app"] == "MAIN MENU":
                last_img = draw_main_menu(current_idx)
            time.sleep(0.05) 

if __name__ == "__main__":
    try: 
        main()
    except KeyboardInterrupt:
        system_running = False
        console.print("\n[bold yellow]Keyboard Interrupt Detected.[/bold yellow]")
        try: animation_shutdown(Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 20)))
        except: 
            push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
            time.sleep(0.1)
            screen_pwm.value = 0; led_filament.value = 0
    except Exception as e:
        system_running = False
        console.print(f"\n[bold red]CRITICAL SYSTEM FAILURE: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        try:
            push_to_screen(Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0)))
            screen_pwm.value = 0; led_filament.value = 0
        except: pass
    finally: 
        system_running = False
        time.sleep(0.5)
        console.print("\n[bold red]SYSTEM OFFLINE.[/bold red] Tactical OS Shutdown Complete.")
        sys.exit(0)
