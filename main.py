import time
import requests
import json
import random
import string
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from urllib.parse import quote
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
import os
import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==========================================
#                  配置区域
# ==========================================
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
except Exception as e:
    logging.error(f"无法读取配置文件 config.yaml: {e}")
    exit(1)

USERNAME = str(config['account']['username'])
PASSWORD = str(config['account']['password'])

SMTP_SERVER = str(config['email']['smtp_server'])
SMTP_PORT = int(config['email']['smtp_port'])
SENDER_EMAIL = str(config['email']['sender_email'])
SENDER_PASSWORD = str(config['email']['sender_password'])
RECEIVER_EMAIL = str(config['email']['receiver_email'])

# 阈值设定 (单位: 元)
ALERT_THRESHOLD = float(config['monitor']['alert_threshold'])

# 动态预测配置
MAX_INTERVAL_HOURS = float(config['monitor']['max_interval_hours'])  
MIN_INTERVAL_HOURS = float(config['monitor']['min_interval_hours'])  
SAFE_MARGIN = float(config['monitor']['safe_margin'])          
EMAIL_COOLDOWN = int(config['monitor']['email_cooldown']) 

# ==========================================

class SmartElecMonitor:
    def __init__(self):
        self.last_balance = None
        self.last_check_time = None
        self.last_alert_time = None
    
    def get_electricity_balance(self):
        """爬虫核心逻辑"""
        try:
            device_id = ''.join(random.choices(string.ascii_letters, k=24))
            client_id = uuid.uuid4().hex
            password_encoded = quote(PASSWORD)
            
            # 1. 登录
            login_url = f"https://mycas.hut.edu.cn/token/password/passwordLogin?username={USERNAME}&password={password_encoded}&appId=com.supwisdom.hut&geo&deviceId={device_id}&osType=android&clientId={client_id}&mfaState"
            login_response = requests.post(login_url, headers={'User-Agent': 'SWSuperApp/1.1.3', 'Accept': '*/*'}, timeout=15)
            login_response.raise_for_status()
            
            id_token = login_response.json()['data']['idToken']
            
            # 2. 获取openid
            openid_response = requests.get(
                'https://v8mobile.hut.edu.cn/zdRedirect/toSingleMenu',
                params={'code': 'openWater', 'token': id_token},
                headers={'X-Id-Token': id_token},
                allow_redirects=False, timeout=15
            )
            openid = openid_response.headers.get('Location').split('openid=')[1]
            jsessionid = openid_response.cookies.get('JSESSIONID')
            
            # 3. 房间信息
            history_response = requests.post(
                f'https://v8mobile.hut.edu.cn/myaccount/querywechatUserLastInfo?openid={openid}',
                json={"idserial": USERNAME, "openid": openid},
                headers={'Cookie': f'userToken={id_token}; JSESSIONID={jsessionid}', 'Accept': 'application/json'},
                timeout=15
            )
            bind_info = json.loads(history_response.json()['resultData']['elelastbind'])
            
            # 4. 电费详细
            room_response = requests.post(
                f'https://v8mobile.hut.edu.cn/channel/queryRoomDetail?openid={openid}',
                json={"areaid": bind_info.get('areaid'), "buildingid": bind_info.get('buildingid'), "factorycode": bind_info.get('factorycode'), "roomid": bind_info.get('roomid')},
                headers={'Cookie': f'userToken={id_token}; JSESSIONID={jsessionid}', 'Accept': 'application/json'},
                timeout=15
            )
            room_data = room_response.json().get('resultData', {})
            
            return {
                'room_name': room_data.get('accname', '未知房间'),
                'balance': float(room_data.get('eledetail', 0.0))
            }
        except Exception as e:
            logging.error(f"查询失败: {str(e)}")
            return None

    def send_alert_email(self, room_name, balance):
        """邮件发送逻辑"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = SENDER_EMAIL
            msg['To'] = RECEIVER_EMAIL
            msg['Subject'] = f"⚠️【电费告警】房间 [{room_name}] 余额已不足"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    background-color: #f6f9fc;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 500px;
                    margin: 40px auto;
                    background: #ffffff;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 10px 25px rgba(0,0,0,0.05);
                }}
                .header {{
                    background: linear-gradient(135deg, #ff4d4d, #ff7675);
                    padding: 25px 20px;
                    text-align: center;
                    color: #ffffff;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 22px;
                    font-weight: 600;
                    letter-spacing: 1px;
                }}
                .content {{
                    padding: 40px 30px;
                    text-align: center;
                    color: #333333;
                }}
                .room-name {{
                    font-size: 16px;
                    color: #666666;
                    margin-bottom: 25px;
                }}
                .balance-container {{
                    margin: 20px 0 30px 0;
                    padding: 40px 20px;
                    background: linear-gradient(to bottom, #fff1f2, #fff);
                    border-radius: 20px;
                    border: 1px solid #ffe4e6;
                    box-shadow: inset 0 2px 4px rgba(255,192,203,0.1);
                }}
                .balance-label {{
                    font-size: 14px;
                    color: #e11d48;
                    font-weight: 600;
                    margin-bottom: 15px;
                    display: block;
                    letter-spacing: 1px;
                }}
                .balance-amount {{
                    font-size: 64px;
                    font-weight: 800;
                    color: #be123c;
                    line-height: 1;
                    font-family: "SF Pro Display", -apple-system, sans-serif;
                }}
                .currency {{
                    font-size: 20px;
                    font-weight: 500;
                    margin-left: 8px;
                    vertical-align: super;
                }}
                .message {{
                    font-size: 14px;
                    color: #718096;
                    line-height: 1.6;
                    padding: 0 10px;
                }}
                .footer {{
                    padding: 20px;
                    text-align: center;
                    font-size: 12px;
                    color: #a0aec0;
                    background-color: #f8fafc;
                    border-top: 1px solid #edf2f7;
                }}
            </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚨 电费余额告警</h1>
                    </div>
                    <div class="content">
                        <div class="room-name">您的房间 <strong>{room_name}</strong> 电费已不足</div>
                        <div class="balance-container">
                            <span class="balance-label">当前剩余电费</span>
                            <div class="balance-amount">{balance:.2f}<span class="currency">元</span></div>
                        </div>
                        <p class="message">
                            当前余额已低于告警阈值（<b>{ALERT_THRESHOLD}</b>元）。<br>
                            系统已进入高频实时监控模式，为避免断电影响您的生活，请尽快完成充值。
                        </p>
                    </div>
                    <div class="footer">
                        智能电费监控系统自动发送 · 请勿直接回复
                    </div>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
            
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) if SMTP_PORT == 465 else smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            if SMTP_PORT != 465: server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            logging.info("📧 告警邮件发送成功！")
            return True
        except Exception as e:
            logging.error(f"邮件发送失败: {str(e)}")
            return False

    def calculate_next_interval(self, current_balance, current_time):
        """核心大脑：预测消耗速率并计算下一次休眠时间"""
        # 兜底：如果低于告警线，强制进入最快频率紧逼
        if current_balance <= ALERT_THRESHOLD:
            logging.warning("⚠️ 余额已跌破告警线！强制进入高频跟踪模式。")
            return MIN_INTERVAL_HOURS

        # 如果没有历史数据，默认返回最长间隔
        if self.last_balance is None or self.last_check_time is None:
            return MAX_INTERVAL_HOURS
            
        time_diff_hours = (current_time - self.last_check_time).total_seconds() / 3600.0
        balance_drop = self.last_balance - current_balance
        
        # 异常情况处理：刚刚充过电 或者 时间差异常
        if balance_drop < 0:
            logging.info(f"💡 检测到余额增加 (+{-balance_drop:.2f}元)，可能是刚刚完成充值。重新开始测算！")
            return MAX_INTERVAL_HOURS
            
        if balance_drop == 0 or time_diff_hours <= 0:
            logging.info("🍃 电量几乎无消耗，保持最长休眠时间。")
            return MAX_INTERVAL_HOURS

        # 计算消耗速率 (元/小时)
        rate = balance_drop / time_diff_hours
        
        # 预测：剩余金额还能撑多少小时到阈值
        hours_to_alert = (current_balance - ALERT_THRESHOLD) / rate
        
        # 留出余量提前检查
        suggested_interval = hours_to_alert * SAFE_MARGIN
        
        logging.info(f"📊 数据分析: 近期耗电速率为 {rate:.3f} 元/小时。")
        logging.info(f"🔮 算法预测: 预计约 {hours_to_alert:.1f} 小时后触及告警线，建议 {suggested_interval:.1f} 小时后复查。")
        
        # 严格执行规则约束：不能高于MAX，也不能低于MIN
        final_interval = max(MIN_INTERVAL_HOURS, min(MAX_INTERVAL_HOURS, suggested_interval))
        
        if final_interval == MAX_INTERVAL_HOURS:
            logging.info(f"✅ 触发约束: 建议休眠过长，强制执行【频率不低于{MAX_INTERVAL_HOURS}小时一次】的保底规则。")
            
        return final_interval

    def execute_task(self):
        """单次执行的任务"""
        logging.info(">> 启动智能巡检...")
        current_time = datetime.now()
        result = self.get_electricity_balance()
        
        if result is None:
            logging.warning("抓取失败，1小时后重试...")
            return 1.0 # 失败时固定1小时后重试

        room_name = result['room_name']
        balance = result['balance']
        logging.info(f"✅ 查询成功 -> 房间: [{room_name}], 当前余额: {balance:.2f} 元")

        # 邮件告警判断逻辑
        if balance <= ALERT_THRESHOLD:
            can_send = True
            if self.last_alert_time:
                cooldown = (current_time - self.last_alert_time).total_seconds()
                if cooldown < EMAIL_COOLDOWN:
                    can_send = False
            
            if can_send:
                if self.send_alert_email(room_name, balance):
                    self.last_alert_time = current_time

        # 将当前数据喂给算法，计算出下一次执行需要等待的小时数
        next_delay_hours = self.calculate_next_interval(balance, current_time)
        
        # 更新状态缓存
        self.last_balance = balance
        self.last_check_time = current_time
        
        logging.info("=" * 55)
        return next_delay_hours

def start_daemon():
    logging.info("=======================================================")
    logging.info("   🤖 智能电费监控服务启动  ")
    logging.info("=======================================================")
    
    monitor = SmartElecMonitor()
    scheduler = BlockingScheduler()

    def job_wrapper():
        # 执行具体任务并获取下次需要等待的小时数
        delay_hours = monitor.execute_task()
        
        # 动态计算下一次的执行时间点
        next_run_time = datetime.now() + timedelta(hours=delay_hours)
        logging.info(f"⏳ 下次自动查询计划于: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')} (距今 {delay_hours:.2f} 小时)")
        
        # 将新计划推入调度器中（替换掉之前的规则）
        scheduler.add_job(
            job_wrapper, 
            trigger='date', 
            run_date=next_run_time, 
            id='dynamic_monitor_job', 
            replace_existing=True
        )

    # 程序启动时立即执行第一次
    job_wrapper()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("已手动安全停止服务。")
    except Exception as e:
        logging.warning("未知错误，已安全退出")

if __name__ == "__main__":
    start_daemon()