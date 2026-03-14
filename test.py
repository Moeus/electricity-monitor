# Scraping electricity bill information
import requests
import json
import random
import string
import uuid
from urllib.parse import quote
from pprint import pprint
# 生成必要的随机值
device_id = ''.join(random.choices(string.ascii_letters, k=24))
client_id = uuid.uuid4().hex
 
# 登录获取token
username = ""
password = ""
password_encoded = quote(password)
 
login_url = f"https://mycas.hut.edu.cn/token/password/passwordLogin?username={username}&password={password_encoded}&appId=com.supwisdom.hut&geo&deviceId={device_id}&osType=android&clientId={client_id}&mfaState"
 
login_response = requests.post(login_url, headers={
    'User-Agent': 'SWSuperApp/1.1.3(XiaomidadaXiaomi15)',
    'Accept': '*/*'
})
pprint(login_response.json())
id_token = login_response.json()['data']['idToken']
 
# 获取openid和JSESSIONID
openid_response = requests.get(
    'https://v8mobile.hut.edu.cn/zdRedirect/toSingleMenu',
    params={'code': 'openWater', 'token': id_token},
    headers={'X-Id-Token': id_token},
    allow_redirects=False
)
pprint(openid_response)
location = openid_response.headers['Location']
openid = location.split('openid=')[1]
jsessionid = openid_response.cookies.get('JSESSIONID')
print(f"OpenID: {openid}, JSESSIONID: {jsessionid}")
 
# 获取房间绑定信息
history_response = requests.post(
    f'https://v8mobile.hut.edu.cn/myaccount/querywechatUserLastInfo?openid={openid}',
    json={"idserial": username, "openid": openid},
    headers={
        'Cookie': f'userToken={id_token}; JSESSIONID={jsessionid}',
        'Accept': 'application/json'
    }
)
 
history_data = history_response.json()
bind_info = json.loads(history_data['resultData']['elelastbind'])
print(f"房间信息: {bind_info}")
 
# 查询电费
room_response = requests.post(
    f'https://v8mobile.hut.edu.cn/channel/queryRoomDetail?openid={openid}',
    json={
        "areaid": bind_info['areaid'],
        "buildingid": bind_info['buildingid'],
        "factorycode": bind_info['factorycode'],
        "roomid": bind_info['roomid']  # 或者指定其他房间ID
    },
    headers={
        'Cookie': f'userToken={id_token}; JSESSIONID={jsessionid}',
        'Accept': 'application/json'
    }
)
pprint(room_response.json())
room_data = room_response.json()['resultData']
print(f"房间: {room_data['accname']}, 剩余电费: {room_data['eledetail']}")