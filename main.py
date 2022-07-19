import json
import os
import re
import threading
import time

import interactions
import requests
from bs4 import BeautifulSoup

bot = interactions.Client(token=os.getenv('BOT_TOKEN'))
guild_id = int(os.getenv("GUILD_ID"))
webhook_url = os.getenv("WEBHOOK_URL")
file_name = "store/subscribed.json"
sleep_time = 3600
list_link = "http://www.psu.ru/files/docs/priem-2022/"

if os.path.exists(file_name):
    with open(file_name, "r") as read_file:
        data = json.loads(read_file.read())
else:
    data = {'last_list_size': -1, 'abit': {}, "spec": {}}


def save():
    with open(file_name, "w") as write_file:
        write_file.write(json.dumps(data, skipkeys=True))


@bot.command(
    name="set-id",
    description="Задать СНИЛС для поиска",
    scope=guild_id,
)
async def set_id(ctx: interactions.CommandContext):
    modal = interactions.Modal(
        title="Введите данные для поиска",
        custom_id="set-id",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="СНИЛС",
                custom_id="id_text",
                min_length=11,
                max_length=11,
            )
        ],
    )

    await ctx.popup(modal)


@bot.modal("set-id")
async def modal_response(ctx, response: str):
    if not re.compile("\\d{11}").match(response):
        await ctx.send("Неверный формат СНИЛС. Должен состоять из 11 цифр")
        return
    data['abit'][str(ctx.author.id)] = {"id": response}
    save()
    await ctx.send(f"Сохранили. СНИЛС: {response}", ephemeral=True)


def checkList():
    req_text = requests.get(list_link, headers="")

    current_list_size = int(req_text.headers["Content-Length"])
    if req_text.status_code != 200:
        print("Error: {} {}".format(req_text.status_code, req_text.reason))
    elif current_list_size != data["last_list_size"]:
        req_text = requests.get(list_link)
        req_text.encoding = req_text.apparent_encoding
        req_text = req_text.text
        time = re.search(re.compile("Сформировано(.*)<"), req_text)[1].strip()
        soup = BeautifulSoup(req_text, "html.parser")
        base_spec = {}

        for dis_id in data['abit'].items():
            new_val = parse_place_by_id(soup, data['abit'][dis_id[0]]['id'])
            txt = f"<@{dis_id[0]}>, опубликовано новое изменение! ({time})"

            if 'prev' not in data['abit'][dis_id[0]]:
                data['abit'][dis_id[0]]['prev'] = {}

            for spec in new_val.items():
                is_spec_in_prev = spec[0] in data['abit'][dis_id[0]]['prev']
                if spec[0] not in base_spec:
                    base_spec[spec[0]] = parse_spec(soup, spec[0])
                spec_parsed = base_spec[spec[0]]
                txt += f'''\nНаправление: *{spec[0]}*
Проходной балл: {spec_parsed['passing_score']}
КЦП: {spec_parsed['admission_digits'][0]} / {spec_parsed['admission_digits'][1]}; ОП: {spec_parsed['admission_digits'][2]} 
Количество заявлений: {spec_parsed['total_applicants']}
Количество заявлений на место: {round(spec_parsed['total_applicants'] / spec_parsed['admission_digits'][0], 2)}
**Место в списке: {spec[1]}**
'''
                if is_spec_in_prev:
                    place_change = data['abit'][dis_id[0]]['prev'][spec[0]] - new_val[spec[0]]
                    if place_change != 0:
                        txt += f'Изменение: {"+" if place_change > 0 else "-"}{abs(place_change)} ' + (":arrow_up:" if place_change > 0
                                                                                           else ":arrow_down:") + "\n"
                data['abit'][dis_id[0]]['prev'][spec[0]] = spec[1]
                data['spec'][spec[0]] = spec_parsed
            d_val = {'content': txt}
            if len(new_val.items()) > 0:
                requests.post(webhook_url, json=d_val)

        data["last_list_size"] = current_list_size
        save()

def parse_spec(soup, spec_name):
    spec_element = soup.find("span", string=spec_name).parent.parent
    admission_digits = list(int(k.text) for k in spec_element.find_all("strong") if k.text.isdigit())[:8]

    return {
        "admission_digits": admission_digits,
        "passing_score": int(spec_element.find("td", string=admission_digits[0]).parent.find_all("td")[-1].text),
        "total_applicants": int(spec_element.find("table").find_all("tr")[-1].find("td").text),
    }


def parse_place_by_id(soup, id):
    places = {}
    for spec in soup.find_all("font", string=id):
        _parent = spec.parent.parent
        spec_name = _parent.parent.parent.find("h2").find_all("span")[2].get_text()
        places[spec_name] = int(_parent.find("td").text)
    return places


def worker():
    while True:
        checkList()
        time.sleep(sleep_time)


thread = threading.Thread(target=worker)
thread.start()
bot.start()
